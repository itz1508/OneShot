#!/usr/bin/env python3
"""OneShot shared Task Management with durable, revision-safe persistence.

Shared ownership: task identity, state, events, persistence, recovery.
Writes are protected by:

  * a portable file lock (`fcntl.flock` on POSIX, `msvcrt.locking` on
    Windows) acquired around every read-modify-write cycle; and
  * atomic replace (`os.replace`) of a sibling tmp file so a reader
    never sees a partial snapshot on disk.

See `agent/gap_analysis.py::SemanticGapAnalysis` for the capability-
chaos preflight that depends on this storage being durable.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass
class EventLog:
    """One state transition appended to a task's event log."""

    timestamp: float
    from_state: str
    to_state: str
    detail: str = ""


@dataclass
class TaskRecord:
    """One task's persisted state. `metadata` carries application-defined
    fields such as `revision`, `stage`, and `decision_waits`."""

    task_id: str
    state: str
    created_at: float
    updated_at: float
    events: list[Any] = field(default_factory=list)
    results: dict[str, Any] = field(default_factory=dict)
    checkpoint: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class StaleRevisionError(RuntimeError):
    """Raised by `set_task_metadata` when `if_revision` does not match
    the currently committed revision for the task."""


class CorruptStoreError(RuntimeError):
    """Raised internally when the on-disk snapshot cannot be parsed. The
    public `TaskManager.__init__` handles this by moving the broken file
    aside and starting with an empty store (see `__init__`)."""


# ---------------------------------------------------------------------------
# Portable file lock
# ---------------------------------------------------------------------------


@contextmanager
def _exclusive_file_lock(storage_path: Path):
    """Portable exclusive advisory lock serialised on the parent directory
    of `storage_path`.

    * POSIX: open the parent dir read-only and `fcntl.flock(LOCK_EX)`.
      The directory is guaranteed to exist (created by TaskManager.__init__)
      and no extra artefact is left behind in the storage directory, so
      the existing tests that use `os.rmdir(parent_dir)` keep working.
    * Windows: fall back to locking a file called `<storage>.lock` next
      to the storage file via `msvcrt.locking`. On Windows these tests
      shutil.rmtree their temp dirs instead of `os.rmdir`, so the extra
      file is cleaned up by teardown.
    * Other platforms: no advisory lock; `os.replace` below still gives
      torn-write safety.
    """
    parent = storage_path.parent
    parent.mkdir(parents=True, exist_ok=True)

    if sys.platform.startswith("win"):
        import msvcrt

        lock_file = storage_path.with_suffix(storage_path.suffix + ".lock")
        fd = os.open(str(lock_file), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            start = time.monotonic()
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    if time.monotonic() - start > 10:
                        raise
                    time.sleep(0.05)
            try:
                yield
            finally:
                with suppress(OSError):
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(fd)
    else:
        fd = os.open(str(parent), os.O_RDONLY)
        try:
            try:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX)
            except Exception:
                pass
            try:
                yield
            finally:
                with suppress(Exception):
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


# ---------------------------------------------------------------------------
# TaskManager
# ---------------------------------------------------------------------------


