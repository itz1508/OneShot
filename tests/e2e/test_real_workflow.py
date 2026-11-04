"""E2E workflow tests — E2E01-E2E06, S1-S6, and adversarial security tests."""

import os
from pathlib import Path

import pytest
from pydantic import BaseModel

from agent.contracts.build import BuildActionStatus
from agent.contracts.common import ArtifactRef
from agent.contracts.host import ReceiptRef
from agent.contracts.research import (
    AuthorizationStatus,
    CriteriaStatus,
    FeasibilityStatus,
    Requirement,
    ResearchRecord,
)
from agent.contracts.scanner import ScannerFinding
from agent.contracts.work_todo import WorkBinding, WorkStatus
from agent.runtime.artifact_store import ArtifactStore
from agent.runtime.authorization import AuthorizationEngine
from agent.runtime.build_admission import BuildAdmission, BuildAdmissionError
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE, digest_raw
from agent.runtime.checkpoint_store import CheckpointStore
from agent.runtime.controller import STAGE_ORDER, HostController, Stage, TransitionError
from agent.runtime.effect_executor import EffectExecutor
from agent.runtime.receipt_store import ReceiptStore
from agent.runtime.scanner_gateway import ScannerGateway
from tests.fixtures.structural_gap import passing_gap

LOCK_SUBJECT = "package_lock"


class _WorkFixture(BaseModel):
    label: str


def _completed_work_todo(controller, task_id, run_id, stage):
    """Record actual persisted test evidence before accepting a simulated stage."""
    request_id = f"request-{stage.value}"
    request_name = f"fixture-input-{task_id}-{run_id}-{stage.value}"
    evidence_name = f"fixture-output-{task_id}-{run_id}-{stage.value}"
    input_digest = controller.artifact_store.put_immutable(
        _WorkFixture(label=request_id), request_name, 1, "fixture", "1.0"
    )
    input_ref = ArtifactRef(
        artifact_id=request_name,
        artifact_revision=1,
        artifact_digest=input_digest,
        contract_id="fixture",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )
    scope = WorkBinding(
        task_id=task_id,
        run_id=run_id,
        stage=stage.value,
        request_id=request_id,
        request_revision=1,
        input_request_ref=input_ref,
    )
    _work, todo_ref = controller.assign_work(
        scope,
        action=f"Observe {stage.value} stage fixture",
        expected_result=f"Verified {stage.value} fixture output",
    )
    _work, running = controller.work_todos.set_status(todo_ref, "work-1", WorkStatus.RUNNING)
    output_digest = controller.artifact_store.put_immutable(
        _WorkFixture(label=f"observed {stage.value}"), evidence_name, 1, "fixture", "1.0"
    )
    output_ref = ArtifactRef(
        artifact_id=evidence_name,
        artifact_revision=1,
        artifact_digest=output_digest,
        contract_id="fixture",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )
    _work, completed = controller.work_todos.set_status(
        running,
        "work-1",
        WorkStatus.COMPLETED,
        actual_result=f"observed {stage.value}",
        evidence_refs=(output_ref,),
    )
    return completed


def _advance_with_receipt(controller, task_id, run_id, stage):
    """Helper: record work, issue a stage receipt, then advance."""
    todo_ref = _completed_work_todo(controller, task_id, run_id, stage)
    receipt = controller.issue_stage_receipt(stage, task_id=task_id, run_id=run_id, revision=1)
    if stage is Stage.PLANNING:
        gap = passing_gap(controller)
        assert gap.completion_receipt_ref is not None
        return controller.advance_stage(
            task_id,
            run_id,
            stage,
            receipt,
            gap_result_ref=gap.result_ref,
            gap_receipt_ref=gap.completion_receipt_ref,
            todo_ref=todo_ref,
        )
    return controller.advance_stage(task_id, run_id, stage, receipt, todo_ref=todo_ref)


