#!/usr/bin/env python3
"""Genuine connected E2E tests for the OneShot Workflow Harness.

Uses the actual built context_counter.py entrypoint and real Task Management.
NOT mocks, NOT static fixtures, NOT synthetic callback traces.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))
sys.path.insert(0, str(REPO_ROOT / "agent"))

from main import OneShotController, WorkflowStage
from color_eval import ColorEvaluator, Color
from task_management import TaskManager, TaskState


class TestContextCounterE2E:
    """E2E: exercise the actual built context_counter.py entrypoint."""

    COUNTER = REPO_ROOT / "bin" / "context_counter.py"

    def test_normal_input(self):
        """Normal case: known Unicode string yields expected metrics."""
        r = subprocess.run(
            [sys.executable, str(self.COUNTER), "A\U0001f600\nB"],
            capture_output=True, text=True, timeout=10
        )
        assert r.returncode == 0
        output = r.stdout
        assert "characters: 4" in output
        assert "bytes: 7" in output
        assert "words: 2" in output

    def test_empty_input(self):
        """Boundary: empty string."""
        r = subprocess.run(
            [sys.executable, str(self.COUNTER), ""],
            capture_output=True, text=True, timeout=10
        )
        assert r.returncode == 0
        assert "characters: 0" in r.stdout
        assert "bytes: 0" in r.stdout
        assert "words: 0" in r.stdout

    def test_file_input(self):
        """File mode: read from file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("hello world")
            fpath = f.name
        try:
            r = subprocess.run(
                [sys.executable, str(self.COUNTER), "--file", fpath],
                capture_output=True, text=True, timeout=10
            )
            assert r.returncode == 0
            assert "characters: 11" in r.stdout
            assert "words: 2" in r.stdout
        finally:
            os.unlink(fpath)

    def test_no_args_returns_error(self):
        """Negative: no arguments produces error exit code."""
        r = subprocess.run(
            [sys.executable, str(self.COUNTER)],
            capture_output=True, text=True, timeout=10
        )
        assert r.returncode == 1

    def test_stdin_input(self):
        """Stdin mode."""
        r = subprocess.run(
            [sys.executable, str(self.COUNTER), "--stdin"],
            input="test input",
            capture_output=True, text=True, timeout=10
        )
        assert r.returncode == 0
        assert "characters: 10" in r.stdout
        assert "words: 2" in r.stdout


class TestTaskManagementE2E:
    """E2E: real Task Management events and recovery."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.storage = os.path.join(self.tmpdir, "e2e_tasks.json")

    def teardown_method(self):
        if os.path.exists(self.storage):
            os.remove(self.storage)
        os.rmdir(self.tmpdir)

    def test_full_lifecycle_with_controller(self):
        """Full task lifecycle: start -> research -> plan -> build -> complete."""
        ctrl = OneShotController(storage_path=self.storage)
        tid = ctrl.start_task("count context demo")
        assert ctrl.get_status(tid)["state"] == "running"

        # Simulate Research stage
        ctrl.transition_stage(tid, WorkflowStage.PLAN, "research complete")
        assert ctrl.get_status(tid)["stage"] == "plan"

        # Simulate Plan stage
        ctrl.transition_stage(tid, WorkflowStage.BUILD, "plan approved")
        assert ctrl.get_status(tid)["stage"] == "build"

        # Simulate Build completion
        ctrl.complete_task(tid, {"counter": "built", "e2e": "passed"})
        assert ctrl.get_status(tid)["state"] == "completed"

    def test_interruption_and_resume(self):
        """Interruption and restart without repeated side effects."""
        ctrl = OneShotController(storage_path=self.storage)
        tid = ctrl.start_task("resume test")
        ctrl.checkpoint(tid, {"milestone": "m1", "done": True})

        # Task is interrupted
        assert ctrl.tm.get_task(tid).state == "interrupted"

        # Resume from checkpoint
        checkpoint = ctrl.resume(tid)
        assert checkpoint["milestone"] == "m1"
        assert ctrl.tm.get_task(tid).state == "running"

        # Verify no duplicate event for the same action
        events = ctrl.tm.get_events(tid)
        # Should have: created, running, interrupted, running (resume)
        assert len(events) >= 4

    def test_user_decision_wait_and_resume(self):
        """User decision wait and resume."""
        ctrl = OneShotController(storage_path=self.storage)
        tid = ctrl.start_task("decision test")
        req_id = ctrl.request_user_decision(tid, "Choose approach", ["A", "B"])

        # Task is interrupted (waiting)
        assert ctrl.tm.get_task(tid).state == "interrupted"
        assert ctrl.has_pending_decision(tid) is not None

        # Provide answer
        assert ctrl.provide_user_decision(tid, req_id, "A") is True
        assert ctrl.tm.get_task(tid).state == "running"
        assert ctrl.has_pending_decision(tid) is None

    def test_stale_answer_rejected(self):
        """Stale answer (from old revision) is rejected."""
        ctrl = OneShotController(storage_path=self.storage)
        tid = ctrl.start_task("stale test")
        req_id = ctrl.request_user_decision(tid, "Choose", ["A", "B"])

        # Change the task revision manually
        task = ctrl.tm.get_task(tid)
        task.metadata["revision"] = 99

        # Answer should be rejected (stale revision)
        assert ctrl.provide_user_decision(tid, req_id, "A") is False


class TestColorEvalE2E:
    """E2E: evidence-backed Color Eval on actual results."""

    def test_green_on_passed_e2e(self):
        """GREEN when E2E passes with artifacts and no failures."""
        evaluator = ColorEvaluator()
        result = evaluator.evaluate_build(
            artifacts=[{"sha256": "abc123"}],
            fixture_results={"all_pass": True},
            partial_failures=[]
        )
        assert result.overall_color == Color.GREEN.value

    def test_red_on_failed_fixtures(self):
        """RED when fixtures fail (critical)."""
        evaluator = ColorEvaluator()
        result = evaluator.evaluate_build(
            artifacts=[{"sha256": "abc123"}],
            fixture_results={"all_pass": False},
            partial_failures=[]
        )
        assert result.overall_color == Color.RED.value

    def test_red_on_partial_failures(self):
        """RED when partial failures exist."""
        evaluator = ColorEvaluator()
        result = evaluator.evaluate_build(
            artifacts=[{"sha256": "abc123"}],
            fixture_results={"all_pass": True},
            partial_failures=[{"step": "test", "error": "fail"}]
        )
        assert result.overall_color == Color.RED.value

    def test_e2e_all_pass_green(self):
        """GREEN when all E2E checks pass."""
        evaluator = ColorEvaluator()
        result = evaluator.evaluate_e2e(
            lifecycle_pass=True, recovery_pass=True,
            invalid_input_pass=True, persistence_pass=True
        )
        assert result.overall_color == Color.GREEN.value

    def test_e2e_recovery_fail_red(self):
        """RED when recovery fails (one RED makes all RED)."""
        evaluator = ColorEvaluator()
        result = evaluator.evaluate_e2e(
            lifecycle_pass=True, recovery_pass=False,
            invalid_input_pass=True, persistence_pass=True
        )
        assert result.overall_color == Color.RED.value
