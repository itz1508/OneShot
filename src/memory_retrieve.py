#!/usr/bin/env python3
"""
OneShot Assignment 01b: Memory Retrieval (Research-side)

Memory is initialized at agent startup via TaskManager. Research performs
task-relevant retrieval from available memory. This module does NOT own
task identity, state, persistence, or recovery — that is TaskManager's job.
"""

from typing import Optional, List
from task_management import TaskManager, TaskState, TaskRecord


class MemoryRetriever:
    """Research-side retrieval. Uses TaskManager, does not own it."""

    def __init__(self, task_manager: TaskManager):
        self.tm = task_manager

    def retrieve_task(self, task_id: str) -> Optional[TaskRecord]:
        return self.tm.get_task(task_id)

    def retrieve_by_state(self, state: TaskState) -> List[TaskRecord]:
        return [t for t in self.tm.list_tasks() if t.state == state.value]

    def retrieve_completed(self) -> List[TaskRecord]:
        return self.retrieve_by_state(TaskState.COMPLETED)

    def retrieve_failed(self) -> List[TaskRecord]:
        return self.retrieve_by_state(TaskState.FAILED)

    def should_resume(self, task_id: str) -> bool:
        return self.tm.should_resume(task_id)

    def resume_from_checkpoint(self, task_id: str) -> dict:
        return self.tm.resume(task_id)

    def is_already_executed(self, task_id: str) -> bool:
        return self.tm.is_completed(task_id)

    def can_retry(self, task_id: str) -> bool:
        return self.tm.can_retry(task_id)

    def retry_task(self, task_id: str) -> bool:
        return self.tm.retry(task_id)
