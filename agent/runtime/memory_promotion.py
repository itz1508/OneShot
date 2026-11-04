"""Host-only promotion of independently verified Build knowledge.

Neither a Builder result nor an ordinary stage event authorizes memory.
Each promoted fact is backed by exact artifacts and trusted receipt subjects.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from agent.contracts.build import BuildActionStatus, BuildRecord
from agent.contracts.build_memory import VerifiedBuildKnowledge
from agent.contracts.build_validation import BuildValidationRecord, CriterionResult
from agent.contracts.common import ArtifactRef, StepStatus
from agent.contracts.host import BuildAdmissionReceipt, PackageLockReceipt, ReceiptRef, admission_receipt_subject
from agent.contracts.plan_template import PlanTemplate, TemplateStatus
from agent.contracts.stage_log import StageLogEvent
from agent.runtime.artifact_store import ArtifactStore
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE
from agent.runtime.plan_templates import PlanTemplateService
from agent.runtime.receipt_store import ReceiptStore
from agent.runtime.stage_journal import StageJournalService


class MemoryPromotionError(ValueError):
    pass


_REDACT = re.compile(r"(?i)(?:/home/|/users/|[a-z]:\\|api[_-]?key\s*[:=]|bearer\s+\S+|sk-[a-z0-9]{12,})")


class HostMemoryManager:
    def __init__(
        self,
        artifacts: ArtifactStore,
        receipts: ReceiptStore,
        journals: StageJournalService,
    ) -> None:
        self._artifacts = artifacts
        self._receipts = receipts
        self._journals = journals
        self._templates = PlanTemplateService(artifacts, receipts)

    def _load(self, ref: ArtifactRef, model: type[BaseModel]) -> BaseModel:
        if self._artifacts.get_digest(ref.artifact_id, ref.artifact_revision) != ref.artifact_digest:
            raise MemoryPromotionError("missing or changed source artifact")
        return model.model_validate_json(self._artifacts.get_verified(ref.artifact_id, ref.artifact_revision))

    def _verify_receipt(self, receipt: ReceiptRef, subject: str) -> None:
        if receipt.issuer_id != "host" or not self._receipts.verify(
            receipt.receipt_id, receipt.receipt_digest, subject
        ):
            raise MemoryPromotionError("trusted host receipt for exact subject required")

    def promote(
        self,
        *,
        workspace_id: str,
        task_id: str,
        run_id: str,
        memory: VerifiedBuildKnowledge,
        build_completion_receipt: ReceiptRef,
        diagnostic_receipt: ReceiptRef,
    ) -> tuple[ArtifactRef, ArtifactRef]:
        """Promote one evidence-backed statement, then verify its source template.

        Retry after interrupted projection is safe: immutable revisions and the
        deterministic journal event ID prevent duplicate knowledge.
        """
        if memory.memory_revision != 1 or memory.reusable_scope not in ("repository", "workspace"):
            raise MemoryPromotionError("memory requires initial revision and bounded reuse scope")
        if _REDACT.search(memory.summary):
            raise MemoryPromotionError("secret or physical-path content forbidden")
        build = self._load(memory.source_build_ref, BuildRecord)
        validation = self._load(memory.build_validation_ref, BuildValidationRecord)
        template = self._templates.load(memory.source_plan_template_ref)
        if not isinstance(build, BuildRecord) or not isinstance(validation, BuildValidationRecord):
            raise MemoryPromotionError("invalid Build evidence")
        if template.synthetic or (template.status is not TemplateStatus.CANDIDATE and not template.verified_by_build):
            raise MemoryPromotionError("accepted candidate template required")
        if build.task_id != task_id or build.run_id != run_id:
            raise MemoryPromotionError("Build task/run identity mismatch")
        if validation.task_id != task_id or validation.run_id != run_id:
            raise MemoryPromotionError("verification task/run identity mismatch")
        if validation.build_ref != memory.source_build_ref:
            raise MemoryPromotionError("verification not bound to source Build")
        lock = self._load(build.lock_ref, PackageLockReceipt)
        if not isinstance(lock, PackageLockReceipt):
            raise MemoryPromotionError("invalid source Package Lock")
        if (
            template.source_plan_ref != lock.frozen_spec_ref
            or template.source_audit_ref != lock.audit_ref
            or template.source_research_ref != lock.research_ref
        ):
            raise MemoryPromotionError("template lineage is not the verified Build lineage")
        self._verify_receipt(
            lock.receipt_ref,
            f"{lock.research_ref.artifact_digest}:{lock.audit_ref.artifact_digest}:{lock.frozen_spec_ref.artifact_digest}"
            + (f":{lock.tool_registry_ref.artifact_digest}" if lock.tool_registry_ref else ""),
        )
        admission = self._load(build.admission_ref, BuildAdmissionReceipt)
        if not isinstance(admission, BuildAdmissionReceipt):
            raise MemoryPromotionError("invalid source Build Admission")
        if admission.lock_receipt_ref != lock.receipt_ref:
            raise MemoryPromotionError("Build Admission does not reference source lock")
        if set(admission.authorized_action_ids) != {entry.action_id for entry in build.action_executions}:
            raise MemoryPromotionError("Build actions differ from authorized admission")
        self._verify_receipt(
            admission.receipt_ref,
            admission_receipt_subject(
                lock.receipt_ref,
                admission.authorized_action_ids,
                admission.authorized_tool_ids,
                admission.tool_registry_ref,
            ),
        )
        if not build.action_executions or any(
            entry.status is not BuildActionStatus.COMPLETED for entry in build.action_executions
        ):
            raise MemoryPromotionError("Build actions not completely successful")
        if any(step.status is not StepStatus.COMPLETED for step in build.step_results):
            raise MemoryPromotionError("Build steps not completely successful")
        if (
            not validation.criterion_results
            or not validation.e2e_results
            or any(
                result.outcome is not CriterionResult.PASS or not result.evidence_refs
                for result in validation.criterion_results
            )
            or any(
                result.outcome is not CriterionResult.PASS or result.exit_code != 0 for result in validation.e2e_results
            )
            or any(step.status is not StepStatus.COMPLETED for step in validation.step_results)
        ):
            raise MemoryPromotionError("independent Build verification did not pass")
        for evidence in memory.evidence_refs:
            if self._artifacts.get_digest(evidence.artifact_id, evidence.artifact_revision) != evidence.artifact_digest:
                raise MemoryPromotionError("unverified reusable statement evidence")
            self._artifacts.get_verified(evidence.artifact_id, evidence.artifact_revision)
        build_subject = f"build-execution-completed:{memory.source_build_ref.artifact_digest}"
        diagnostic_subject = f"build-diagnostic-valid:{memory.source_build_ref.artifact_digest}"
        verification_subject = (
            f"build-verification-passed:{memory.build_validation_ref.artifact_digest}:"
            f"{memory.source_build_ref.artifact_digest}"
        )
        approval_subject = (
            f"reusable-memory-approved:{memory.build_validation_ref.artifact_digest}:"
            f"{memory.source_plan_template_ref.artifact_digest}:{memory.memory_id}"
        )
        self._verify_receipt(build_completion_receipt, build_subject)
        self._verify_receipt(diagnostic_receipt, diagnostic_subject)
        self._verify_receipt(memory.verification_receipt_ref, verification_subject)
        self._verify_receipt(memory.approval_receipt_ref, approval_subject)

        # Fail before any memory side effect if the template was verified
        # against a different Build. Concurrent CAS is still independently
        # checked below and must be reconciled by the host on interruption.
        latest_template_revision = self._artifacts.latest_revision(memory.source_plan_template_ref.artifact_id)
        if latest_template_revision > memory.source_plan_template_ref.artifact_revision:
            current_digest = self._artifacts.get_digest(
                memory.source_plan_template_ref.artifact_id, latest_template_revision
            )
            if current_digest is None:
                raise MemoryPromotionError("missing latest template revision")
            current = self._templates.load(
                ArtifactRef(
                    artifact_id=memory.source_plan_template_ref.artifact_id,
                    artifact_revision=latest_template_revision,
                    artifact_digest=current_digest,
                    contract_id="plan_template",
                    contract_version="1.0",
                    serializer_profile=SERIALIZER_PROFILE,
                )
            )
            if (
                not current.verified_by_build
                or current.build_verification_receipt_ref != memory.verification_receipt_ref
            ):
                raise MemoryPromotionError("conflicting verified template revision")

        memory_artifact_id = f"build-memory:{workspace_id}:{memory.memory_id}"
        digest = self._artifacts.put_immutable(memory, memory_artifact_id, 1, "verified_build_memory", "1.0")
        memory_ref = ArtifactRef(
            artifact_id=memory_artifact_id,
            artifact_revision=1,
            artifact_digest=digest,
            contract_id="verified_build_memory",
            contract_version="1.0",
            serializer_profile=SERIALIZER_PROFILE,
        )
        self._journals.append_verified_memory(
            StageLogEvent(
                event_id=f"memory-promoted:{memory_artifact_id}",
                sequence=1,
                workspace_id=workspace_id,
                task_id=task_id,
                run_id=run_id,
                stage="mem",
                event="build_pattern_recorded",
                status="verified",
                summary=memory.summary,
                artifact_ref=f"{memory_ref.artifact_id}@{memory_ref.artifact_revision}",
                source_build_ref=f"{memory.source_build_ref.artifact_id}@{memory.source_build_ref.artifact_revision}",
                verification_receipt_ref=memory.verification_receipt_ref.receipt_id,
                reusable_scope=memory.reusable_scope,
            ),
            receipts=self._receipts,
            verification_receipt_ref=memory.verification_receipt_ref,
            verification_subject=verification_subject,
            approval_receipt_ref=memory.approval_receipt_ref,
            approval_subject=approval_subject,
        )
        latest = self._artifacts.latest_revision(memory.source_plan_template_ref.artifact_id)
        if latest == memory.source_plan_template_ref.artifact_revision:
            promoted = PlanTemplate.model_validate(
                {
                    **template.model_dump(),
                    "template_version": latest + 1,
                    "status": "verified",
                    "verified_by_build": True,
                    "build_verification_receipt_ref": memory.verification_receipt_ref.model_dump(),
                }
            )
            rev, next_digest = self._artifacts.put_cas(
                promoted, memory.source_plan_template_ref.artifact_id, latest, "plan_template", "1.0"
            )
        else:
            rev = latest
            promoted = self._templates.load(
                ArtifactRef(
                    artifact_id=memory.source_plan_template_ref.artifact_id,
                    artifact_revision=rev,
                    artifact_digest=self._artifacts.get_digest(memory.source_plan_template_ref.artifact_id, rev) or "",
                    contract_id="plan_template",
                    contract_version="1.0",
                    serializer_profile=SERIALIZER_PROFILE,
                )
            )
            if (
                not promoted.verified_by_build
                or promoted.build_verification_receipt_ref != memory.verification_receipt_ref
            ):
                raise MemoryPromotionError("conflicting verified template revision")
            next_digest = self._artifacts.get_digest(memory.source_plan_template_ref.artifact_id, rev) or ""
        verified_ref = ArtifactRef(
            artifact_id=memory.source_plan_template_ref.artifact_id,
            artifact_revision=rev,
            artifact_digest=next_digest,
            contract_id="plan_template",
            contract_version="1.0",
            serializer_profile=SERIALIZER_PROFILE,
        )
        self._journals.append(
            StageLogEvent(
                event_id=f"plan-template-verified:{verified_ref.artifact_id}:{verified_ref.artifact_revision}",
                sequence=1,
                workspace_id=workspace_id,
                task_id=task_id,
                run_id=run_id,
                stage="plan",
                event="template_verified",
                status="verified",
                summary="Accepted Planning template verified by independent Build",
                template_ref=f"{verified_ref.artifact_id}@{verified_ref.artifact_revision}",
                verification_receipt_ref=memory.verification_receipt_ref.receipt_id,
            )
        )
        return memory_ref, verified_ref
