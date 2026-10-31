#!/usr/bin/env python3
"""
OneShot Assignment 01: Task Management (Shared Responsibility)

Task Management is a distinct shared responsibility: task identity, state,
events, persistence, and recovery. It is NOT memory retrieval — memory is
initialized at agent startup and Research retrieves from it.
"""

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass
class EventLog:
    timestamp: float
    from_state: str
    to_state: str
    detail: str = ""


@dataclass
class TaskRecord:
    task_id: str
    state: str
    created_at: float
    updated_at: float
    events: list = field(default_factory=list)
    results: dict = field(default_factory=dict)
    checkpoint: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class TaskManager:
    """Shared Task Management: identity, state, events, persistence, recovery."""

    def __init__(self, storage_path: Optional[str] = None):
        self.storage_path = Path(storage_path) if storage_path else Path("/tmp/oneshot_tasks.json")
        self._tasks: dict[str, TaskRecord] = {}
        self._load()

    def _load(self):
        if self.storage_path.exists():
            with open(self.storage_path, "r") as f:
                data = json.load(f)
                for tid, rec in data.items():
                    self._tasks[tid] = TaskRecord(**rec)

    def _save(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w") as f:
            data = {tid: asdict(rec) for tid, rec in self._tasks.items()}
            json.dump(data, f, indent=2)

    def create_task(self, task_id=None, metadata=None):
        tid = task_id or str(uuid.uuid4())
        if tid in self._tasks:
            raise ValueError(f"Task {tid} already exists")
        now = time.time()
        record = TaskRecord(
            task_id=tid, state=TaskState.PENDING.value,
            created_at=now, updated_at=now,
            events=[asdict(EventLog(timestamp=now, from_state="", to_state=TaskState.PENDING.value, detail="Task created"))],
            metadata=metadata or {},
        )
        self._tasks[tid] = record
        self._save()
        return record

    def get_task(self, task_id):
        return self._tasks.get(task_id)

    def list_tasks(self):
        return list(self._tasks.values())

    def transition(self, task_id, to_state, detail=""):
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        now = time.time()
        event = EventLog(timestamp=now, from_state=task.state, to_state=to_state.value, detail=detail)
        task.state = to_state.value
        task.updated_at = now
        task.events.append(asdict(event))
        self._save()

    def get_events(self, task_id):
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        return task.events

    def save_checkpoint(self, task_id, checkpoint):
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        task.checkpoint = checkpoint
        task.updated_at = time.time()
        self._save()

    def get_checkpoint(self, task_id):
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        return task.checkpoint

    def save_results(self, task_id, results):
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        task.results = results
        task.updated_at = time.time()
        self._save()

    def get_results(self, task_id):
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        return task.results

    def should_resume(self, task_id):
        task = self._tasks.get(task_id)
        if not task:
            return False
        return task.state == TaskState.INTERRUPTED.value and bool(task.checkpoint)

    def resume(self, task_id):
        if not self.should_resume(task_id):
            raise ValueError(f"Task {task_id} cannot resume")
        checkpoint = self.get_checkpoint(task_id)
        self.transition(task_id, TaskState.RUNNING, detail="Resumed from checkpoint")
        return checkpoint

    def is_completed(self, task_id):
        task = self._tasks.get(task_id)
        if not task:
            return False
        return task.state == TaskState.COMPLETED.value

    def can_retry(self, task_id):
        task = self._tasks.get(task_id)
        if not task:
            return False
        return task.state == TaskState.FAILED.value and not self.is_completed(task_id)

    def retry(self, task_id):
        if self.is_completed(task_id):
            return False
        if not self.can_retry(task_id):
            return False
        self.transition(task_id, TaskState.RUNNING, detail="Retry started")
        return True

    def interrupt(self, task_id, checkpoint):
        self.save_checkpoint(task_id, checkpoint)
        self.transition(task_id, TaskState.INTERRUPTED, detail="Task interrupted")

    def complete(self, task_id, results):
        self.save_results(task_id, results)
        self.transition(task_id, TaskState.COMPLETED, detail="Task completed")

    def fail(self, task_id, error=""):
        self.transition(task_id, TaskState.FAILED, detail=error)
