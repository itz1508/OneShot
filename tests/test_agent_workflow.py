#!/usr/bin/env python3
"""Tests for the OneShot controller — task continuity, registry, user decisions."""

import os
import tempfile

import pytest
from main import CapabilityDescriptor, CapabilityRegistry, OneShotController, WorkflowStage


class TestTaskLifecycle:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = os.path.join(self.tmpdir, "test_controller.json")
        self.ctrl = OneShotController(storage_path=self.storage)

    def teardown_method(self):
        if os.path.exists(self.storage):
            os.remove(self.storage)
        os.rmdir(self.tmpdir)

    def test_start_task_returns_id(self):
        tid = self.ctrl.start_task("request.txt")
        assert tid
        status = self.ctrl.get_status(tid)
        assert status["state"] == "running"
        assert status["stage"] == "research"

    def test_status_nonexistent_task(self):
        status = self.ctrl.get_status("nonexistent")
        assert "error" in status

    def test_list_tasks(self):
        self.ctrl.start_task("req1")
        self.ctrl.start_task("req2")
        tasks = self.ctrl.list_tasks()
        assert len(tasks) == 2

    def test_complete_task(self):
        tid = self.ctrl.start_task("req")
        self.ctrl.complete_task(tid, {"result": "done"})
        status = self.ctrl.get_status(tid)
        assert status["state"] == "completed"
        assert status["results"]["result"] == "done"

    def test_fail_task(self):
        tid = self.ctrl.start_task("req")
        self.ctrl.fail_task(tid, "something broke")
        status = self.ctrl.get_status(tid)
        assert status["state"] == "failed"


class TestStageTransitions:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = os.path.join(self.tmpdir, "test_stages.json")
        self.ctrl = OneShotController(storage_path=self.storage)

    def teardown_method(self):
        if os.path.exists(self.storage):
            os.remove(self.storage)
        os.rmdir(self.tmpdir)

    def test_transition_to_plan(self):
        tid = self.ctrl.start_task("req")
        self.ctrl.transition_stage(tid, WorkflowStage.PLAN, "research done")
        status = self.ctrl.get_status(tid)
        assert status["stage"] == "plan"
        assert status["checkpoint"]["stage"] == "plan"

    def test_transition_to_build(self):
        tid = self.ctrl.start_task("req")
        self.ctrl.transition_stage(tid, WorkflowStage.PLAN, "research done")
        self.ctrl.transition_stage(tid, WorkflowStage.BUILD, "plan done")
        status = self.ctrl.get_status(tid)
        assert status["stage"] == "build"

    def test_event_ordering(self):
        tid = self.ctrl.start_task("req")
        self.ctrl.transition_stage(tid, WorkflowStage.PLAN, "step1")
        self.ctrl.transition_stage(tid, WorkflowStage.BUILD, "step2")
        status = self.ctrl.get_status(tid)
        events = status.get("events", None)
        # Get events from TaskManager directly
        events = self.ctrl.tm.get_events(tid)
        assert len(events) >= 4  # created + running + 2 transitions
        # Verify timestamps are monotonic
        timestamps = [e["timestamp"] for e in events]
        assert timestamps == sorted(timestamps)


