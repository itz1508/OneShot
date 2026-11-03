"""Planning Input Interface — host-owned consumer requirements."""

from __future__ import annotations

from pydantic import Field

from agent.contracts.common import (
    ArtifactRef,
    ContractModel,
    CriterionId,
    RequirementId,
)
from agent.contracts.host import ReceiptRef


class PlanningResearchInput(ContractModel):
    artifact: ArtifactRef
    validation_receipt: ReceiptRef
    handoff_receipt: ReceiptRef
    accepted_requirement_ids: tuple[RequirementId, ...] = Field(min_length=1)
    criterion_bindings: tuple[tuple[CriterionId, RequirementId], ...] = ()


class PlanningAuditInput(ContractModel):
    artifact: ArtifactRef
    package_receipt: ReceiptRef
    repository_identity_ref: str = Field(min_length=1)
    evidence_manifest_ref: str = Field(min_length=1)
    finding_ids: tuple[str, ...] = ()
    code_intent_ids: tuple[str, ...] = ()


class PlanningInput(ContractModel):
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    research: PlanningResearchInput
    audit_discovery: PlanningAuditInput