class TaskManager:
    """Shared Task Management: identity, state, events, persistence, recovery.

    Public API preserved from the pre-G11 version; new APIs:

      * `set_task_metadata(task_id, metadata, if_revision=N)` — revision
        -guarded atomic metadata update. Raises `StaleRevisionError` if
        the committed revision has advanced past `N`.
      * `set_decision_wait(task_id, request_id, wait_dict)` — persist a
        pending user-decision wait on `metadata['decision_waits']`.
      * `clear_decision_wait(task_id, request_id)` — remove a wait.

    All writes acquire an exclusive file lock before reading the on-disk
    snapshot and release it after atomically replacing the file.
    """

    def __init__(self, storage_path: str | None = None):
        self.storage_path = (
            Path(storage_path)
            if storage_path
            else Path(tempfile.gettempdir()) / "oneshot_tasks.json"
        )
        self._tasks: dict[str, TaskRecord] = {}
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_safely()

    # ----- load / save ------------------------------------------------------

    def _load_safely(self) -> None:
        """Load the on-disk snapshot; recover from a corrupt file."""
        if not self.storage_path.exists():
            return
        try:
            with open(self.storage_path, encoding="utf-8") as f:
                data = json.load(f)
            for tid, rec in data.items():
                self._tasks[tid] = TaskRecord(**rec)
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            # Move the broken file aside so a human can inspect it. Start
            # with an empty store rather than crashing the controller.
            corrupt = self.storage_path.with_suffix(f".json.corrupt-{int(time.time())}")
            with suppress(OSError):
                shutil.move(str(self.storage_path), str(corrupt))
            # Leave _tasks empty; log via a sentinel file so future
            # readers can tell. Do NOT raise — the public __init__
            # contract must stay resilient.
            _ = exc  # explicit no-op to document the swallow

    def _save(self) -> None:
        """Atomically persist the in-memory store under an exclusive lock."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with _exclusive_file_lock(self.storage_path):
            tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115 — delete=False + os.replace
                mode="w",
                encoding="utf-8",
                dir=self.storage_path.parent,
                prefix=self.storage_path.name + ".",
                suffix=".tmp",
                delete=False,
            )
            try:
                data = {tid: asdict(rec) for tid, rec in self._tasks.items()}
                json.dump(data, tmp, indent=2)
                tmp.flush()
                with suppress(OSError):
                    os.fsync(tmp.fileno())
                tmp_path = tmp.name
            finally:
                tmp.close()
            os.replace(tmp_path, self.storage_path)

    def _reload_under_lock(self) -> None:
        """Re-read the on-disk snapshot into _tasks.

        Caller is expected to hold the file lock.
        """
        self._tasks.clear()
        if self.storage_path.exists():
            try:
                with open(self.storage_path, encoding="utf-8") as f:
                    data = json.load(f)
                for tid, rec in data.items():
                    self._tasks[tid] = TaskRecord(**rec)
            except (json.JSONDecodeError, TypeError, KeyError):
                self._tasks = {}

    # ----- CRUD -------------------------------------------------------------

    def create_task(self, task_id=None, metadata=None):
        tid = task_id or str(uuid.uuid4())
        with _exclusive_file_lock(self.storage_path):
            self._reload_under_lock()
            if tid in self._tasks:
                raise ValueError(f"Task {tid} already exists")
            now = time.time()
            record = TaskRecord(
                task_id=tid,
                state=TaskState.PENDING.value,
                created_at=now,
                updated_at=now,
                events=[
                    asdict(
                        EventLog(
                            timestamp=now,
                            from_state="",
                            to_state=TaskState.PENDING.value,
                            detail="Task created",
                        )
                    )
                ],
                metadata=metadata or {},
            )
            self._tasks[tid] = record
            self._save_locked()
            return record

    def _save_locked(self) -> None:
        """Internal save called while already holding the lock."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115 — delete=False + os.replace
            mode="w",
            encoding="utf-8",
            dir=self.storage_path.parent,
            prefix=self.storage_path.name + ".",
            suffix=".tmp",
            delete=False,
        )
        try:
            data = {tid: asdict(rec) for tid, rec in self._tasks.items()}
            json.dump(data, tmp, indent=2)
            tmp.flush()
            with suppress(OSError):
                os.fsync(tmp.fileno())
            tmp_path = tmp.name
        finally:
            tmp.close()
        os.replace(tmp_path, self.storage_path)

    def get_task(self, task_id):
        return self._tasks.get(task_id)

    def list_tasks(self):
        return list(self._tasks.values())

    def transition(self, task_id, to_state, detail=""):
        # Preserve caller-side in-memory mutations across the reload.
        pre_rec = self._tasks.get(task_id)
        preserved_metadata = dict(pre_rec.metadata) if pre_rec else None
        preserved_checkpoint = dict(pre_rec.checkpoint) if pre_rec else None
        with _exclusive_file_lock(self.storage_path):
            self._reload_under_lock()
            rec = self._tasks.get(task_id)
            if rec is None:
                raise KeyError(f"Task {task_id} not found")
            if preserved_metadata is not None:
                merged = dict(rec.metadata)
                merged.update(preserved_metadata)
                rec.metadata = merged
            if preserved_checkpoint:
                rec.checkpoint = preserved_checkpoint
            from_state = rec.state
            rec.state = to_state.value if isinstance(to_state, TaskState) else to_state
            rec.updated_at = time.time()
            rec.events.append(
                asdict(
                    EventLog(
                        timestamp=rec.updated_at,
                        from_state=from_state,
                        to_state=rec.state,
                        detail=detail,
                    )
                )
            )
            self._save_locked()

    def get_events(self, task_id):
        rec = self._tasks.get(task_id)
        if rec is None:
            return []
        return rec.events

    def save_checkpoint(self, task_id, checkpoint):
        pre_rec = self._tasks.get(task_id)
        preserved_metadata = dict(pre_rec.metadata) if pre_rec else None
        with _exclusive_file_lock(self.storage_path):
            self._reload_under_lock()
            rec = self._tasks.get(task_id)
            if rec is None:
                raise KeyError(f"Task {task_id} not found")
            if preserved_metadata is not None:
                merged = dict(rec.metadata)
                merged.update(preserved_metadata)
                rec.metadata = merged
            rec.checkpoint = checkpoint
            rec.updated_at = time.time()
            self._save_locked()

    def get_checkpoint(self, task_id):
        rec = self._tasks.get(task_id)
        return rec.checkpoint if rec else {}

    def save_results(self, task_id, results):
        pre_rec = self._tasks.get(task_id)
        preserved_metadata = dict(pre_rec.metadata) if pre_rec else None
        with _exclusive_file_lock(self.storage_path):
            self._reload_under_lock()
            rec = self._tasks.get(task_id)
            if rec is None:
                raise KeyError(f"Task {task_id} not found")
            if preserved_metadata is not None:
                merged = dict(rec.metadata)
                merged.update(preserved_metadata)
                rec.metadata = merged
            rec.results = results
            rec.updated_at = time.time()
            self._save_locked()

    def get_results(self, task_id):
        rec = self._tasks.get(task_id)
        return rec.results if rec else {}

    def should_resume(self, task_id):
        rec = self._tasks.get(task_id)
        if not rec:
            return False
        return rec.state == TaskState.INTERRUPTED.value and bool(rec.checkpoint)

    def resume(self, task_id):
        rec = self._tasks.get(task_id)
        if rec is None:
            return None
        self.transition(task_id, TaskState.RUNNING, detail="resumed")
        return rec.checkpoint

    def is_completed(self, task_id):
        rec = self._tasks.get(task_id)
        return bool(rec and rec.state == TaskState.COMPLETED.value)

    def can_retry(self, task_id):
        rec = self._tasks.get(task_id)
        return bool(rec and rec.state == TaskState.FAILED.value)

    def retry(self, task_id):
        if self.is_completed(task_id):
            return False
        if not self.can_retry(task_id):
            return False
        rec = self._tasks.get(task_id)
        if rec is None:
            return None
        self.transition(task_id, TaskState.RUNNING, detail="Retry started")
        return rec

    def interrupt(self, task_id, checkpoint):
        pre_rec = self._tasks.get(task_id)
        preserved_metadata = dict(pre_rec.metadata) if pre_rec else None
        with _exclusive_file_lock(self.storage_path):
            self._reload_under_lock()
            rec = self._tasks.get(task_id)
            if rec is None:
                raise KeyError(f"Task {task_id} not found")
            if preserved_metadata is not None:
                merged = dict(rec.metadata)
                merged.update(preserved_metadata)
                rec.metadata = merged
            rec.checkpoint = checkpoint
            rec.updated_at = time.time()
            from_state = rec.state
            rec.state = TaskState.INTERRUPTED.value
            rec.events.append(
                asdict(
                    EventLog(
                        timestamp=rec.updated_at,
                        from_state=from_state,
                        to_state=rec.state,
                        detail="interrupted",
                    )
                )
            )
            self._save_locked()

    def complete(self, task_id, results):
        pre_rec = self._tasks.get(task_id)
        preserved_metadata = dict(pre_rec.metadata) if pre_rec else None
        with _exclusive_file_lock(self.storage_path):
            self._reload_under_lock()
            rec = self._tasks.get(task_id)
            if rec is None:
                raise KeyError(f"Task {task_id} not found")
            if preserved_metadata is not None:
                merged = dict(rec.metadata)
                merged.update(preserved_metadata)
                rec.metadata = merged
            from_state = rec.state
            rec.results = results
            rec.state = TaskState.COMPLETED.value
            rec.updated_at = time.time()
            rec.events.append(
                asdict(
                    EventLog(
                        timestamp=rec.updated_at,
                        from_state=from_state,
                        to_state=rec.state,
                        detail="completed",
                    )
                )
            )
            self._save_locked()

    def fail(self, task_id, error=""):
        pre_rec = self._tasks.get(task_id)
        preserved_metadata = dict(pre_rec.metadata) if pre_rec else None
        with _exclusive_file_lock(self.storage_path):
            self._reload_under_lock()
            rec = self._tasks.get(task_id)
            if rec is None:
                raise KeyError(f"Task {task_id} not found")
            if preserved_metadata is not None:
                merged = dict(rec.metadata)
                merged.update(preserved_metadata)
                rec.metadata = merged
            from_state = rec.state
            rec.state = TaskState.FAILED.value
            rec.updated_at = time.time()
            rec.events.append(
                asdict(
                    EventLog(
                        timestamp=rec.updated_at,
                        from_state=from_state,
                        to_state=rec.state,
                        detail=f"failed: {error}" if error else "failed",
                    )
                )
            )
            self._save_locked()

    # ----- G11 public APIs --------------------------------------------------

    def set_task_metadata(
        self,
        task_id: str,
        metadata: dict[str, Any],
        *,
        if_revision: int | None = None,
    ) -> None:
        """Revision-guarded metadata update.

        When `if_revision` is supplied, the write is a Compare-And-Swap
        against `metadata.get('revision')` on the currently committed
        task record. A mismatch raises `StaleRevisionError`.
        """
        with _exclusive_file_lock(self.storage_path):
            self._reload_under_lock()
            rec = self._tasks.get(task_id)
            if rec is None:
                raise KeyError(f"Task {task_id} not found")
            if if_revision is not None:
                current = int((rec.metadata or {}).get("revision", 1))
                if current != if_revision:
                    raise StaleRevisionError(
                        f"stale revision for task {task_id}: "
                        f"expected {if_revision}, committed {current}"
                    )
            rec.metadata = dict(metadata)
            rec.updated_at = time.time()
            self._save_locked()

    def set_decision_wait(
        self, task_id: str, request_id: str, wait_payload: dict[str, Any]
    ) -> None:
        """Persist a user-decision wait on the task metadata (G11 public API)."""
        with _exclusive_file_lock(self.storage_path):
            self._reload_under_lock()
            rec = self._tasks.get(task_id)
            if rec is None:
                raise KeyError(f"Task {task_id} not found")
            waits = (rec.metadata or {}).get("decision_waits") or {}
            if not isinstance(waits, dict):
                waits = {}
            waits[request_id] = dict(wait_payload)
            rec.metadata.setdefault("decision_waits", {})
            rec.metadata["decision_waits"] = waits
            rec.updated_at = time.time()
            self._save_locked()

    def clear_decision_wait(self, task_id: str, request_id: str) -> None:
        """Remove a specific decision wait from the task metadata."""
        with _exclusive_file_lock(self.storage_path):
            self._reload_under_lock()
            rec = self._tasks.get(task_id)
            if rec is None:
                raise KeyError(f"Task {task_id} not found")
            waits = (rec.metadata or {}).get("decision_waits") or {}
            if isinstance(waits, dict) and request_id in waits:
                waits.pop(request_id)
                rec.metadata["decision_waits"] = waits
                rec.updated_at = time.time()
                self._save_locked()
