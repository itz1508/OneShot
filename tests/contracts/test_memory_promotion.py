"""Real host stores: verify memory admission and journal/template promotion."""

import pytest
from pydantic import BaseModel

from agent.contracts.build import BuildActionExecution, BuildActionStatus, BuildRecord
from agent.contracts.build_memory import KnowledgeKind, VerifiedBuildKnowledge
from agent.contracts.build_validation import (
    BuildValidationRecord,
    CriterionResult,
    E2EResult,
    ObservedCriterionResult,
)
from agent.contracts.common import ArtifactRef
from agent.contracts.host import (
    BuildAdmissionReceipt,
    PackageLockReceipt,
    ReceiptRef,
    admission_receipt_subject,
)
from agent.contracts.plan_template import PlanTemplate
from agent.runtime.artifact_store import ArtifactStore
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE
from agent.runtime.memory_promotion import HostMemoryManager, MemoryPromotionError
from agent.runtime.plan_templates import PlanTemplateService
from agent.runtime.receipt_store import ReceiptStore
from agent.runtime.stage_journal import StageJournalService


class Evidence(BaseModel):
    text: str


def stored(store, model, artifact_id, contract):
    digest = store.put_immutable(model, artifact_id, 1, contract, "1.0")
    return ArtifactRef(
        artifact_id=artifact_id,
        artifact_revision=1,
        artifact_digest=digest,
        contract_id=contract,
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )


def receipt(receipts, receipt_id, subject):
    _, digest = receipts.issue_verified(receipt_id, "host", subject)
    return ReceiptRef(receipt_id=receipt_id, receipt_digest=digest, issuer_id="host")


def setup_case(tmp_path, *, success=True):
    artifacts = ArtifactStore(tmp_path)
    receipts = ReceiptStore(tmp_path)
    journals = StageJournalService(tmp_path / "runs", tmp_path / "events.db")
    research = stored(artifacts, Evidence(text="research"), "research", "evidence")
    audit = stored(artifacts, Evidence(text="audit"), "audit", "evidence")
    plan = stored(artifacts, Evidence(text="frozen plan"), "plan", "evidence")
    template = PlanTemplate(
        template_id="p",
        template_version=1,
        title="Known plan",
        category="integration",
        source_plan_ref=plan,
        source_audit_ref=audit,
        source_research_ref=research,
        matching_keywords=("build",),
        applicable_conditions=("verified repository",),
        required_decisions=("admission",),
        action_pattern=("change source",),
        verification_pattern=("independent E2E",),
    )
    acceptance = receipt(receipts, "acceptance", f"accepted-plan:{plan.artifact_digest}")
    template_ref = PlanTemplateService(artifacts, receipts).publish_candidate(
        template,
        acceptance_receipt_id=acceptance.receipt_id,
        acceptance_receipt_digest=acceptance.receipt_digest,
    )
    lock_subject = f"{research.artifact_digest}:{audit.artifact_digest}:{plan.artifact_digest}"
    lock_receipt = receipt(receipts, "lock", lock_subject)
    lock = PackageLockReceipt(
        lock_id="lock",
        research_ref=research,
        audit_ref=audit,
        frozen_spec_ref=plan,
        receipt_ref=lock_receipt,
    )
    lock_ref = stored(artifacts, lock, "lock-artifact", "package_lock")
    admission = BuildAdmissionReceipt(
        admission_id="admission",
        lock_receipt_ref=lock_receipt,
        authorized_action_ids=("action-1",),
        receipt_ref=receipt(
            receipts,
            "admission",
            admission_receipt_subject(lock_receipt, ("action-1",)),
        ),
    )
    admission_ref = stored(artifacts, admission, "admission-artifact", "build_admission")
    build = BuildRecord(
        task_id="t",
        run_id="r",
        stage_revision=1,
        lock_ref=lock_ref,
        admission_ref=admission_ref,
        action_executions=(
            BuildActionExecution(
                action_id="action-1",
                status=BuildActionStatus.COMPLETED,
            ),
        ),
    )
    build_ref = stored(artifacts, build, "build", "build_record")
    validation = BuildValidationRecord(
        task_id="t",
        run_id="r",
        stage_revision=1,
        build_ref=build_ref,
        criterion_results=(
            ObservedCriterionResult(
                criterion_id="AC-001",
                observed_result="passed",
                outcome=CriterionResult.PASS,
                evidence_refs=("EVD-001",),
                independent_observation="CI observed",
            ),
        ),
        e2e_results=(
            E2EResult(
                e2e_id="e2e",
                entrypoint="pytest",
                exit_code=0 if success else 1,
                outcome=CriterionResult.PASS if success else CriterionResult.FAIL,
            ),
        ),
    )
    validation_ref = stored(artifacts, validation, "validation", "build_validation_record")
    verification_subject = f"build-verification-passed:{validation_ref.artifact_digest}:{build_ref.artifact_digest}"
    approval_subject = (
        f"reusable-memory-approved:{validation_ref.artifact_digest}:{template_ref.artifact_digest}:knowledge-1"
    )
    memory = VerifiedBuildKnowledge(
        memory_id="knowledge-1",
        memory_revision=1,
        kind=KnowledgeKind.IMPLEMENTATION_PATTERN,
        summary="TaskTodo wave integration validated",
        reusable_scope="repository",
        evidence_refs=(research,),
        source_build_ref=build_ref,
        build_validation_ref=validation_ref,
        source_plan_template_ref=template_ref,
        verification_receipt_ref=receipt(receipts, "verification", verification_subject),
        approval_receipt_ref=receipt(receipts, "approval", approval_subject),
    )
    manager = HostMemoryManager(artifacts, receipts, journals)
    completion = receipt(receipts, "completed", f"build-execution-completed:{build_ref.artifact_digest}")
    diagnostic = receipt(receipts, "diagnostic", f"build-diagnostic-valid:{build_ref.artifact_digest}")
    return manager, journals, memory, completion, diagnostic


