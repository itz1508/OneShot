#!/usr/bin/env python3
"""Behavioral tests for task-level memory retrieval (TaskManager surface).

The retired tools/memory_retrieve.py MemoryRetriever was a thin wrapper over
TaskManager — every method forwarded to a TaskManager method under a
slightly different name. The current source already exposes the same
behavior directly on TaskManager, so this file was migrated to exercise
TaskManager rather than restore the wrapper.

Mapping:
    retrieve_task(id)              → tm.get_task(id)
    retrieve_by_state(state)       → [t for t in tm.list_tasks() if t.state == state.value]
    retrieve_completed()           → list filter (TaskState.COMPLETED)
    retrieve_failed()              → list filter (TaskState.FAILED)
    should_resume(id)              → tm.should_resume(id)
    resume_from_checkpoint(id)     → tm.resume(id)
    is_already_executed(id)        → tm.is_completed(id)
    can_retry(id)                  → tm.can_retry(id)
    retry_task(id)                 → tm.retry(id)
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

# conftest.py puts tools/ on sys.path.
from task_management import TaskManager, TaskState


class TestTaskMemory(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.storage = os.path.join(self.tmpdir, "test_mem.json")
        self.tm = TaskManager(storage_path=self.storage)

    def tearDown(self) -> None:
        if os.path.exists(self.storage):
            os.remove(self.storage)
        os.rmdir(self.tmpdir)

    def _by_state(self, state: TaskState):
        return [t for t in self.tm.list_tasks() if t.state == state.value]

    def test_get_task(self):
        task = self.tm.create_task()
        self.assertIsNotNone(self.tm.get_task(task.task_id))
        self.assertEqual(self.tm.get_task(task.task_id).task_id, task.task_id)

    def test_list_by_state(self):
        self.tm.create_task()
        t2 = self.tm.create_task()
        self.tm.transition(t2.task_id, TaskState.RUNNING, "Started")
        self.assertEqual(len(self._by_state(TaskState.RUNNING)), 1)
        self.assertEqual(len(self._by_state(TaskState.PENDING)), 1)

    def test_completed_and_failed_filters(self):
        t1 = self.tm.create_task()
        t2 = self.tm.create_task()
        self.tm.transition(t2.task_id, TaskState.RUNNING, "Started")
        self.tm.fail(t2.task_id, "Error")
        self.tm.complete(t1.task_id, {"result": "ok"})
        self.assertEqual(len(self._by_state(TaskState.COMPLETED)), 1)
        self.assertEqual(len(self._by_state(TaskState.FAILED)), 1)

    def test_resume_from_checkpoint(self):
        task = self.tm.create_task()
        self.tm.transition(task.task_id, TaskState.RUNNING, "Started")
        self.tm.interrupt(task.task_id, {"step": "research"})
        self.assertTrue(self.tm.should_resume(task.task_id))
        ckpt = self.tm.resume(task.task_id)
        self.assertEqual(ckpt["step"], "research")

    def test_no_duplicate_execution(self):
        task = self.tm.create_task()
        self.tm.complete(task.task_id, {"result": "done"})
        self.assertTrue(self.tm.is_completed(task.task_id))
        # Already-completed task cannot be retried.
        self.assertFalse(self.tm.retry(task.task_id))

    def test_retry_failed_task(self):
        task = self.tm.create_task()
        self.tm.transition(task.task_id, TaskState.RUNNING, "Started")
        self.tm.fail(task.task_id, "Error")
        self.assertTrue(self.tm.can_retry(task.task_id))
        self.assertTrue(self.tm.retry(task.task_id))


if __name__ == "__main__":
    unittest.main()