def _make_admission(receipts, action_ids=("act-001",), lock_subject=LOCK_SUBJECT):
    """Helper: issue lock receipt and admission."""
    _, lock_digest = receipts.issue_verified("lock-001", "host", lock_subject)
    lock_ref = ReceiptRef(receipt_id="lock-001", receipt_digest=lock_digest, issuer_id="host")
    admission = BuildAdmission(receipts)
    return admission.admit(
        admission_id="adm-001",
        lock_receipt_ref=lock_ref,
        authorized_action_ids=action_ids,
        lock_subject=lock_subject,
    )


def _store_artifact(tmp_path, artifact_id="cand-001"):
    """Store a research artifact and return (store, digest)."""
    store = ArtifactStore(tmp_path)
    record = ResearchRecord(
        task_id="task-001",
        run_id="run-001",
        stage_revision=1,
        requirements=(
            Requirement(
                requirement_id="REQ-001",
                source_reference="user",
                original_wording="need",
                statement="implement",
            ),
        ),
    )
    digest = store.put_immutable(record, artifact_id, 1, "planning", "1.0")
    return store, digest


class TestE2EWorkflow:
    def test_task_init_and_advance(self, tmp_path):
        """E2E01: Task initialization and stage advancement."""
        controller = HostController(state_root=tmp_path)
        state = controller.init_task("task-001", "run-001")
        assert state.current_stage == Stage.RESEARCH
        state = _advance_with_receipt(controller, "task-001", "run-001", Stage.RESEARCH)
        assert state.current_stage == Stage.AUDIT_DISCOVERY
        assert Stage.RESEARCH in state.completed_stages

    def test_stage_order_correct(self, tmp_path):
        """E2E02: Stage order matches design."""
        expected = (
            Stage.RESEARCH,
            Stage.AUDIT_DISCOVERY,
            Stage.PLANNING,
            Stage.FIXTURE_VALIDATION,
            Stage.BUILD,
            Stage.BUILD_VALIDATION,
        )
        assert expected == STAGE_ORDER

    def test_illegal_transition_rejected(self, tmp_path):
        """E2E03: Illegal stage transition rejected."""
        controller = HostController(state_root=tmp_path)
        controller.init_task("task-001", "run-001")
        with pytest.raises(TransitionError):
            controller.advance_stage("task-001", "run-001", Stage.BUILD)

    def test_advance_without_receipt_rejected(self, tmp_path):
        """E2E03b: Stage advance without completion receipt is rejected."""
        controller = HostController(state_root=tmp_path)
        controller.init_task("task-001", "run-001")
        with pytest.raises(TransitionError, match="receipt required"):
            controller.advance_stage("task-001", "run-001", Stage.RESEARCH)

    def test_advance_with_invalid_receipt_rejected(self, tmp_path):
        """E2E03c: Stage advance with invalid receipt is rejected."""
        controller = HostController(state_root=tmp_path)
        controller.init_task("task-001", "run-001")
        fake_receipt = ReceiptRef(receipt_id="fake", receipt_digest="0" * 64, issuer_id="host")
        with pytest.raises(TransitionError, match="invalid completion receipt"):
            controller.advance_stage("task-001", "run-001", Stage.RESEARCH, fake_receipt)

    def test_advance_with_cross_task_receipt_rejected(self, tmp_path):
        """E2E03d: Receipt from different task is rejected."""
        controller = HostController(state_root=tmp_path)
        controller.init_task("task-001", "run-001")
        controller.init_task("task-002", "run-002")
        _completed_work_todo(controller, "task-002", "run-002", Stage.RESEARCH)
        # Issue a legitimate artifact-bound receipt for a DIFFERENT task.
        cross_receipt = controller.issue_stage_receipt(Stage.RESEARCH, task_id="task-002", run_id="run-002", revision=1)
        with pytest.raises(TransitionError, match="invalid completion receipt"):
            controller.advance_stage("task-001", "run-001", Stage.RESEARCH, cross_receipt)

    def test_planning_requires_verified_structural_gap(self, tmp_path):
        controller = HostController(state_root=tmp_path)
        controller.init_task("task-001", "run-001")
        _advance_with_receipt(controller, "task-001", "run-001", Stage.RESEARCH)
        _advance_with_receipt(controller, "task-001", "run-001", Stage.AUDIT_DISCOVERY)
        todo_ref = _completed_work_todo(controller, "task-001", "run-001", Stage.PLANNING)
        receipt = controller.issue_stage_receipt(Stage.PLANNING, task_id="task-001", run_id="run-001", revision=1)
        with pytest.raises(TransitionError, match="structural gap analysis"):
            controller.advance_stage("task-001", "run-001", Stage.PLANNING, receipt)

        gap = passing_gap(controller)
        assert gap.completion_receipt_ref is not None
        state = controller.advance_stage(
            "task-001",
            "run-001",
            Stage.PLANNING,
            receipt,
            gap_result_ref=gap.result_ref,
            gap_receipt_ref=gap.completion_receipt_ref,
            todo_ref=todo_ref,
        )
        assert state.current_stage == Stage.FIXTURE_VALIDATION

    def test_resume_from_checkpoint(self, tmp_path):
        """E2E04: Resume from last checkpoint."""
        controller = HostController(state_root=tmp_path)
        controller.init_task("task-001", "run-001")
        _advance_with_receipt(controller, "task-001", "run-001", Stage.RESEARCH)
        controller2 = HostController(state_root=tmp_path)
        state = controller2.get_state("task-001")
        assert state is not None
        assert state.current_stage == Stage.AUDIT_DISCOVERY

    def test_provider_integration_in_workflow(self, tmp_path):
        """E2E05: Provider works within workflow context."""
        controller = HostController(state_root=tmp_path)
        result = controller.providers.generate(
            "echo",
            __import__("agent.runtime.providers.base", fromlist=["ProviderRequest"]).ProviderRequest(
                run_id="run-001",
                prompt="analyze requirements",
            ),
        )
        assert result.content.startswith("echo:")

    def test_artifact_persisted_across_stages(self, tmp_path):
        """E2E06: Artifacts persist across stage transitions."""
        store = ArtifactStore(tmp_path)
        record = ResearchRecord(
            task_id="task-001",
            run_id="run-001",
            stage_revision=1,
            requirements=(
                Requirement(
                    requirement_id="REQ-001",
                    source_reference="user",
                    original_wording="need a thing",
                    statement="Implement a thing",
                    authorization_status=AuthorizationStatus.GRANTED,
                    feasibility_status=FeasibilityStatus.FEASIBLE,
                    criteria_status=CriteriaStatus.DEFINED,
                    acceptance_criteria_ids=("AC-001",),
                ),
            ),
        )
        digest = store.put_immutable(record, "research-001", 1, "research", "1.0")
        assert store.get_digest("research-001", 1) == digest