def test_verified_memory_promotes_template_once(tmp_path):
    manager, journals, memory, completion, diagnostic = setup_case(tmp_path)
    first, template = manager.promote(
        workspace_id="w",
        task_id="t",
        run_id="r",
        memory=memory,
        build_completion_receipt=completion,
        diagnostic_receipt=diagnostic,
    )
    assert template.artifact_revision == 2
    assert first.artifact_revision == 1
    assert len(journals.load(workspace_id="w", task_id="t", run_id="r", stage="mem")) == 1
    assert len(journals.load(workspace_id="w", task_id="t", run_id="r", stage="plan")) == 1
    replay = manager.promote(
        workspace_id="w",
        task_id="t",
        run_id="r",
        memory=memory,
        build_completion_receipt=completion,
        diagnostic_receipt=diagnostic,
    )
    assert replay == (first, template)
    assert len(journals.load(workspace_id="w", task_id="t", run_id="r", stage="mem")) == 1


def test_failed_e2e_cannot_promote(tmp_path):
    manager, journals, memory, completion, diagnostic = setup_case(tmp_path, success=False)
    with pytest.raises(MemoryPromotionError, match="verification did not pass"):
        manager.promote(
            workspace_id="w",
            task_id="t",
            run_id="r",
            memory=memory,
            build_completion_receipt=completion,
            diagnostic_receipt=diagnostic,
        )
    assert journals.load(workspace_id="w", task_id="t", run_id="r", stage="mem") == ()


def test_missing_approval_blocks_memory(tmp_path):
    manager, journals, memory, completion, diagnostic = setup_case(tmp_path)

    untrusted = ReceiptRef(receipt_id="missing", receipt_digest="a" * 64, issuer_id="host")
    forged = VerifiedBuildKnowledge.model_validate(
        {**memory.model_dump(), "approval_receipt_ref": untrusted.model_dump()}
    )
    with pytest.raises(MemoryPromotionError, match="trusted host receipt"):
        manager.promote(
            workspace_id="w",
            task_id="t",
            run_id="r",
            memory=forged,
            build_completion_receipt=completion,
            diagnostic_receipt=diagnostic,
        )
    assert journals.load(workspace_id="w", task_id="t", run_id="r", stage="mem") == ()


def test_conflicting_template_receipt_cannot_append_memory(tmp_path):
    manager, journals, memory, completion, diagnostic = setup_case(tmp_path)
    manager.promote(
        workspace_id="w",
        task_id="t",
        run_id="r",
        memory=memory,
        build_completion_receipt=completion,
        diagnostic_receipt=diagnostic,
    )
    subject = (
        f"build-verification-passed:{memory.build_validation_ref.artifact_digest}:"
        f"{memory.source_build_ref.artifact_digest}"
    )
    alternate = receipt(manager._receipts, "verification-alternate", subject)
    conflicting = VerifiedBuildKnowledge.model_validate(
        {**memory.model_dump(), "verification_receipt_ref": alternate.model_dump()}
    )
    with pytest.raises(MemoryPromotionError, match="conflicting verified template"):
        manager.promote(
            workspace_id="w",
            task_id="t",
            run_id="r",
            memory=conflicting,
            build_completion_receipt=completion,
            diagnostic_receipt=diagnostic,
        )
    assert len(journals.load(workspace_id="w", task_id="t", run_id="r", stage="mem")) == 1
