"""MVP task input and event adapter. HostController owns workflow state.

This adapter does not execute or promote workflow stages and never emits
fabricated Research/Audit/Plan completion records.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from pydantic import BaseModel, Field

from agent.contracts.work_todo import WorkStatus
from agent.runtime.artifact_store import ArtifactStore, StaleRevisionError
from agent.runtime.authorization import Capability
from agent.runtime.controller import HostController
from agent.runtime.work_todo import WorkTodoManager
from mvp.mcp_research import register_mcp_research, research_artifact_id

_ID = re.compile(r"^[0-9a-f]{32}$")


class TaskInput(BaseModel):
    task_id: str
    text: str = Field(min_length=1, max_length=20000)
    purpose: str = Field(default="research", pattern=r"^(research|audit)$")
    thread_message_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,128}$")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MVPError(ValueError):
    pass


class _ResearchAdmissionStore:
    """Process-independent admission for local workers sharing one SQLite state root.

    A crashed owner may be reclaimed only after its OS process no longer exists.
    This is not a distributed lease across separate hosts.
    """

    def __init__(self, state_root: str | Path) -> None:
        self.path = Path(state_root) / "research_admission.db"
        with sqlite3.connect(str(self.path)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS active_research "
                "(task_id TEXT PRIMARY KEY, owner_token TEXT NOT NULL, owner_pid INTEGER NOT NULL)"
            )

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid < 1:
            return True
        if sys.platform == "win32":
            # On Windows, os.kill(pid, 0) sends CTRL_C_EVENT rather than
            # probing for existence. Query a process handle instead.
            import ctypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = (ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32)
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_uint32)
            kernel32.WaitForSingleObject.restype = ctypes.c_uint32
            kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
            kernel32.CloseHandle.restype = ctypes.c_int
            handle = kernel32.OpenProcess(0x100000, 0, pid)  # SYNCHRONIZE
            if not handle:
                return ctypes.get_last_error() != 87  # ERROR_INVALID_PARAMETER: no such PID
            try:
                result = kernel32.WaitForSingleObject(handle, 0)
                return result != 0  # WAIT_OBJECT_0 means the process has exited.
            finally:
                kernel32.CloseHandle(handle)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return True
        return True

    def acquire(self, task_id: str) -> str:
        token = uuid4().hex
        with sqlite3.connect(str(self.path), timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT owner_pid FROM active_research WHERE task_id = ?", (task_id,)).fetchone()
            if row is not None:
                pid = int(row[0])
                if self._pid_alive(pid):
                    raise MVPError("Research execution conflict: task is already active")
                conn.execute("DELETE FROM active_research WHERE task_id = ?", (task_id,))
            conn.execute(
                "INSERT INTO active_research (task_id, owner_token, owner_pid) VALUES (?, ?, ?)",
                (task_id, token, os.getpid()),
            )
        return token

    def release(self, task_id: str, token: str) -> None:
        with sqlite3.connect(str(self.path), timeout=10) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM active_research WHERE task_id = ? AND owner_token = ?",
                (task_id, token),
            )


class MVPService:
    def __init__(self, state_root: str | Path) -> None:
        # Host pins scanner scope at initialization, not at the request boundary.
        configured_root = os.environ.get("MCP_WORKSPACE_ROOT", "")
        trusted = os.environ.get("MCP_TRUSTED_ANCESTRY") == "true"
        candidate = Path(configured_root) if configured_root else None
        self.audit_workspace_root = (
            candidate.resolve()
            if trusted and candidate is not None and candidate.is_absolute() and candidate.is_dir()
            else None
        )
        self.host = HostController(state_root, workspace_root=self.audit_workspace_root)
        if self.audit_workspace_root is not None:
            self.host.authorization.grant("research-audit", Capability.SCANNER, str(self.audit_workspace_root))
        self.artifacts: ArtifactStore = self.host.artifact_store
        # One-time registration eliminates the per-request discovery/registration race.
        register_mcp_research(self.host.providers)
        self._active_guard = Lock()
        self._active_requests: set[str] = set()
        self._admission = _ResearchAdmissionStore(state_root)

    @contextmanager
    def research_slot(self, task_id: str) -> Iterator[None]:
        """Guard in-process Research starts and input edits for the same task.

        SQLite governs cross-process admission for a shared state root. The
        in-memory guard is not a durable authorization or recovery receipt.
        """
        self._check_id(task_id)
        token = self._admission.acquire(task_id)
        try:
            with self._active_guard:
                if task_id in self._active_requests:
                    raise MVPError("Research execution conflict: task is already active")
                self._active_requests.add(task_id)
            try:
                yield
            finally:
                with self._active_guard:
                    self._active_requests.discard(task_id)
        finally:
            self._admission.release(task_id, token)

    @staticmethod
    def _check_id(task_id: str) -> str:
        if _ID.fullmatch(task_id) is None:
            raise MVPError("invalid task identifier")
        return task_id

    @staticmethod
    def _artifact_id(task_id: str) -> str:
        return f"mvp-input:{task_id}"

    def create(self, prompt: str, purpose: str = "research") -> dict[str, object]:
        cleaned = prompt.strip()
        if not cleaned or len(cleaned) > 20000:
            raise MVPError("task text must contain 1-20000 characters")
        if purpose not in ("research", "audit"):
            raise MVPError("purpose must be research or audit")
        task_id = uuid4().hex
        run_id = f"run-{task_id}"
        record = TaskInput(
            task_id=task_id,
            text=cleaned,
            purpose=purpose,
            thread_message_id=f"msg_{uuid4().hex}",
        )
        self.artifacts.put_immutable(record, self._artifact_id(task_id), 1, "mvp_task_input", "1.0")
        self.host.init_task(task_id, run_id)
        self.host.event_store.append(task_id, "mvp_input_persisted", "input revision 1")
        if purpose == "audit":
            self.host.event_store.append(task_id, "audit_queued", "Read-only audit capability awaiting execution")
        else:
            self.host.event_store.append(task_id, "mvp_research_ready", "Research awaits an explicit MCP request")
        return self.get(task_id)

    def get(self, task_id: str) -> dict[str, object]:
        self._check_id(task_id)
        state = self.host.get_state(task_id)
        if state is None:
            raise MVPError("task not found")
        input_record, revision, digest = self.read_input(task_id)
        research_id = research_artifact_id(task_id, state.run_id)
        research_done = self.artifacts.latest_revision(research_id) > 0
        audit_done = False
        audit_disposition = ""
        audit_work_status = ""
        if input_record.purpose == "audit":
            from agent.contracts.audit import AuditFindingsRecord
            from mvp.research_host import audit_artifact_id

            audit_id = audit_artifact_id(task_id, state.run_id)
            if self.artifacts.latest_revision(audit_id) > 0:
                audit = AuditFindingsRecord.model_validate_json(self.artifacts.get_verified(audit_id, 1))
                if audit.task_id != task_id or audit.run_id != state.run_id:
                    raise MVPError("audit artifact belongs to a different task/run")
                audit_disposition = audit.disposition
                audit_done = audit_disposition != "blocked" and state.active_work_artifact_id is None
            if state.active_work_artifact_id is not None:
                todo_id = state.active_work_artifact_id
                todo_revision = self.artifacts.latest_revision(todo_id)
                todo_digest = self.artifacts.get_digest(todo_id, todo_revision)
                if todo_revision > 0 and todo_digest is not None:
                    todo_ref = WorkTodoManager._ref(todo_id, todo_revision, todo_digest, "work_todo")
                    todo = self.host.work_todos.read(todo_ref)
                    audit_work_status = todo.actions[0].status.value
        if input_record.purpose == "audit":
            execution_status = (
                "audit_blocked"
                if audit_disposition == "blocked" or audit_work_status == WorkStatus.BLOCKED.value
                else "audit_completed"
                if audit_done
                else "audit_recovery_required"
                if audit_disposition and audit_work_status == WorkStatus.RUNNING.value
                else "audit_running"
                if audit_work_status == WorkStatus.RUNNING.value
                else "audit_recovery_required"
                if state.active_work_artifact_id is not None
                else "audit_pending"
            )
        else:
            execution_status = (
                "research_completed" if research_done and state.current_stage.value != "research" else "awaiting_mcp"
            )
        return {
            "task_id": task_id,
            "run_id": state.run_id,
            "current_stage": state.current_stage.value,
            "completed_stages": [s.value for s in state.completed_stages],
            "execution_status": execution_status,
            "input_revision": revision,
            "input_digest": digest,
            "input_text": input_record.text,
            "thread_message_id": input_record.thread_message_id,
            "purpose": input_record.purpose,
            "audit_completed": audit_done,
            "audit_disposition": audit_disposition,
            "research_completed": research_done and state.current_stage.value != "research",
        }

    def read_input(self, task_id: str) -> tuple[TaskInput, int, str]:
        self._check_id(task_id)
        aid = self._artifact_id(task_id)
        revision = self.artifacts.latest_revision(aid)
        if revision < 1:
            raise MVPError("task input not found")
        raw = self.artifacts.get_verified(aid, revision)
        digest = self.artifacts.get_digest(aid, revision)
        if digest is None:
            raise MVPError("missing input artifact digest")
        record = TaskInput.model_validate_json(raw)
        if record.task_id != task_id:
            raise MVPError("input identity mismatch")
        return record, revision, digest

    def revise_input(self, task_id: str, text: str, expected_revision: int) -> dict[str, object]:
        with self.research_slot(task_id):
            return self._revise_input_locked(task_id, text, expected_revision)

    def _revise_input_locked(self, task_id: str, text: str, expected_revision: int) -> dict[str, object]:
        self._check_id(task_id)
        state = self.host.get_state(task_id)
        if state is None:
            raise MVPError("task not found")
        if state.current_stage.value != "research" or state.active_work_artifact_id is not None:
            raise MVPError("input locked after Research starts")
        if expected_revision < 1:
            raise MVPError("invalid expected revision")
        content = text.strip()
        if not content or len(content) > 20000:
            raise MVPError("task text must contain 1-20000 characters")
        current, _, _ = self.read_input(task_id)
        if current.purpose == "audit":
            from mvp.research_host import audit_artifact_id

            if self.artifacts.latest_revision(audit_artifact_id(task_id, state.run_id)) > 0:
                raise MVPError("input locked after Audit output; create a new task")
        record = TaskInput(
            task_id=task_id,
            text=content,
            purpose=current.purpose,
            thread_message_id=current.thread_message_id,
        )
        try:
            self.artifacts.put_cas(record, self._artifact_id(task_id), expected_revision, "mvp_task_input", "1.0")
        except StaleRevisionError as exc:
            raise MVPError("input revision conflict") from exc
        self.host.event_store.append(task_id, "mvp_input_revised", f"input revision {expected_revision + 1}")
        return self.get(task_id)

    def events(self, task_id: str, after: int = 0) -> list[dict[str, object]]:
        self._check_id(task_id)
        if after < 0:
            raise MVPError("invalid event cursor")
        if self.host.get_state(task_id) is None:
            raise MVPError("task not found")
        return [
            {
                "sequence": event["seq"],
                "type": event["event_type"],
                "message": event["event_data"],
                "created_at": event["created_at"],
            }
            for event in self.host.event_store.list(task_id)
            if event["seq"] > after
        ]

    def artifacts_for_task(self, task_id: str) -> list[dict[str, object]]:
        record, revision, digest = self.read_input(task_id)
        files: list[dict[str, object]] = [
            {
                "name": "_input.json",
                "kind": "input",
                "revision": revision,
                "digest": digest,
                "content": record.model_dump_json(indent=2),
            }
        ]
        state = self.host.get_state(task_id)
        if state is not None:
            research_id = research_artifact_id(task_id, state.run_id)
            if self.artifacts.latest_revision(research_id) > 0:
                files.append(
                    {
                        "name": "_research.json",
                        "kind": "research",
                        "revision": 1,
                        "digest": self.artifacts.get_digest(research_id, 1),
                        "content": self.artifacts.get_verified(research_id, 1).decode("utf-8"),
                    }
                )
            from mvp.research_host import audit_artifact_id

            audit_id = audit_artifact_id(task_id, state.run_id)
            if self.artifacts.latest_revision(audit_id) > 0:
                files.append(
                    {
                        "name": "_audit.json",
                        "kind": "audit",
                        "revision": 1,
                        "digest": self.artifacts.get_digest(audit_id, 1),
                        "content": self.artifacts.get_verified(audit_id, 1).decode("utf-8"),
                    }
                )
        # PRE/POST are supporting artifacts, not new canonical stages.
        for artifact_prefix, display_name, kind in (
            ("discovery-pre:", "_discovery_pre.json", "discovery"),
            ("discovery-research-request:", "input_request_search.json", "research_request"),
            ("discovery-post:", "_discovery_post.json", "audit_discovery"),
        ):
            aid = f"{artifact_prefix}{task_id}"
            rev = self.artifacts.latest_revision(aid)
            if rev > 0:
                files.append(
                    {
                        "name": display_name,
                        "kind": kind,
                        "revision": rev,
                        "digest": self.artifacts.get_digest(aid, rev),
                        "content": self.artifacts.get_verified(aid, rev).decode("utf-8"),
                    }
                )
        return files
