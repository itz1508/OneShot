"""Shared immutable primitive types for all OneShot contracts.

No stage-specific contracts, stores, or IO. These are the stable
building blocks every stage contract depends on.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Type aliases with validation
Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
RequirementId = Annotated[str, Field(pattern=r"^REQ-[0-9]{3,}$")]
CriterionId = Annotated[str, Field(pattern=r"^AC-[0-9]{3,}$")]
EvidenceId = Annotated[str, Field(pattern=r"^EVD-[0-9]{3,}$")]
FindingId = Annotated[str, Field(pattern=r"^ADF-[0-9]{3,}$")]
AssessmentId = Annotated[str, Field(pattern=r"^ASM-[0-9]{3,}$")]
IssueId = Annotated[str, Field(pattern=r"^PLI-[0-9]{3,}$")]
ReviewId = Annotated[str, Field(pattern=r"^REV-[0-9]{3,}$")]
DecisionId = Annotated[str, Field(pattern=r"^DEC-[0-9]{3,}$")]


class ContractModel(BaseModel):
    """Frozen, strict base for every contract model.

    - ``extra="forbid"`` rejects unknown fields.
    - ``frozen=True`` makes instances immutable.
    - ``validate_default=True`` ensures defaults pass validation.
    """

    model_config = ConfigDict(extra="forbid", validate_default=True, frozen=True)


class StepStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    NOT_RUN = "not_run"
    SKIPPED = "skipped"


class DiagnosticStatus(StrEnum):
    """Tri-valued evidence reliability axis."""

    VALID = "valid"
    NOT_VALID = "not_valid"
    UNCERTAINTY = "uncertainty"


class ProposalState(StrEnum):
    """Lifecycle of proposed operations before/after admission."""

    PROPOSAL_ONLY = "proposal_only"
    REVIEW_REQUIRED = "review_required"
    APPROVED_FOR_APPLY = "approved_for_apply"
    NOT_APPROVED = "not_approved"
    ALREADY_APPLIED = "already_applied"
    IDEMPOTENT = "idempotent"
    MISSING_PARENT = "missing_parent"
    PROTECTED_SURFACE = "protected_surface"


class OperationState(StrEnum):
    """Internal operation lifecycle with in-flight and effect-uncertain states."""

    NOT_RUN = "not_run"
    IN_FLIGHT = "in_flight"
    EFFECT_UNCERTAIN = "effect_uncertain"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"

    @property
    def final_report_status(self) -> StepStatus:
        """Project internal OperationState to external StepStatus.

        ``in_flight`` has no final report; callers must not call this
        property on an in-flight operation.
        """
        if self is OperationState.EFFECT_UNCERTAIN:
            return StepStatus.BLOCKED
        if self is OperationState.IN_FLIGHT:
            raise ValueError("in_flight has no final report status")
        return StepStatus(self.value)


class SpecificationState(StrEnum):
    """Specification lifecycle gate."""

    CANDIDATE = "candidate"
    FROZEN = "frozen"
    BLOCKED = "blocked"


class CoverageStatus(StrEnum):
    """Requirement/criterion coverage tracking."""

    COVERED = "covered"
    BLOCKED = "blocked"
    NOT_RUN = "not_run"
    NOT_APPLICABLE = "not_applicable"


class CriteriaStatus(StrEnum):
    """Acceptance criteria readiness."""

    DEFINED = "defined"
    INCOMPLETE = "incomplete"
    BLOCKED = "blocked"


class ArtifactRef(ContractModel):
    """Reference to a content-addressed artifact in host storage."""

    artifact_id: str = Field(min_length=1)
    artifact_revision: int = Field(ge=1)
    artifact_digest: Sha256
    contract_id: str = Field(min_length=1)
    contract_version: str = Field(min_length=1)
    serializer_profile: str = Field(min_length=1)


class EvidenceRef(ContractModel):
    """Reference to evidence with content digest, locator, and host receipt."""

    evidence_id: EvidenceId
    content_digest: Sha256
    location: str = Field(min_length=1)
    description: str = ""
    observation: str = ""
    receipt_ref: str | None = None
    artifact_ref: str | None = None


class StepResult(ContractModel):
    """Result of a single step within a stage."""

    step_id: str = Field(min_length=1)
    status: StepStatus
    actual_result: str = ""
    reason: str | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()
    receipt_ref: str | None = None
    blocker: str | None = None
    recovery_ref: str | None = None
    resume_point: str | None = None

    @model_validator(mode="after")
    def check_outcome(self) -> StepResult:
        if self.status in (StepStatus.COMPLETED, StepStatus.FAILED):
            if not self.receipt_ref:
                raise ValueError("executed step missing receipt")
        else:
            if not self.reason:
                raise ValueError("non-executed step missing reason")
        if self.status is StepStatus.BLOCKED and not self.blocker:
            raise ValueError("blocked step missing blocker")
        return self


class UpstreamBinding(ContractModel):
    """Binds an upstream artifact to its validation and handoff receipts."""

    artifact: ArtifactRef
    validation_receipt_ref: str = Field(min_length=1)
    handoff_receipt_ref: str = Field(min_length=1)


class ArtifactEnvelope(ContractModel):
    """Envelope wrapping an artifact with provenance chain."""

    artifact_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    contract_id: str = Field(min_length=1)
    contract_version: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    upstream: tuple[UpstreamBinding, ...] = ()
