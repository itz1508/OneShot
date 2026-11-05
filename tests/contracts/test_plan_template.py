"""Accepted Planning templates have provenance and never imply verified Build."""

import pytest
from pydantic import BaseModel, ValidationError

from agent.contracts.common import ArtifactRef
from agent.contracts.plan_template import PlanTemplate, TemplateStatus
from agent.runtime.artifact_store import ArtifactStore
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE
from agent.runtime.plan_templates import PlanTemplateError, PlanTemplateService
from agent.runtime.receipt_store import ReceiptStore


class Evidence(BaseModel):
    text: str


def stored(artifacts, artifact_id):
    digest = artifacts.put_immutable(Evidence(text=artifact_id), artifact_id, 1, "example", "1.0")
    return ArtifactRef(
        artifact_id=artifact_id,
        artifact_revision=1,
        artifact_digest=digest,
        contract_id="example",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )


def template(artifacts):
    return PlanTemplate(
        template_id="registry",
        template_version=1,
        title="Tool registry",
        category="integration",
        source_plan_ref=stored(artifacts, "plan"),
        source_audit_ref=stored(artifacts, "audit"),
        source_research_ref=stored(artifacts, "research"),
        matching_keywords=("registry",),
        applicable_conditions=("host owns admission",),
        required_decisions=("pinned tools",),
        action_pattern=("compile actions",),
        verification_pattern=("run E2E",),
    )


def test_candidate_publication_requires_exact_accepted_plan(tmp_path):
    artifacts, receipts = ArtifactStore(tmp_path), ReceiptStore(tmp_path)
    service = PlanTemplateService(artifacts, receipts)
    entry = template(artifacts)
    with pytest.raises(PlanTemplateError, match="accepted Plan"):
        service.publish_candidate(entry, acceptance_receipt_id="missing", acceptance_receipt_digest="0" * 64)
    _, digest = receipts.issue_verified("accepted", "host", f"accepted-plan:{entry.source_plan_ref.artifact_digest}")
    ref = service.publish_candidate(entry, acceptance_receipt_id="accepted", acceptance_receipt_digest=digest)
    assert service.load(ref).status is TemplateStatus.CANDIDATE
    assert not service.load(ref).verified_by_build


def test_unverified_and_synthetic_claims_rejected(tmp_path):
    entry = template(ArtifactStore(tmp_path))
    with pytest.raises(ValidationError, match="Build verification receipt"):
        PlanTemplate.model_validate({**entry.model_dump(), "status": "verified", "verified_by_build": True})
    with pytest.raises(ValidationError):
        PlanTemplate.model_validate({**entry.model_dump(), "verified_by_build": True})
