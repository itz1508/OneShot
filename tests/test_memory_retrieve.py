#!/usr/bin/env python3
"""
Tests for OneShot Assignment 01: memory_retrieve.py

Verifies: create task, interrupt, restart, resume, retry, no-duplicate.
"""

import os
import sys
import tempfile
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from memory_retrieve import MemoryStore, MemoryRetriever, TaskState, TaskRecord


class TestMemoryRetrieve:
    """Contract and E2E tests for memory_retrieve.py."""

    def setup_method(self):
        """Use a temp file for each test to avoid state leakage."""
        self.tmpdir = tempfile.mkdtemp()
        self.storage_path = os.path.join(self.tmpdir, "test_memory.json")
        self.store = MemoryStore(storage_path=self.storage_path)
        self.retriever = MemoryRetriever(self.store)

    def teardown_method(self):
        if os.path.exists(self.storage_path):
            os.remove(self.storage_path)
        os.rmdir(self.tmpdir)

    def test_create_task_persists_with_unique_id(self):
        """Create task → verify task record persisted with unique ID."""
        task = self.store.create_task()
        assert task.task_id
        assert task.state == "pending"
        # Verify it's persisted
        store2 = MemoryStore(storage_path=self.storage_path)
        retrieved = store2.get_task(task.task_id)
        assert retrieved is not None
        assert retrieved.task_id == task.task_id

    def test_interrupt_and_restart_resumes_from_checkpoint(self):
        """Interrupt execution → restart → verify state resumed from last checkpoint."""
        task = self.store.create_task()
        self.store.transition(task.task_id, TaskState.RUNNING, "Started")
        self.retriever.interrupt_task(task.task_id, {"step": "research", "progress": 50})

        # Simulate restart with a fresh store loaded from disk
        store2 = MemoryStore(storage_path=self.storage_path)
        retriever2 = MemoryRetriever(store2)

        assert retriever2.should_resume(task.task_id)
        checkpoint = retriever2.resume_from_checkpoint(task.task_id)
        assert checkpoint["step"] == "research"
        assert checkpoint["progress"] == 50

        # Verify task is now running
        task2 = store2.get_task(task.task_id)
        assert task2.state == "running"

    def test_retry_failed_no_duplicate_execution(self):
        """Retry failed operation → verify no duplicate side effects."""
        task = self.store.create_task()
        self.store.transition(task.task_id, TaskState.RUNNING, "Started")
        self.store.transition(task.task_id, TaskState.FAILED, "Error occurred")

        # Retry should work
        assert self.retriever.can_retry(task.task_id)
        assert self.retriever.retry_task(task.task_id)

        # Complete the task
        self.retriever.complete_task(task.task_id, {"output": "done"})

        # Retry again should be blocked (no duplicate)
        assert not self.retriever.is_already_executed(task.task_id) or not self.retriever.can_retry(task.task_id)
        assert not self.retriever.retry_task(task.task_id)  # Already completed

    def test_query_status_returns_events_and_results(self):
        """Query task status → verify current state, events, and results returned."""
        task = self.store.create_task()
        self.store.transition(task.task_id, TaskState.RUNNING, "Started")
        self.retriever.complete_task(task.task_id, {"findings": ["finding1", "finding2"]})

        retrieved = self.retriever.retrieve_task(task.task_id)
        assert retrieved.state == "completed"
        assert len(retrieved.events) >= 3  # created, started, completed
        assert retrieved.results["findings"] == ["finding1", "finding2"]

    def test_retrieve_by_state_filters_correctly(self):
        """retrieve_by_state returns only tasks matching the state."""
        t1 = self.store.create_task()
        t2 = self.store.create_task()
        self.store.transition(t2.task_id, TaskState.RUNNING, "Started")

        running = self.retriever.retrieve_by_state(TaskState.RUNNING)
        pending = self.retriever.retrieve_by_state(TaskState.PENDING)

        assert len(running) == 1
        assert len(pending) == 1
        assert running[0].task_id == t2.task_id
        assert pending[0].task_id == t1.task_id

    def test_retrieve_completed_and_failed(self):
        """retrieve_completed and retrieve_failed return correct tasks."""
        t1 = self.store.create_task()
        t2 = self.store.create_task()
        t3 = self.store.create_task()

        self.retriever.complete_task(t1.task_id, {"result": "ok"})
        self.store.transition(t2.task_id, TaskState.RUNNING, "Started")
        self.store.transition(t2.task_id, TaskState.FAILED, "Error")

        completed = self.retriever.retrieve_completed()
        failed = self.retriever.retrieve_failed()

        assert len(completed) == 1
        assert completed[0].task_id == t1.task_id
        assert len(failed) == 1
        assert failed[0].task_id == t2.task_id

    def test_persistence_across_restart(self):
        """Verify state persists across restart (new store loads from file)."""
        task = self.store.create_task()
        self.store.transition(task.task_id, TaskState.RUNNING, "Started")
        self.retriever.complete_task(task.task_id, {"data": "test"})

        # New store from same file
        store2 = MemoryStore(storage_path=self.storage_path)
        task2 = store2.get_task(task.task_id)
        assert task2 is not None
        assert task2.state == "completed"
        assert task2.results["data"] == "test"

    def test_checkpoint_preserved_on_interrupt(self):
        """Checkpoint data is preserved when task is interrupted."""
        task = self.store.create_task()
        self.store.transition(task.task_id, TaskState.RUNNING, "Started")

        checkpoint_data = {"completed_steps": ["step1", "step2"], "next_step": "step3"}
        self.retriever.interrupt_task(task.task_id, checkpoint_data)

        # Reload from disk
        store2 = MemoryStore(storage_path=self.storage_path)
        checkpoint = store2.get_checkpoint(task.task_id)
        assert checkpoint == checkpoint_data

    def test_event_log_tracks_all_transitions(self):
        """Event log records all state transitions with timestamps."""
        task = self.store.create_task()
        self.store.transition(task.task_id, TaskState.RUNNING, "Started")
        self.store.transition(task.task_id, TaskState.COMPLETED, "Done")

        retrieved = self.retriever.retrieve_task(task.task_id)
        assert len(retrieved.events) == 3  # created, started, completed
        # Verify timestamps are increasing
        timestamps = [e["timestamp"] for e in retrieved.events]
        assert timestamps == sorted(timestamps)

    def test_no_duplicate_execution_after_completion(self):
        """is_already_executed returns True for completed tasks."""
        task = self.store.create_task()
        self.retriever.complete_task(task.task_id, {"result": "done"})

        assert self.retriever.is_already_executed(task.task_id)
        assert not self.retriever.retry_task(task.task_id)  # No duplicate
