"""Public ``agent.start`` / ``Run`` / ``Task`` API tests.

The reviewer-approved public API is minimal — these tests exercise
it against the real ``OneShotController`` + ``TaskManager`` (reused;
no new state owner, no mock) with a scratch snapshot per test. No
live providers are touched.
"""

from __future__ import annotations

import pytest

import agent
from agent.orchestration import (
    PlannedFileOperation,
    Run,
    RunPlan,
    Task,
)

# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

@pytest.fixture
def tm_snapshot(tmp_path):
    return str(tmp_path / "tasks.json")


@pytest.fixture
def three_file_plan():
    return RunPlan(
        plan_id="plan-001",
        objective="Edit three files in sequence",
        files=(
            PlannedFileOperation(path="a.py", operation="edit", note="a"),
            PlannedFileOperation(path="b.py", operation="create", note="b"),
            PlannedFileOperation(path="c.py", operation="remove", note="c"),
        ),
    )


# ---------------------------------------------------------------------
# start() + Run basic contract
# ---------------------------------------------------------------------

class TestStartContract:
    def test_start_returns_run_with_matching_plan_id(
        self, three_file_plan, tm_snapshot
    ):
        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        assert isinstance(run, Run)
        assert run.plan_id == "plan-001"

    def test_start_accepts_mapping_shape(self, tm_snapshot):
        run = agent.start(
            {
                "plan_id": "plan-002",
                "objective": "Just one file",
                "files": [{"path": "x.py", "operation": "edit", "note": ""}],
            },
            storage_path=tm_snapshot,
        )
        assert run.plan_id == "plan-002"
        assert len(run.tasks) == 1
        assert run.tasks[0].path == "x.py"
        assert run.tasks[0].operation == "edit"

    def test_start_accepts_bare_string(self, tm_snapshot):
        run = agent.start("ping", storage_path=tm_snapshot)
        assert run.plan_id == "ping"
        assert run.tasks == ()
        # Status defaults to pending for an empty plan.
        assert run.status() == "pending"

    def test_start_rejects_other_types(self):
        with pytest.raises(TypeError, match="plan_id must be"):
            agent.start(42)  # type: ignore[arg-type]

    def test_start_rejects_empty_plan_id(self, tm_snapshot):
        with pytest.raises(Exception):  # noqa: B017 - Pydantic ValidationError
            agent.start(
                {
                    "plan_id": "   ",
                    "objective": "x",
                    "files": [],
                },
                storage_path=tm_snapshot,
            )


# ---------------------------------------------------------------------
# One Task per planned file, in plan order
# ---------------------------------------------------------------------

class TestTaskIteration:
    def test_tasks_mirror_planned_files_in_order(
        self, three_file_plan, tm_snapshot
    ):
        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        assert [t.path for t in run.tasks] == ["a.py", "b.py", "c.py"]
        assert [t.operation for t in run.tasks] == ["edit", "create", "remove"]

    def test_each_task_is_a_distinct_task_manager_row(
        self, three_file_plan, tm_snapshot
    ):
        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        task_ids = [t.task_id for t in run.tasks]
        assert len(set(task_ids)) == len(task_ids)
        # Each one is a real task on TaskManager.
        tm = run._controller.tm
        for t in run.tasks:
            row = tm.get_task(t.task_id)
            assert row is not None
            assert row.metadata["plan_id"] == "plan-001"
            assert row.metadata["file_path"] == t.path
            assert row.metadata["operation"] == t.operation

    def test_task_status_reads_task_manager(
        self, three_file_plan, tm_snapshot
    ):
        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        # Initial state in TaskManager is pending.
        for t in run.tasks:
            assert t.status() == "pending"
        # Promote one to running directly on the TaskManager.
        tm = run._controller.tm
        tm.transition(run.tasks[0].task_id, "running", detail="x")
        assert run.tasks[0].status() == "running"
        tm.transition(run.tasks[0].task_id, "completed", detail="y")
        assert run.tasks[0].status() == "completed"


