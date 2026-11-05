"""Host-owned accepted Planning template publication, without execution authority."""

from __future__ import annotations

from agent.contracts.common import ArtifactRef
from agent.contracts.plan_template import PlanTemplate, TemplateStatus
from agent.runtime.artifact_store import ArtifactStore
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE, digest_model
from agent.runtime.receipt_store import ReceiptStore


class PlanTemplateError(ValueError):
    pass


class PlanTemplateService:
    def __init__(self, artifacts: ArtifactStore, receipts: ReceiptStore) -> None:
        self._artifacts = artifacts
        self._receipts = receipts

    def _verify_source(self, ref: ArtifactRef) -> None:
        if self._artifacts.get_digest(ref.artifact_id, ref.artifact_revision) != ref.artifact_digest:
            raise PlanTemplateError("source artifact digest mismatch")
        self._artifacts.get_verified(ref.artifact_id, ref.artifact_revision)

    def publish_candidate(
        self,
        template: PlanTemplate,
        *,
        acceptance_receipt_id: str,
        acceptance_receipt_digest: str,
    ) -> ArtifactRef:
        """Publish only an accepted Plan as a candidate reusable pattern.

        Caller supplies an existing host-issued receipt bound to exact Plan digest.
        Candidate publication is not a Build verification or permission to execute.
        """
        if template.template_version != 1 or template.status is not TemplateStatus.CANDIDATE:
            raise PlanTemplateError("initial publication must be candidate revision one")
        for source in (template.source_plan_ref, template.source_audit_ref, template.source_research_ref):
            self._verify_source(source)
        subject = f"accepted-plan:{template.source_plan_ref.artifact_digest}"
        if not self._receipts.verify(acceptance_receipt_id, acceptance_receipt_digest, subject):
            raise PlanTemplateError("trusted accepted Plan receipt required")
        aid = f"plan-template:{template.template_id}"
        digest = self._artifacts.put_immutable(template, aid, template.template_version, "plan_template", "1.0")
        return ArtifactRef(
            artifact_id=aid,
            artifact_revision=template.template_version,
            artifact_digest=digest,
            contract_id="plan_template",
            contract_version="1.0",
            serializer_profile=SERIALIZER_PROFILE,
        )

    def load(self, ref: ArtifactRef) -> PlanTemplate:
        if ref.contract_id != "plan_template":
            raise PlanTemplateError("wrong template contract")
        self._verify_source(ref)
        template = PlanTemplate.model_validate_json(
            self._artifacts.get_verified(ref.artifact_id, ref.artifact_revision)
        )
        if digest_model(template) != ref.artifact_digest:
            raise PlanTemplateError("template bytes changed")
        return template