class TestScenarios:
    """S1-S6 scenario and adversarial security tests."""

    def test_s1_normal_completion(self, tmp_path):
        """S1: Normal stage progression through all stages."""
        controller = HostController(state_root=tmp_path)
        controller.init_task("task-001", "run-001")
        for stage in STAGE_ORDER[:-1]:
            _advance_with_receipt(controller, "task-001", "run-001", stage)
        state = controller.get_state("task-001")
        assert state.current_stage == Stage.BUILD_VALIDATION
        final_ref = _completed_work_todo(controller, "task-001", "run-001", Stage.BUILD_VALIDATION)
        final_receipt = controller.issue_stage_receipt(Stage.BUILD_VALIDATION, task_id="task-001", run_id="run-001")
        with pytest.raises(TransitionError, match="final-stage work list"):
            controller.complete_final_stage("task-001", "run-001", final_receipt, todo_ref=None)
        state = controller.complete_final_stage("task-001", "run-001", final_receipt, todo_ref=final_ref)
        assert Stage.BUILD_VALIDATION in state.completed_stages
        from agent.cli import cmd_verify

        assert cmd_verify("task-001", state_root=str(tmp_path)) == 0

    def test_s2_unsupported_claim_do_not_use(self, tmp_path):
        """S2: Unsupported capability returns BLOCKED, not pass."""
        store, _ = _store_artifact(tmp_path)
        scanner = ScannerGateway(artifact_store=store)
        scanner.register_detector("syntax", lambda _: ())
        ref = ArtifactRef(
            artifact_id="cand-001",
            artifact_revision=1,
            artifact_digest="a" * 64,
            contract_id="planning",
            contract_version="1.0",
            serializer_profile="rfc8785-jcs-sha256-v1",
        )
        result = scanner.scan_exact(ref, "repo-001", ("syntax", "security"))
        assert result.outcome.value == "blocked"

    def test_s2b_scanner_blocks_without_artifact_store(self, tmp_path):
        """S2b: Scanner returns BLOCKED when no artifact store is configured."""
        scanner = ScannerGateway()
        scanner.register_detector("syntax", lambda _: ())
        ref = ArtifactRef(
            artifact_id="cand-001",
            artifact_revision=1,
            artifact_digest="a" * 64,
            contract_id="planning",
            contract_version="1.0",
            serializer_profile="rfc8785-jcs-sha256-v1",
        )
        result = scanner.scan_exact(ref, "repo-001", ("syntax",))
        assert result.outcome.value == "blocked"
        assert "no artifact store" in result.limitation_reasons[0]

    def test_s2c_scanner_passes_with_real_detector(self, tmp_path):
        """S2c: Scanner passes when real detector finds no issues."""
        store, digest = _store_artifact(tmp_path)
        scanner = ScannerGateway(artifact_store=store)

        # Register a real detector that checks content is non-empty
        def syntax_detector(content: bytes) -> tuple[ScannerFinding, ...]:
            if not content:
                return (
                    ScannerFinding(
                        finding_id="find-001",
                        capability="syntax",
                        severity="error",
                        message="empty content",
                    ),
                )
            return ()

        scanner.register_detector("syntax", syntax_detector)
        ref = ArtifactRef(
            artifact_id="cand-001",
            artifact_revision=1,
            artifact_digest=digest,
            contract_id="planning",
            contract_version="1.0",
            serializer_profile="rfc8785-jcs-sha256-v1",
        )
        result = scanner.scan_exact(ref, "repo-001", ("syntax",))
        assert result.outcome.value == "pass"
        assert "syntax" in result.capabilities_checked

    def test_s2d_scanner_blocks_with_detector_findings(self, tmp_path):
        """S2d: Scanner blocks when detector finds issues."""
        store, digest = _store_artifact(tmp_path)
        scanner = ScannerGateway(artifact_store=store)

        # Detector that always finds an issue
        def failing_detector(content: bytes) -> tuple[ScannerFinding, ...]:
            return (
                ScannerFinding(
                    finding_id="find-001",
                    capability="syntax",
                    severity="error",
                    message="syntax error detected",
                ),
            )

        scanner.register_detector("syntax", failing_detector)
        ref = ArtifactRef(
            artifact_id="cand-001",
            artifact_revision=1,
            artifact_digest=digest,
            contract_id="planning",
            contract_version="1.0",
            serializer_profile="rfc8785-jcs-sha256-v1",
        )
        result = scanner.scan_exact(ref, "repo-001", ("syntax",))
        assert result.outcome.value == "blocked"
        assert len(result.findings) > 0

    def test_s2e_scanner_blocks_without_detector(self, tmp_path):
        """S2e: Scanner blocks when capability has no detector registered."""
        store, digest = _store_artifact(tmp_path)
        scanner = ScannerGateway(artifact_store=store)
        # Register capability but NOT a detector
        scanner.register_capability("syntax")
        ref = ArtifactRef(
            artifact_id="cand-001",
            artifact_revision=1,
            artifact_digest=digest,
            contract_id="planning",
            contract_version="1.0",
            serializer_profile="rfc8785-jcs-sha256-v1",
        )
        result = scanner.scan_exact(ref, "repo-001", ("syntax",))
        assert result.outcome.value == "blocked"
        assert "no detector registered" in result.limitation_reasons[0]

    def test_s2f_scanner_blocks_digest_mismatch(self, tmp_path):
        """S2f: Scanner blocks when content digest doesn't match expected."""
        store, _ = _store_artifact(tmp_path)
        scanner = ScannerGateway(artifact_store=store)
        scanner.register_detector("syntax", lambda _: ())
        ref = ArtifactRef(
            artifact_id="cand-001",
            artifact_revision=1,
            artifact_digest="0" * 64,
            contract_id="planning",
            contract_version="1.0",
            serializer_profile="rfc8785-jcs-sha256-v1",
        )
        result = scanner.scan_exact(ref, "repo-001", ("syntax",))
        assert result.outcome.value == "blocked"
        assert "digest mismatch" in result.limitation_reasons[0]

    def test_s3_validate_first(self, tmp_path):
        """S3: Validation occurs before stage advancement."""
        controller = HostController(state_root=tmp_path)
        controller.init_task("task-001", "run-001")
        with pytest.raises(TransitionError):
            controller.advance_stage("task-001", "run-001", Stage.PLANNING)

    def test_s4_build_contradicts_plan(self, tmp_path):
        """S4: Build effect with wrong preimage fails."""
        auth = AuthorizationEngine(allowed_roots=(str(tmp_path),))
        checkpoints = CheckpointStore(tmp_path)
        receipts = ReceiptStore(tmp_path)
        executor = EffectExecutor(auth, checkpoints, receipts, tmp_path)
        admission_receipt = _make_admission(receipts)
        (tmp_path / "existing.py").write_text("original content")
        result = executor.execute_admitted(
            action_id="act-001",
            action_kind="modify",
            admission_receipt=admission_receipt,
            source_path="existing.py",
            content="new content",
            expected_source_digest="0" * 64,
        )
        assert result.status.value == "failed"
        assert "preimage mismatch" in (result.error or "")

    def test_s4b_execute_without_admission_rejected(self, tmp_path):
        """S4b: Effect execution without admission receipt raises error."""
        auth = AuthorizationEngine(allowed_roots=(str(tmp_path),))
        checkpoints = CheckpointStore(tmp_path)
        receipts = ReceiptStore(tmp_path)
        executor = EffectExecutor(auth, checkpoints, receipts, tmp_path)
        with pytest.raises(TypeError):
            executor.execute_admitted(
                action_id="act-001",
                action_kind="create",
                target_path="test.py",
                content="content",
            )

    def test_s4c_path_escape_blocked(self, tmp_path):
        """S4c: Filesystem containment rejects paths escaping workspace."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state = tmp_path / "state"
        auth = AuthorizationEngine(allowed_roots=(str(workspace), str(state)))
        checkpoints = CheckpointStore(state)
        receipts = ReceiptStore(state)
        executor = EffectExecutor(auth, checkpoints, receipts, workspace)
        admission_receipt = _make_admission(receipts)
        for path in (tmp_path / "outside" / "escape.py", Path("../relative-outside/escape.py")):
            result = executor.execute_admitted(
                action_id="act-001",
                action_kind="create",
                admission_receipt=admission_receipt,
                target_path=str(path),
                content="escaped",
            )
            assert result.status.value == "blocked"
            assert "escapes workspace" in (result.error or "")
        assert not (tmp_path / "outside").exists()
        assert not (tmp_path / "relative-outside").exists()

    def test_s4d_admission_with_invalid_lock_rejected(self, tmp_path):
        """S4d: BuildAdmission rejects invalid lock receipt."""
        receipts = ReceiptStore(tmp_path)
        admission = BuildAdmission(receipts)
        fake_lock = ReceiptRef(receipt_id="nonexistent", receipt_digest="0" * 64, issuer_id="host")
        with pytest.raises(BuildAdmissionError, match="invalid lock receipt"):
            admission.admit(
                admission_id="adm-001",
                lock_receipt_ref=fake_lock,
                authorized_action_ids=("act-001",),
                lock_subject=LOCK_SUBJECT,
            )

    def test_s4e_admission_with_wrong_subject_rejected(self, tmp_path):
        """S4e: BuildAdmission rejects lock with wrong subject."""
        receipts = ReceiptStore(tmp_path)
        _, lock_digest = receipts.issue_verified("lock-001", "host", "wrong_subject")
        lock_ref = ReceiptRef(receipt_id="lock-001", receipt_digest=lock_digest, issuer_id="host")
        admission = BuildAdmission(receipts)
        with pytest.raises(BuildAdmissionError, match="invalid lock receipt"):
            admission.admit(
                admission_id="adm-001",
                lock_receipt_ref=lock_ref,
                authorized_action_ids=("act-001",),
                lock_subject=LOCK_SUBJECT,
            )

    def test_s4f_admission_with_untrusted_issuer_rejected(self, tmp_path):
        """S4f: BuildAdmission rejects lock from untrusted issuer."""
        receipts = ReceiptStore(tmp_path)
        _, lock_digest = receipts.issue_verified("lock-001", "host", LOCK_SUBJECT)
        lock_ref = ReceiptRef(receipt_id="lock-001", receipt_digest=lock_digest, issuer_id="attacker")
        admission = BuildAdmission(receipts)
        with pytest.raises(BuildAdmissionError, match="untrusted lock issuer"):
            admission.admit(
                admission_id="adm-001",
                lock_receipt_ref=lock_ref,
                authorized_action_ids=("act-001",),
                lock_subject=LOCK_SUBJECT,
            )

    def test_s4g_symlink_escape_blocked(self, tmp_path):
        """S4g: Symlink-based path escape is blocked by realpath containment."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        # Create a symlink inside workspace pointing outside
        target_outside = tmp_path / "outside_target.txt"
        symlink_path = workspace / "evil_link.py"
        os.symlink(str(target_outside), str(symlink_path))

        state = tmp_path / "state"
        auth = AuthorizationEngine(allowed_roots=(str(workspace), str(state)))
        checkpoints = CheckpointStore(state)
        receipts = ReceiptStore(state)
        executor = EffectExecutor(auth, checkpoints, receipts, workspace)
        admission_receipt = _make_admission(receipts)

        # Try to modify through the symlink — should be blocked
        result = executor.execute_admitted(
            action_id="act-001",
            action_kind="modify",
            admission_receipt=admission_receipt,
            source_path="evil_link.py",
            content="escaped via symlink",
        )
        assert result.status.value in ("blocked", "failed")

    def test_s4h_sibling_path_confusion_blocked(self, tmp_path):
        """S4h: Sibling directory with similar name is not confused with workspace."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        evil_twin = tmp_path / "workspace_evil"
        evil_twin.mkdir()

        state = tmp_path / "state"
        auth = AuthorizationEngine(allowed_roots=(str(workspace), str(state)))
        checkpoints = CheckpointStore(state)
        receipts = ReceiptStore(state)
        executor = EffectExecutor(auth, checkpoints, receipts, workspace)
        admission_receipt = _make_admission(receipts)

        # Try to create in sibling dir that starts with same prefix
        result = executor.execute_admitted(
            action_id="act-001",
            action_kind="create",
            admission_receipt=admission_receipt,
            target_path=str(evil_twin / "escape.py"),
            content="sibling escape",
        )
        assert result.status.value == "blocked"
        assert "escapes workspace" in (result.error or "")

    def test_s5_interruption_and_resume(self, tmp_path):
        """S5: Interrupted task can resume from checkpoint."""
        controller = HostController(state_root=tmp_path)
        controller.init_task("task-001", "run-001")
        _advance_with_receipt(controller, "task-001", "run-001", Stage.RESEARCH)
        _advance_with_receipt(controller, "task-001", "run-001", Stage.AUDIT_DISCOVERY)
        controller2 = HostController(state_root=tmp_path)
        state = controller2.get_state("task-001")
        assert state is not None
        assert state.current_stage == Stage.PLANNING
        assert Stage.RESEARCH in state.completed_stages
        assert Stage.AUDIT_DISCOVERY in state.completed_stages

    def test_s6_crash_safe_reconciliation(self, tmp_path):
        """S6: Effect executor reconciles after crash by comparing digests."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state = tmp_path / "state"
        auth = AuthorizationEngine(allowed_roots=(str(workspace), str(state)))
        checkpoints = CheckpointStore(state)
        receipts = ReceiptStore(state)
        executor = EffectExecutor(auth, checkpoints, receipts, workspace)
        admission_receipt = _make_admission(receipts)

        result = executor.execute_admitted(
            action_id="act-001",
            action_kind="create",
            admission_receipt=admission_receipt,
            target_path="output.py",
            content="print('hello')",
        )
        assert result.status is BuildActionStatus.COMPLETED
        expected_digest = result.post_image_digest

        # Reconcile after successful completion
        reconciled = executor.reconcile_effect("act-001", "output.py", expected_digest)
        assert reconciled.status is BuildActionStatus.COMPLETED

        # Simulate corruption
        (workspace / "output.py").write_text("print('corrupted')")
        corrupted = executor.reconcile_effect("act-001", "output.py", expected_digest)
        assert corrupted.status is BuildActionStatus.FAILED
        assert "digest mismatch" in (corrupted.error or "")

    def test_s6b_effect_uncertain_after_crash(self, tmp_path, monkeypatch):
        """S6b: Pre-effect checkpoint survives crash and produces EFFECT_UNCERTAIN."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state = tmp_path / "state"
        auth = AuthorizationEngine(allowed_roots=(str(workspace), str(state)))
        checkpoints = CheckpointStore(state)
        receipts = ReceiptStore(state)
        executor = EffectExecutor(auth, checkpoints, receipts, workspace)
        admission_receipt = _make_admission(receipts, action_ids=("act-002",))

        # Interrupt after the filesystem effect, before the completion checkpoint.
        def interrupt_completion(_action_id):
            raise RuntimeError("simulated crash before completion checkpoint")

        monkeypatch.setattr(executor, "_clear_pre_effect_checkpoint", interrupt_completion)
        result = executor.execute_admitted(
            action_id="act-002",
            action_kind="create",
            admission_receipt=admission_receipt,
            target_path="output2.py",
            content="print('hello')",
        )
        assert result.status is BuildActionStatus.EFFECT_UNCERTAIN
        expected_digest = digest_raw(b"print('hello')")

        # Simulate a crash on a NEW executor with same state
        executor2 = EffectExecutor(auth, checkpoints, receipts, workspace)

        # Reconcile — file matches, should complete
        reconciled = executor2.reconcile_effect("act-002", "output2.py", expected_digest)
        assert reconciled.status is BuildActionStatus.COMPLETED

    def test_s6c_post_effect_reconciled_receipt(self, tmp_path, monkeypatch):
        """S6c: POST_EFFECT_RECONCILED receipt is issued after successful crash reconciliation."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state = tmp_path / "state"
        auth = AuthorizationEngine(allowed_roots=(str(workspace), str(state)))
        checkpoints = CheckpointStore(state)
        receipts = ReceiptStore(state)
        executor = EffectExecutor(auth, checkpoints, receipts, workspace)
        admission_receipt = _make_admission(receipts, action_ids=("act-003",))

        # Leave the pre-effect checkpoint pending after the file is written.
        def interrupt_completion(_action_id):
            raise RuntimeError("simulated crash before completion checkpoint")

        monkeypatch.setattr(executor, "_clear_pre_effect_checkpoint", interrupt_completion)
        result = executor.execute_admitted(
            action_id="act-003",
            action_kind="create",
            admission_receipt=admission_receipt,
            target_path="output3.py",
            content="test",
        )
        assert result.status is BuildActionStatus.EFFECT_UNCERTAIN

        # New executor simulates restart
        executor2 = EffectExecutor(auth, checkpoints, receipts, workspace)
        reconciled = executor2.reconcile_effect("act-003", "output3.py", digest_raw(b"test"))
        assert reconciled.status is BuildActionStatus.COMPLETED

        # Verify the receipt is bound to the reconciled action and its post-image.
        subject = f"post_effect_reconciled:act-003:{reconciled.post_image_digest}"
        receipt_digest = digest_raw(f"reconciled-act-003:host:{subject}".encode())
        assert receipts.verify("reconciled-act-003", receipt_digest, subject)

    def test_s7_full_host_controlled_execution(self, tmp_path):
        """S7: Full host-controlled execution path: lock → admit → execute → verify."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state = tmp_path / "state"
        auth = AuthorizationEngine(allowed_roots=(str(workspace), str(state)))
        checkpoints = CheckpointStore(state)
        receipts = ReceiptStore(state)
        executor = EffectExecutor(auth, checkpoints, receipts, workspace)

        # 1. Issue Package Lock receipt
        lock_subject = "package_lock:research-001:audit-001:spec-001"
        _, lock_digest = receipts.issue_verified("lock-001", "host", lock_subject)
        lock_ref = ReceiptRef(receipt_id="lock-001", receipt_digest=lock_digest, issuer_id="host")

        # 2. Admit build operations
        admission = BuildAdmission(receipts)
        admission_receipt = admission.admit(
            admission_id="adm-001",
            lock_receipt_ref=lock_ref,
            authorized_action_ids=("act-001",),
            lock_subject=lock_subject,
        )

        # 3. Execute build action
        result = executor.execute_admitted(
            action_id="act-001",
            action_kind="create",
            admission_receipt=admission_receipt,
            target_path="built.py",
            content="print('built')",
        )
        assert result.status is BuildActionStatus.COMPLETED
        assert result.post_image_digest is not None

        # 4. Verify the file exists and has correct digest
        assert (workspace / "built.py").exists()
        import hashlib

        actual = hashlib.sha256((workspace / "built.py").read_bytes()).hexdigest()
        assert actual == result.post_image_digest

        # 5. Reconcile to confirm durability
        executor2 = EffectExecutor(auth, checkpoints, receipts, workspace)
        reconciled = executor2.reconcile_effect("act-001", "built.py", result.post_image_digest)
        assert reconciled.status is BuildActionStatus.COMPLETED

    def test_s8_unauthorized_action_rejected(self, tmp_path):
        """S8: Action not in admission authorized_action_ids is rejected."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        state = tmp_path / "state"
        auth = AuthorizationEngine(allowed_roots=(str(workspace), str(state)))
        checkpoints = CheckpointStore(state)
        receipts = ReceiptStore(state)
        executor = EffectExecutor(auth, checkpoints, receipts, workspace)

        # Admit only act-001
        admission_receipt = _make_admission(receipts, action_ids=("act-001",))

        # Try to execute act-002 (not authorized)
        from agent.runtime.effect_executor import EffectExecutionError

        with pytest.raises(EffectExecutionError, match="not authorized"):
            executor.execute_admitted(
                action_id="act-002",
                action_kind="create",
                admission_receipt=admission_receipt,
                target_path="unauthorized.py",
                content="unauthorized",
            )

    def test_cli_verify_incomplete_returns_nonzero(self, tmp_path):
        """CLI verify returns 1 when task is not complete."""
        from agent.cli import cmd_verify

        controller = HostController(state_root=tmp_path)
        controller.init_task("task-001", "run-001")
        assert cmd_verify("task-001", str(tmp_path)) == 1

    def test_research_to_audit_handoff(self, tmp_path):
        """Full research→audit handoff with artifact store."""
        store = ArtifactStore(tmp_path)
        receipts = ReceiptStore(tmp_path)
        research = ResearchRecord(
            task_id="task-001",
            run_id="run-001",
            stage_revision=1,
            requirements=(
                Requirement(
                    requirement_id="REQ-001",
                    source_reference="user",
                    original_wording="need",
                    statement="implement",
                    authorization_status=AuthorizationStatus.GRANTED,
                    feasibility_status=FeasibilityStatus.FEASIBLE,
                    criteria_status=CriteriaStatus.DEFINED,
                ),
            ),
        )
        research_digest = store.put_immutable(research, "research-001", 1, "research", "1.0")
        _, receipt_digest = receipts.issue_verified("handoff-001", "host", f"research-001:{research_digest}")
        assert receipt_digest
        assert store.get_digest("research-001", 1) == research_digest
