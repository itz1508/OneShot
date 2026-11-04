"""TASK-01: Host stage receipts bind the exact verified artifact."""

from __future__ import annotations

import pytest

from agent.contracts.host import ReceiptRef, stage_receipt_id, stage_receipt_subject
from agent.runtime.controller import HostController, Stage, TransitionError
from tests.e2e.test_real_workflow import _completed_work_todo


def _issue(controller: HostController, task_id: str, run_id: str, stage: Stage):
    todo_ref = _completed_work_todo(controller, task_id, run_id, stage)
    receipt = controller.issue_stage_receipt(
        stage,
        task_id=task_id,
        run_id=run_id,
        revision=todo_ref.artifact_revision,
        artifact_digest=todo_ref.artifact_digest,
        todo_ref=todo_ref,
    )
    return todo_ref, receipt


def test_subject_and_id_bind_revision_and_digest() -> None:
    subject = stage_receipt_subject("t", "r", "research", 3, "a" * 64)
    assert subject == f"stage_complete:t:r:research:3:{'a' * 64}"
    receipt_id = stage_receipt_id("t", "r", "research", 3, "a" * 64)
    assert "3" in receipt_id and "a" * 64 in receipt_id


def test_issue_requires_verified_work_reference(tmp_path) -> None:
    controller = HostController(state_root=tmp_path)
    controller.init_task("task-001", "run-001")
    with pytest.raises(TransitionError, match="verified work artifact"):
        controller.issue_stage_receipt(Stage.RESEARCH, task_id="task-001", run_id="run-001", revision=1)


def test_issue_rejects_mismatched_revision_and_digest(tmp_path) -> None:
    controller = HostController(state_root=tmp_path)
    controller.init_task("task-001", "run-001")
    todo_ref = _completed_work_todo(controller, "task-001", "run-001", Stage.RESEARCH)
    with pytest.raises(TransitionError, match="revision"):
        controller.issue_stage_receipt(
            Stage.RESEARCH,
            task_id="task-001",
            run_id="run-001",
            revision=todo_ref.artifact_revision + 1,
            artifact_digest=todo_ref.artifact_digest,
            todo_ref=todo_ref,
        )
    with pytest.raises(TransitionError, match="digest"):
        controller.issue_stage_receipt(
            Stage.RESEARCH,
            task_id="task-001",
            run_id="run-001",
            revision=todo_ref.artifact_revision,
            artifact_digest="0" * 64,
            todo_ref=todo_ref,
        )


def test_tampered_artifact_digest_rejected(tmp_path) -> None:
    controller = HostController(state_root=tmp_path)
    controller.init_task("task-001", "run-001")
    todo_ref, receipt = _issue(controller, "task-001", "run-001", Stage.RESEARCH)
    tampered = todo_ref.model_copy(update={"artifact_digest": "0" * 64})
    # Tampered digests fail closed at the host work-list gate before receipt verify.
    with pytest.raises(TransitionError, match=r"invalid"):
        controller.advance_stage("task-001", "run-001", Stage.RESEARCH, receipt, todo_ref=tampered)


def test_stale_revision_cannot_reuse_old_receipt(tmp_path) -> None:
    from agent.contracts.common import ArtifactRef as _Ref
    from agent.runtime.canonical_serialization import SERIALIZER_PROFILE as _Profile
    from agent.runtime.work_todo import WorkStatus
    from tests.e2e.test_work_todo import WorkEvidence, binding

    controller = HostController(state_root=tmp_path)
    controller.init_task("real-work", "run-real")
    # Build a running intermediate revision, bind a receipt to it, then complete.
    scope = binding(controller, "research", "research-stale")
    _, pending = controller.assign_work(scope, action="Gather", expected_result="Evidence")
    _, running = controller.work_todos.set_status(pending, "work-1", WorkStatus.RUNNING)
    stale_receipt = controller.issue_stage_receipt(
        Stage.RESEARCH,
        task_id="real-work",
        run_id="run-real",
        revision=running.artifact_revision,
        artifact_digest=running.artifact_digest,
        todo_ref=running,
    )
    evidence = controller.artifact_store.put_immutable(
        WorkEvidence(value="done"),
        "evidence-work-1-stale",
        1,
        "test_evidence",
        "1.0",
    )

    evidence_ref = _Ref(
        artifact_id="evidence-work-1-stale",
        artifact_revision=1,
        artifact_digest=evidence,
        contract_id="test_evidence",
        contract_version="1.0",
        serializer_profile=_Profile,
    )
    _, completed = controller.work_todos.set_status(
        running, "work-1", WorkStatus.COMPLETED, actual_result="done", evidence_refs=(evidence_ref,)
    )
    assert completed.artifact_revision != running.artifact_revision
    with pytest.raises(TransitionError, match=r"invalid completion receipt"):
        controller.advance_stage("real-work", "run-real", Stage.RESEARCH, stale_receipt, todo_ref=completed)


def test_forged_receipt_id_rejected(tmp_path) -> None:
    controller = HostController(state_root=tmp_path)
    controller.init_task("task-001", "run-001")
    todo_ref, _ = _issue(controller, "task-001", "run-001", Stage.RESEARCH)
    forged = ReceiptRef(receipt_id="receipt-forged", receipt_digest="0" * 64, issuer_id="host")
    with pytest.raises(TransitionError, match="invalid completion receipt"):
        controller.advance_stage("task-001", "run-001", Stage.RESEARCH, forged, todo_ref=todo_ref)


def test_untrusted_issuer_rejected(tmp_path) -> None:
    controller = HostController(state_root=tmp_path)
    controller.init_task("task-001", "run-001")
    todo_ref, receipt = _issue(controller, "task-001", "run-001", Stage.RESEARCH)
    spoofed = ReceiptRef(receipt_id=receipt.receipt_id, receipt_digest=receipt.receipt_digest, issuer_id="agent")
    with pytest.raises(TransitionError, match="untrusted"):
        controller.advance_stage("task-001", "run-001", Stage.RESEARCH, spoofed, todo_ref=todo_ref)


def test_replay_across_tasks_runs_and_stages_rejected(tmp_path) -> None:
    controller = HostController(state_root=tmp_path)
    controller.init_task("task-001", "run-001")
    todo_ref, receipt = _issue(controller, "task-001", "run-001", Stage.RESEARCH)
    with pytest.raises(TransitionError, match=r"task/run binding mismatch|invalid completion receipt"):
        controller.advance_stage("task-001", "run-XXX", Stage.RESEARCH, receipt, todo_ref=todo_ref)
    controller2 = HostController(state_root=tmp_path / "other")
    controller2.init_task("task-001", "run-001")
    other_ref = _completed_work_todo(controller2, "task-001", "run-001", Stage.RESEARCH)
    assert receipt.receipt_id != stage_receipt_id(
        "task-001",
        "run-001",
        Stage.AUDIT_DISCOVERY.value,
        other_ref.artifact_revision,
        other_ref.artifact_digest,
    )
    with pytest.raises(TransitionError):
        controller2.advance_stage("task-001", "run-001", Stage.AUDIT_DISCOVERY, receipt, todo_ref=other_ref)
