"""TASK-02: crash-safe recovery — interruption, restart, reconcile, retry, replay.

Recovery dispositions (existing host mechanisms only):
- NO_WORK: checkpoint exists, no assignment yet → assign work.
- RETRY_WORK: interrupted TODO (pending/running/blocked/failed/stale) → finish
  work, never transition.
- READY_TO_ADVANCE: completed TODO persisted → explicit bound receipt + advance
  still required; recovery never auto-advances.
- CONTRADICTORY/BLOCKED: task/run mismatch or unverifiable state → fail closed.
"""

from __future__ import annotations

import pytest

from agent.contracts.host import ReceiptRef
from agent.contracts.work_todo import WorkStatus
from agent.runtime.controller import (
    HostController,
    Stage,
    TaskRecovery,
    TaskRecoveryDisposition,
    TransitionError,
)
from tests.e2e.test_work_todo import binding, run_action


def test_recover_no_work_before_assignment(tmp_path) -> None:
    controller = HostController(tmp_path / "state")
    controller.init_task("task-001", "run-001")
    recovery = controller.recover_task("task-001", "run-001")
    assert recovery.disposition is TaskRecoveryDisposition.NO_WORK
    assert recovery.checkpoint_revision == 1
    assert recovery.work_ref is None


def test_recover_retry_after_running_interruption(tmp_path) -> None:
    controller = HostController(tmp_path / "state")
    controller.init_task("real-work", "run-real")
    scope = binding(controller, "research", "research-1")
    _, pending = controller.assign_work(scope, action="Gather", expected_result="Evidence")
    _, running = controller.work_todos.set_status(pending, "work-1", WorkStatus.RUNNING)
    # Simulate process death: new controller on the same state.
    restarted = HostController(tmp_path / "state")
    recovery = restarted.recover_task("real-work", "run-real")
    assert recovery.disposition is TaskRecoveryDisposition.RETRY_WORK
    assert recovery.work_ref is not None
    assert recovery.work_ref.artifact_revision == running.artifact_revision
    assert recovery.work_ref.artifact_digest == running.artifact_digest


def test_recover_ready_after_completed_work(tmp_path) -> None:
    controller = HostController(tmp_path / "state")
    controller.init_task("real-work", "run-real")
    scope = binding(controller, "research", "research-1")
    _, pending = controller.assign_work(scope, action="Gather", expected_result="Evidence")
    completed = run_action(controller, pending, "work-1", "observed")
    restarted = HostController(tmp_path / "state")
    recovery = restarted.recover_task("real-work", "run-real")
    assert recovery.disposition is TaskRecoveryDisposition.READY_TO_ADVANCE
    assert recovery.work_ref is not None
    assert recovery.work_ref == completed
    # Recovery never auto-advances: explicit bound receipt + transition required.
    receipt = restarted.issue_stage_receipt(
        Stage.RESEARCH,
        task_id="real-work",
        run_id="run-real",
        revision=recovery.work_ref.artifact_revision,
        artifact_digest=recovery.work_ref.artifact_digest,
        todo_ref=recovery.work_ref,
    )
    state = restarted.advance_stage("real-work", "run-real", Stage.RESEARCH, receipt, todo_ref=recovery.work_ref)
    assert state.current_stage is Stage.AUDIT_DISCOVERY


def test_recover_contradictory_run_rejected(tmp_path) -> None:
    controller = HostController(tmp_path / "state")
    controller.init_task("real-work", "run-real")
    scope = binding(controller, "research", "research-1")
    controller.assign_work(scope, action="Gather", expected_result="Evidence")
    restarted = HostController(tmp_path / "state")
    recovery = restarted.recover_task("real-work", "run-other")
    assert recovery.disposition is TaskRecoveryDisposition.CONTRADICTORY
    # A stale worker with the wrong run cannot commit a transition.
    with pytest.raises(TransitionError, match=r"task/run binding mismatch|task/run mismatch"):
        restarted.advance_stage(
            "real-work",
            "run-other",
            Stage.RESEARCH,
            ReceiptRef(receipt_id="receipt-x", receipt_digest="0" * 64, issuer_id="host"),
        )


def test_recover_does_not_double_transition(tmp_path) -> None:
    controller = HostController(tmp_path / "state")
    controller.init_task("real-work", "run-real")
    scope = binding(controller, "research", "research-1")
    _, pending = controller.assign_work(scope, action="Gather", expected_result="Evidence")
    completed = run_action(controller, pending, "work-1", "observed")
    receipt = controller.issue_stage_receipt(
        Stage.RESEARCH,
        task_id="real-work",
        run_id="run-real",
        revision=completed.artifact_revision,
        artifact_digest=completed.artifact_digest,
        todo_ref=completed,
    )
    controller.advance_stage("real-work", "run-real", Stage.RESEARCH, receipt, todo_ref=completed)
    restarted = HostController(tmp_path / "state")
    recovery = restarted.recover_task("real-work", "run-real")
    # After the transition, audit-discovery has no work yet — no replay of research.
    assert recovery.stage is Stage.AUDIT_DISCOVERY
    assert recovery.disposition is TaskRecoveryDisposition.NO_WORK
    with pytest.raises(TransitionError, match=r"expected stage|already|not at"):
        restarted.advance_stage("real-work", "run-real", Stage.RESEARCH, receipt, todo_ref=completed)


def test_recover_preserves_task_run_identity(tmp_path) -> None:
    controller = HostController(tmp_path / "state")
    controller.init_task("real-work", "run-real")
    scope = binding(controller, "research", "research-1")
    _, pending = controller.assign_work(scope, action="Gather", expected_result="Evidence")
    completed = run_action(controller, pending, "work-1", "observed")
    recovery = HostController(tmp_path / "state").recover_task("real-work", "run-real")
    assert isinstance(recovery, TaskRecovery)
    assert (recovery.task_id, recovery.run_id) == ("real-work", "run-real")
    assert recovery.work_ref == completed
