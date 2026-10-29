#!/usr/bin/env python3
"""
OneShot Assignment 01: Memory Retrieval

Memory is initialized and available whenever an agent starts. Research performs
task-relevant retrieval from available memory. This module builds the retrieval
capability — initialization and persistence are agent startup's job, not Research's.

Supports restart, resume, retry, and prevents duplicated execution using
existing infrastructure.

Usage:
    from memory_retrieve import MemoryStore, MemoryRetriever
"""

import json
import os
import time
import uuid
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
from typing import Optional, Any


class TaskState(str, Enum):
    """Execution state for a task."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass
class TaskRecord:
    """A single task record in memory."""
    task_id: str
    state: str
    created_at: float
    updated_at: float
    events: list = field(default_factory=list)
    results: dict = field(default_factory=dict)
    checkpoint: dict = field(default_factory=dict)


@dataclass
class EventLog:
    """A state transition event."""
    timestamp: float
    from_state: str
    to_state: str
    detail: str = ""


class MemoryStore:
    """
    In-memory store backed by a JSON file for persistence.

    Memory is initialized at agent startup. This store handles persistence
    using existing infrastructure (file-based). It does NOT mandate specific
    persistence tools. Research retrieves from this store but does not own it.
    """

    def __init__(self, storage_path: Optional[str] = None):
        """Initialize with optional storage path (defaults to /tmp)."""
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            self.storage_path = Path("/tmp") / "oneshot_memory.json"

        self._tasks: dict[str, TaskRecord] = {}
        self._load()

    def _load(self):
        """Load persisted state from file."""
        if self.storage_path.exists():
            with open(self.storage_path, "r") as f:
                data = json.load(f)
                for tid, rec in data.items():
                    self._tasks[tid] = TaskRecord(**rec)

    def _save(self):
        """Persist state to file."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w") as f:
            data = {tid: asdict(rec) for tid, rec in self._tasks.items()}
            json.dump(data, f, indent=2)

    def create_task(self, task_id: Optional[str] = None) -> TaskRecord:
        """Create a new task with unique ID."""
        tid = task_id or str(uuid.uuid4())
        if tid in self._tasks:
            raise ValueError(f"Task {tid} already exists")

        now = time.time()
        record = TaskRecord(
            task_id=tid,
            state=TaskState.PENDING.value,
            created_at=now,
            updated_at=now,
            events=[asdict(EventLog(timestamp=now, from_state="", to_state=TaskState.PENDING.value, detail="Task created"))],
        )
        self._tasks[tid] = record
        self._save()
        return record

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        """Retrieve a task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[TaskRecord]:
        """List all tasks."""
        return list(self._tasks.values())

    def transition(self, task_id: str, to_state: TaskState, detail: str = ""):
        """Transition a task to a new state, logging the event."""
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")

        now = time.time()
        event = EventLog(
            timestamp=now,
            from_state=task.state,
            to_state=to_state.value,
            detail=detail,
        )
        task.state = to_state.value
        task.updated_at = now
        task.events.append(asdict(event))
        self._save()

    def save_checkpoint(self, task_id: str, checkpoint: dict):
        """Save a checkpoint for restart/resume."""
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        task.checkpoint = checkpoint
        task.updated_at = time.time()
        self._save()

    def get_checkpoint(self, task_id: str) -> dict:
        """Retrieve the last checkpoint for restart/resume."""
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        return task.checkpoint

    def save_results(self, task_id: str, results: dict):
        """Save task results."""
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        task.results = results
        task.updated_at = time.time()
        self._save()

    def get_results(self, task_id: str) -> dict:
        """Retrieve task results."""
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task {task_id} not found")
        return task.results


class MemoryRetriever:
    """
    Research-side retrieval capability.

    Research retrieves task-relevant records from available memory.
    Does NOT own memory initialization or persistence.
    Supports restart, resume, retry, and prevents duplicated execution.
    """

    def __init__(self, store: MemoryStore):
        self.store = store

    def retrieve_task(self, task_id: str) -> Optional[TaskRecord]:
        """Retrieve a task by ID from memory."""
        return self.store.get_task(task_id)

    def retrieve_by_state(self, state: TaskState) -> list[TaskRecord]:
        """Retrieve all tasks matching a state."""
        return [t for t in self.store.list_tasks() if t.state == state.value]

    def retrieve_completed(self) -> list[TaskRecord]:
        """Retrieve all completed tasks."""
        return self.retrieve_by_state(TaskState.COMPLETED)

    def retrieve_failed(self) -> list[TaskRecord]:
        """Retrieve all failed tasks for retry analysis."""
        return self.retrieve_by_state(TaskState.FAILED)

    def should_resume(self, task_id: str) -> bool:
        """Check if a task should resume from checkpoint (was interrupted)."""
        task = self.store.get_task(task_id)
        if not task:
            return False
        return task.state == TaskState.INTERRUPTED.value and bool(task.checkpoint)

    def resume_from_checkpoint(self, task_id: str) -> dict:
        """Resume a task from its last checkpoint."""
        if not self.should_resume(task_id):
            raise ValueError(f"Task {task_id} cannot resume (not interrupted or no checkpoint)")
        checkpoint = self.store.get_checkpoint(task_id)
        self.store.transition(task_id, TaskState.RUNNING, detail="Resumed from checkpoint")
        return checkpoint

    def is_already_executed(self, task_id: str) -> bool:
        """Check if a task was already executed (prevents duplicate execution)."""
        task = self.store.get_task(task_id)
        if not task:
            return False
        return task.state in (TaskState.COMPLETED.value,)

    def can_retry(self, task_id: str) -> bool:
        """Check if a failed task can be retried (not already completed)."""
        task = self.store.get_task(task_id)
        if not task:
            return False
        # Can retry if failed and not completed
        return task.state == TaskState.FAILED.value

    def retry_task(self, task_id: str) -> bool:
        """Retry a failed task. Returns True if retry started, False if duplicate."""
        if self.is_already_executed(task_id):
            return False  # No duplicate execution
        if not self.can_retry(task_id):
            return False
        self.store.transition(task_id, TaskState.RUNNING, detail="Retry started")
        return True

    def interrupt_task(self, task_id: str, checkpoint: dict):
        """Interrupt a running task and save checkpoint."""
        self.store.save_checkpoint(task_id, checkpoint)
        self.store.transition(task_id, TaskState.INTERRUPTED, detail="Task interrupted")

    def complete_task(self, task_id: str, results: dict):
        """Mark a task as completed and save results."""
        self.store.save_results(task_id, results)
        self.store.transition(task_id, TaskState.COMPLETED, detail="Task completed")
