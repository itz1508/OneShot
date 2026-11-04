"""Reusable, versioned Planning cases; acceptance never implies Build success."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from agent.contracts.common import ArtifactRef, ContractModel
from agent.contracts.host import ReceiptRef


class TemplateStatus(StrEnum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"


class PlanTemplate(ContractModel):
    template_id: str = Field(min_length=1)
    template_version: int = Field(ge=1)
    title: str = Field(min_length=1)
    category: str = Field(min_length=1)
    source_plan_ref: ArtifactRef
    source_audit_ref: ArtifactRef
    source_research_ref: ArtifactRef
    matching_keywords: tuple[str, ...] = Field(min_length=1)
    applicable_conditions: tuple[str, ...] = Field(min_length=1)
    required_decisions: tuple[str, ...] = Field(min_length=1)
    action_pattern: tuple[str, ...] = Field(min_length=1)
    verification_pattern: tuple[str, ...] = Field(min_length=1)
    known_constraints: tuple[str, ...] = ()
    known_failure_modes: tuple[str, ...] = ()
    synthetic: bool = False
    status: TemplateStatus = TemplateStatus.CANDIDATE
    verified_by_build: bool = False
    build_verification_receipt_ref: ReceiptRef | None = None

    @model_validator(mode="after")
    def check_verification(self) -> PlanTemplate:
        if self.verified_by_build != (self.status is TemplateStatus.VERIFIED):
            raise ValueError("verified status and verified_by_build must agree")
        if self.verified_by_build != (self.build_verification_receipt_ref is not None):
            raise ValueError("verified template requires Build verification receipt")
        if self.synthetic and self.verified_by_build:
            raise ValueError("synthetic template cannot claim a verified Build")
        return self