class TestUserDecisionWait:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = os.path.join(self.tmpdir, "test_decisions.json")
        self.ctrl = OneShotController(storage_path=self.storage)

    def teardown_method(self):
        if os.path.exists(self.storage):
            os.remove(self.storage)
        os.rmdir(self.tmpdir)

    def test_request_and_answer_decision(self):
        tid = self.ctrl.start_task("req")
        req_id = self.ctrl.request_user_decision(tid, "Choose A or B", ["A", "B"])
        assert self.ctrl.has_pending_decision(tid) is not None
        assert self.ctrl.provide_user_decision(tid, req_id, "A") is True
        assert self.ctrl.has_pending_decision(tid) is None

    def test_duplicate_answer_rejected(self):
        tid = self.ctrl.start_task("req")
        req_id = self.ctrl.request_user_decision(tid, "Choose", ["A", "B"])
        assert self.ctrl.provide_user_decision(tid, req_id, "A") is True
        assert self.ctrl.provide_user_decision(tid, req_id, "A") is False

    def test_invalid_answer_rejected(self):
        tid = self.ctrl.start_task("req")
        req_id = self.ctrl.request_user_decision(tid, "Choose A or B", ["A", "B"])
        assert self.ctrl.provide_user_decision(tid, req_id, "C") is False

    def test_wrong_task_answer_rejected(self):
        tid1 = self.ctrl.start_task("req1")
        tid2 = self.ctrl.start_task("req2")
        req_id = self.ctrl.request_user_decision(tid1, "Choose", ["A"])
        assert self.ctrl.provide_user_decision(tid2, req_id, "A") is False


class TestCheckpointResume:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = os.path.join(self.tmpdir, "test_resume.json")
        self.ctrl = OneShotController(storage_path=self.storage)

    def teardown_method(self):
        if os.path.exists(self.storage):
            os.remove(self.storage)
        os.rmdir(self.tmpdir)

    def test_checkpoint_and_resume(self):
        tid = self.ctrl.start_task("req")
        self.ctrl.checkpoint(tid, {"milestone": "m1", "progress": 50})
        assert self.ctrl.tm.should_resume(tid)
        checkpoint = self.ctrl.resume(tid)
        assert checkpoint["milestone"] == "m1"
        assert checkpoint["progress"] == 50

    def test_resume_not_interrupted(self):
        tid = self.ctrl.start_task("req")
        assert self.ctrl.resume(tid) is None

    def test_resume_preserves_task_id(self):
        tid = self.ctrl.start_task("req")
        self.ctrl.checkpoint(tid, {"data": "test"})
        self.ctrl.resume(tid)
        status = self.ctrl.get_status(tid)
        assert status["task_id"] == tid


class TestCapabilityRegistry:
    def test_default_capabilities_registered(self):
        ctrl = OneShotController.__new__(OneShotController)
        ctrl.registry = CapabilityRegistry()
        ctrl._register_default_capabilities()
        caps = ctrl.registry.list_capabilities()
        cap_ids = [c.id for c in caps]
        assert "text_metrics" in cap_ids
        assert "color_eval" in cap_ids
        assert "system_scanner" in cap_ids

    def test_duplicate_owner_rejected(self):
        reg = CapabilityRegistry()
        reg.register(
            CapabilityDescriptor(
                id="test", version="1", owner="a", invocation_paths=["read"], effects=["read"]
            )
        )
        with pytest.raises(ValueError, match="already owned"):
            reg.register(
                CapabilityDescriptor(
                    id="test", version="2", owner="b", invocation_paths=["read"], effects=["read"]
                )
            )

    def test_same_owner_reregister_ok(self):
        reg = CapabilityRegistry()
        reg.register(
            CapabilityDescriptor(
                id="test", version="1", owner="a", invocation_paths=["read"], effects=["read"]
            )
        )
        reg.register(
            CapabilityDescriptor(
                id="test", version="2", owner="a", invocation_paths=["read"], effects=["read"]
            )
        )

    def test_unavailable_capability_returns_none(self):
        reg = CapabilityRegistry()
        reg.register(
            CapabilityDescriptor(
                id="test",
                version="1",
                owner="a",
                invocation_paths=["read"],
                effects=["read"],
                available=False,
            )
        )
        assert reg.get("test") is None

    def test_check_effect(self):
        reg = CapabilityRegistry()
        reg.register(
            CapabilityDescriptor(
                id="test",
                version="1",
                owner="a",
                invocation_paths=["active"],
                effects=["read", "internal_write"],
            )
        )
        assert reg.check_effect("test", "read") is True
        assert reg.check_effect("test", "destructive") is False
        assert reg.check_effect("nonexistent", "read") is False
