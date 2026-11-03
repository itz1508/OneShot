"""Guardrail contracts -- blocking checks for stage input, tool calls, and stage output."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from agent.contracts.common import ContractModel, Sha256


class GuardrailDecision(StrEnum):
    """Three-valued guardrail decision with a review middle state."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_REVIEW = "require_review"


class GuardrailRequest(ContractModel):
    """Request for a guardrail check on a boundary-crossing action."""

    request_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    boundary: str = Field(min_length=1)
    subject_digest: Sha256
    policy_version: str = Field(min_length=1)


class GuardrailResult(ContractModel):
    """Result of a guardrail check with decision and check IDs."""

    request_id: str = Field(min_length=1)
    decision: GuardrailDecision
    policy_version: str = Field(min_length=1)
    check_ids: tuple[str, ...] = Field(min_length=1)
    reason: str = ""
    receipt_ref: str | None = None
