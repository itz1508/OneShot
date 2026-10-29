#!/usr/bin/env python3
"""Tests for Memory Retrieval — Research-side retrieval using TaskManager."""
import os, sys, tempfile
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from task_management import TaskManager, TaskState
from memory_retrieve import MemoryRetriever


class TestMemoryRetrieve:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = os.path.join(self.tmpdir, "test_mem.json")
        self.tm = TaskManager(storage_path=self.storage)
        self.retriever = MemoryRetriever(self.tm)

    def teardown_method(self):
        if os.path.exists(self.storage): os.remove(self.storage)
        os.rmdir(self.tmpdir)

    def test_retrieve_task(self):
        task = self.tm.create_task()
        retrieved = self.retriever.retrieve_task(task.task_id)
        assert retrieved is not None
        assert retrieved.task_id == task.task_id

    def test_retrieve_by_state(self):
        t1 = self.tm.create_task()
        t2 = self.tm.create_task()
        self.tm.transition(t2.task_id, TaskState.RUNNING, "Started")
        running = self.retriever.retrieve_by_state(TaskState.RUNNING)
        pending = self.retriever.retrieve_by_state(TaskState.PENDING)
        assert len(running) == 1
        assert len(pending) == 1

    def test_retrieve_completed_and_failed(self):
        t1 = self.tm.create_task()
        t2 = self.tm.create_task()
        self.tm.transition(t2.task_id, TaskState.RUNNING, "Started")
        self.tm.fail(t2.task_id, "Error")
        self.retriever = MemoryRetriever(self.tm)
        self.tm.complete(t1.task_id, {"result": "ok"})
        completed = self.retriever.retrieve_completed()
        failed = self.retriever.retrieve_failed()
        assert len(completed) == 1
        assert len(failed) == 1

    def test_resume_from_checkpoint(self):
        task = self.tm.create_task()
        self.tm.transition(task.task_id, TaskState.RUNNING, "Started")
        self.tm.interrupt(task.task_id, {"step": "research"})
        assert self.retriever.should_resume(task.task_id)
        ckpt = self.retriever.resume_from_checkpoint(task.task_id)
        assert ckpt["step"] == "research"

    def test_no_duplicate_execution(self):
        task = self.tm.create_task()
        self.tm.complete(task.task_id, {"result": "done"})
        assert self.retriever.is_already_executed(task.task_id)
        assert not self.retriever.retry_task(task.task_id)

    def test_retry_failed_task(self):
        task = self.tm.create_task()
        self.tm.transition(task.task_id, TaskState.RUNNING, "Started")
        self.tm.fail(task.task_id, "Error")
        assert self.retriever.can_retry(task.task_id)
        assert self.retriever.retry_task(task.task_id)
