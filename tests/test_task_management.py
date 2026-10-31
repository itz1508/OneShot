#!/usr/bin/env python3
"""Tests for Task Management — shared identity, state, events, persistence, recovery."""

import os
import tempfile

from task_management import TaskManager, TaskState


class TestTaskManagement:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = os.path.join(self.tmpdir, "test_tm.json")
        self.tm = TaskManager(storage_path=self.storage)

    def teardown_method(self):
        if os.path.exists(self.storage):
            os.remove(self.storage)
        os.rmdir(self.tmpdir)

    def test_create_task_unique_id(self):
        task = self.tm.create_task()
        assert task.task_id
        assert task.state == "pending"
        assert len(task.events) == 1

    def test_persist_across_restart(self):
        task = self.tm.create_task()
        self.tm.transition(task.task_id, TaskState.RUNNING, "Started")
        tm2 = TaskManager(storage_path=self.storage)
        t2 = tm2.get_task(task.task_id)
        assert t2.state == "running"

    def test_interrupt_resume_from_checkpoint(self):
        task = self.tm.create_task()
        self.tm.transition(task.task_id, TaskState.RUNNING, "Started")
        self.tm.interrupt(task.task_id, {"step": "research", "progress": 50})
        tm2 = TaskManager(storage_path=self.storage)
        assert tm2.should_resume(task.task_id)
        ckpt = tm2.resume(task.task_id)
        assert ckpt["step"] == "research"

    def test_retry_no_duplicate(self):
        task = self.tm.create_task()
        self.tm.transition(task.task_id, TaskState.RUNNING, "Started")
        self.tm.fail(task.task_id, "Error")
        assert self.tm.can_retry(task.task_id)
        assert self.tm.retry(task.task_id)
        self.tm.complete(task.task_id, {"result": "done"})
        assert not self.tm.retry(task.task_id)  # No duplicate

    def test_event_log_tracks_transitions(self):
        task = self.tm.create_task()
        self.tm.transition(task.task_id, TaskState.RUNNING, "Started")
        self.tm.complete(task.task_id, {"result": "ok"})
        events = self.tm.get_events(task.task_id)
        assert len(events) == 3  # created, started, completed

    def test_results_persisted(self):
        task = self.tm.create_task()
        self.tm.complete(task.task_id, {"findings": ["f1", "f2"]})
        tm2 = TaskManager(storage_path=self.storage)
        assert tm2.get_results(task.task_id)["findings"] == ["f1", "f2"]
