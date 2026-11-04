"""MVP task input and event adapter. HostController owns workflow state.

This adapter does not execute or promote workflow stages and never emits
fabricated Research/Audit/Plan completion records.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from pydantic import BaseModel, Field

from agent.runtime.artifact_store import ArtifactStore, StaleRevisionError
from agent.runtime.controller import HostController
from mvp.mcp_research import register_mcp_research, research_artifact_id

_ID = re.compile(r"^[0-9a-f]{32}$")


class TaskInput(BaseModel):
    task_id: str
    text: str = Field(min_length=1, max_length=20000)
    purpose: str = Field(default="research", pattern=r"^(research|audit)$")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MVPError(ValueError):
    pass


class MVPService:
    def __init__(self, state_root: str | Path) -> None:
        self.host = HostController(state_root)
        self.artifacts: ArtifactStore = self.host.artifact_store
        # One-time registration eliminates the per-request discovery/registration race.
        register_mcp_research(self.host.providers)
        self._active_guard = Lock()
        self._active_requests: set[str] = set()

    @contextmanager
    def research_slot(self, task_id: str) -> Iterator[None]:
        """Guard in-process Research starts and input edits for the same task.

        Cross-process admission is still governed by host CAS; do not use the
        in-memory guard as a durable authorization or recovery receipt.
        """
        self._check_id(task_id)
        with self._active_guard:
            if task_id in self._active_requests:
                raise MVPError("Research execution conflict: task is already active")
            self._active_requests.add(task_id)
        try:
            yield
        finally:
            with self._active_guard:
                self._active_requests.discard(task_id)

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
        record = TaskInput(task_id=task_id, text=cleaned, purpose=purpose)
        self.artifacts.put_immutable(record, self._artifact_id(task_id), 1, "mvp_task_input", "1.0")
        self.host.init_task(task_id, run_id)
        self.host.event_store.append(task_id, "mvp_input_persisted", "input revision 1")
        self.host.event_store.append(task_id, "mvp_mcp_unavailable", "MCP client not connected; no workflow executed")
        return self.get(task_id)

    def get(self, task_id: str) -> dict[str, object]:
        self._check_id(task_id)
        state = self.host.get_state(task_id)
        if state is None:
            raise MVPError("task not found")
        input_record, revision, digest = self.read_input(task_id)
        research_id = research_artifact_id(task_id, state.run_id)
        research_done = self.artifacts.latest_revision(research_id) > 0
        return {
            "task_id": task_id,
            "run_id": state.run_id,
            "current_stage": state.current_stage.value,
            "completed_stages": [s.value for s in state.completed_stages],
            "execution_status": (
                "research_completed" if research_done and state.current_stage.value != "research" else "awaiting_mcp"
            ),
            "input_revision": revision,
            "input_digest": digest,
            "input_text": input_record.text,
            "purpose": input_record.purpose,
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
        record = TaskInput(task_id=task_id, text=content)
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
        return files