# ---------------------------------------------------------------------
# pause / resume lifecycle
# ---------------------------------------------------------------------

class TestLifecycle:
    def test_pause_reports_paused_status(self, three_file_plan, tm_snapshot):
        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        assert run.status() == "pending"
        run.pause()
        assert run.paused is True
        assert run.status() == "paused"
        # Child tasks also report paused while the run is paused.
        for t in run.tasks:
            assert t.status() == "paused"

    def test_resume_clears_pause(self, three_file_plan, tm_snapshot):
        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        run.pause()
        run.resume()
        assert run.paused is False
        assert run.status() == "pending"
        for t in run.tasks:
            assert t.status() == "pending"

    def test_pause_idempotent(self, three_file_plan, tm_snapshot):
        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        run.pause()
        run.pause()
        assert run.paused is True

    def test_resume_idempotent(self, three_file_plan, tm_snapshot):
        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        run.resume()  # not paused — no-op
        assert run.paused is False

    def test_terminal_task_states_beat_pause(
        self, three_file_plan, tm_snapshot
    ):
        """A completed/failed task reports its terminal state even if
        the Run is currently paused — pausing does not retroactively
        hide outcomes."""
        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        tm = run._controller.tm
        tm.transition(run.tasks[0].task_id, "running", detail="x")
        tm.transition(run.tasks[0].task_id, "completed", detail="y")
        tm.transition(run.tasks[1].task_id, "running", detail="x")
        tm.transition(run.tasks[1].task_id, "failed", detail="boom")
        run.pause()
        assert run.tasks[0].status() == "completed"
        assert run.tasks[1].status() == "failed"
        assert run.tasks[2].status() == "paused"
        # Overall run status reports paused (pause flag beats aggregate).
        assert run.status() == "paused"


# ---------------------------------------------------------------------
# Aggregate status derivation (unpaused)
# ---------------------------------------------------------------------

class TestAggregateStatus:
    def test_all_completed(self, three_file_plan, tm_snapshot):
        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        tm = run._controller.tm
        for t in run.tasks:
            tm.transition(t.task_id, "running", detail="x")
            tm.transition(t.task_id, "completed", detail="y")
        assert run.status() == "completed"

    def test_any_failed_wins(self, three_file_plan, tm_snapshot):
        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        tm = run._controller.tm
        tm.transition(run.tasks[0].task_id, "running", detail="x")
        tm.transition(run.tasks[0].task_id, "completed", detail="y")
        tm.transition(run.tasks[1].task_id, "running", detail="x")
        tm.transition(run.tasks[1].task_id, "failed", detail="boom")
        assert run.status() == "failed"

    def test_any_running_without_failure(self, three_file_plan, tm_snapshot):
        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        tm = run._controller.tm
        tm.transition(run.tasks[0].task_id, "running", detail="x")
        assert run.status() == "running"


# ---------------------------------------------------------------------
# get_run lookup
# ---------------------------------------------------------------------

class TestGetRun:
    def test_get_run_returns_same_instance(
        self, three_file_plan, tm_snapshot
    ):
        run = agent.start(three_file_plan, storage_path=tm_snapshot)
        got = agent.get_run("plan-001")
        assert got is run

    def test_get_run_returns_none_for_unknown_id(self):
        assert agent.get_run("made-up-id") is None


# ---------------------------------------------------------------------
# Module-level exports
# ---------------------------------------------------------------------

class TestPublicSurface:
    def test_agent_module_exposes_the_promised_names(self):
        for name in ("start", "Run", "Task", "RunPlan", "PlannedFileOperation", "get_run"):
            assert hasattr(agent, name), f"agent.{name} missing"

    def test_task_is_the_planned_file_type(self):
        assert Task.__name__ == "Task"
        # Task carries path + operation (one planned file operation).
        import dataclasses
        fields = {f.name for f in dataclasses.fields(Task)}
        assert {"path", "operation", "task_id"}.issubset(fields)
