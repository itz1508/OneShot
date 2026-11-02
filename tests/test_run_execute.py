"""Run.execute() tests — parallel file-task scheduling + Build Admission."""

from __future__ import annotations

import threading
import time

import pytest

import agent
from agent.orchestration import PlannedFileOperation, RunPlan, Task


@pytest.fixture
def tm_snapshot(tmp_path):
    return str(tmp_path / "tasks.json")


@pytest.fixture
def three_file_plan():
    return RunPlan(
        plan_id="exec-plan-001",
        objective="exec three files",
        files=(
            PlannedFileOperation(path="a.py"),
            PlannedFileOperation(path="b.py"),
            PlannedFileOperation(path="c.py"),
        ),
    )


class TestExecuteHappyPath:
    def test_default_executor_completes_every_task(
        self, three_file_plan, tm_snapshot
    ):
        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        results = run.execute()
        assert set(results.values()) == {"completed"}
        for t in run.tasks:
            assert t.status() == "completed"
        assert run.status() == "completed"

    def test_build_admission_recorded_on_each_task(
        self, three_file_plan, tm_snapshot
    ):
        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        run.execute()
        tm = run._controller.tm
        for t in run.tasks:
            row = tm.get_task(t.task_id)
            admission = row.metadata["build_admission"]
            assert admission["outcome"] == "completed"
            assert admission["task_path"] == t.path
            assert admission["actor"] == "agent.orchestration"

    def test_custom_executor_sees_each_task(
        self, three_file_plan, tm_snapshot
    ):
        seen = []
        lock = threading.Lock()

        def executor(task: Task) -> None:
            with lock:
                seen.append(task.path)
            # Add a tiny sleep so parallelism is visible.
            time.sleep(0.01)

        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        run.execute(executor=executor, max_workers=3)
        assert sorted(seen) == ["a.py", "b.py", "c.py"]


class TestExecuteParallelism:
    def test_parallel_scheduling_beats_serial(self, tm_snapshot):
        """Four tasks sleeping 0.3s each: serial would be 1.2s; a pool
        of 4 workers must finish well under 1.0s."""
        files = tuple(
            PlannedFileOperation(path=f"{i}.py") for i in range(4)
        )
        plan = RunPlan(plan_id="par-01", objective="par", files=files)
        run = agent.start(plan, storage_path=tm_snapshot)

        def slow(task: Task) -> None:
            time.sleep(0.3)

        t0 = time.monotonic()
        results = run.execute(executor=slow, max_workers=4)
        elapsed = time.monotonic() - t0
        assert set(results.values()) == {"completed"}
        assert elapsed < 1.0, (
            f"parallel execute took {elapsed:.3f}s; expected < 1.0s "
            "(serial would be ~1.2s)"
        )


class TestExecuteFailurePath:
    def test_executor_exception_marks_task_failed(
        self, three_file_plan, tm_snapshot
    ):
        run = agent.start(three_file_plan, storage_path=tm_snapshot)

        def executor(task: Task) -> None:
            if task.path == "b.py":
                raise RuntimeError("boom")

        results = run.execute(executor=executor)
        assert results == {
            run.tasks[0].task_id: "completed",
            run.tasks[1].task_id: "failed",
            run.tasks[2].task_id: "completed",
        }
        # The run-level status prefers "failed" when any task failed.
        assert run.status() == "failed"
        # Build admission on the failed task records the exception class.
        row = run._controller.tm.get_task(run.tasks[1].task_id)
        admission = row.metadata["build_admission"]
        assert admission["outcome"] == "failed"
        assert admission["error_class"] == "RuntimeError"


class TestExecuteLifecycleInteractions:
    def test_execute_on_paused_run_is_noop(
        self, three_file_plan, tm_snapshot
    ):
        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        run.pause()
        results = run.execute()
        # Every task reports paused, nothing was executed.
        for _task_id, status in results.items():
            assert status == "paused"
        for t in run.tasks:
            assert t.status() == "paused"
        run.resume()
        # After resume, a fresh execute completes everything.
        results2 = run.execute()
        assert set(results2.values()) == {"completed"}

    def test_timeout_marks_slow_tasks_failed(self, tm_snapshot):
        files = tuple(
            PlannedFileOperation(path=f"{i}.py") for i in range(4)
        )
        plan = RunPlan(plan_id="timeout-01", objective="t", files=files)
        run = agent.start(plan, storage_path=tm_snapshot)

        def slow(task: Task) -> None:
            time.sleep(2.0)

        results = run.execute(executor=slow, max_workers=4, timeout_s=0.2)
        # At least one task should be failed with TimeoutError admission.
        failed = [k for k, v in results.items() if v == "failed"]
        assert failed, f"expected at least one timeout failure, got {results}"
