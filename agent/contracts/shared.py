"""OneShot shared contracts extracted from the former models.py monolith.

Keep stage fields and validators compatible; YAML record templates remain intact.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Shared types and helpers
# ---------------------------------------------------------------------------

EvidenceCheck = Callable[[str], bool]

_SHA256_RE = r"^[0-9a-f]{64}$"


class RecordStatus(str, Enum):
    DRAFT = "draft"
    IN_PROGRESS = "in_progress"
    FAILED = "failed"
    BLOCKED = "blocked"
    COMPLETE = "complete"


class ReviewCoverage(str, Enum):
    NOT_CHECKED = "not_checked"
    INCOMPLETE = "incomplete"
    SUFFICIENT = "sufficient"


class EvidenceGrounding(str, Enum):
    NOT_CHECKED = "not_checked"
    FAILED = "failed"
    PASSED = "passed"


class ReviewDisposition(str, Enum):
    NOT_CHECKED = "not_checked"
    RESEARCH_AGAIN = "research_again"
    NEEDS_USER = "needs_user"
    READY_FOR_PLAN = "ready_for_plan"


class FindingAssessment(str, Enum):
    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNCERTAIN = "uncertain"
    NOT_CHECKED = "not_checked"


class PlanApplicability(str, Enum):
    """Plan-stage decision about an externally sourced Research finding.

    USE                 — the finding is accepted as grounding for executable
                          Plan content.
    DO_NOT_USE          — the finding is retained (not deleted) but no
                          executable step may derive from it; dependent Build
                          steps are rejected at admission.
    VALIDATE_FIRST      — dependent Build steps are gated pending new evidence
                          and a subsequent accepted Plan revision; the finding
                          stays visible in Research.
    """

    USE = "USE"
    DO_NOT_USE = "DO_NOT_USE"
    VALIDATE_FIRST = "VALIDATE_FIRST"


class GapStatus(str, Enum):
    NOT_CHECKED = "not_checked"
    FINDINGS_OPEN = "findings_open"
    RECHECK_REQUIRED = "recheck_required"
    RESOLVED = "resolved"
    BLOCKED = "blocked"


class FixtureValidationStatus(str, Enum):
    NOT_CHECKED = "not_checked"
    FAILED = "failed"
    PASSED = "passed"
    BLOCKED = "blocked"


class ChaosApplicability(str, Enum):
    NOT_CHECKED = "not_checked"
    REQUIRED = "required"
    NOT_APPLICABLE = "not_applicable"


class OutcomeStatus(str, Enum):
    NOT_VERIFIED = "not_verified"
    FAILED = "failed"
    BLOCKED = "blocked"
    VERIFIED = "verified"


class ActionState(str, Enum):
    NONE = "none"
    PENDING = "pending"
    UNCERTAIN = "uncertain"
    COMPLETED = "completed"


class RetryDisposition(str, Enum):
    NOT_APPLICABLE = "not_applicable"
    SAFE_RETRY = "safe_retry"
    RECONCILE_FIRST = "reconcile_first"
    BLOCKED = "blocked"


def _is_filled(value: Any) -> bool:
    """Check that a string is non-empty and not a placeholder."""
    return isinstance(value, str) and bool(value.strip()) and not value.strip().startswith("<")


# ---------------------------------------------------------------------------
# Shared sub-models
# ---------------------------------------------------------------------------


class Checkpoint(BaseModel):
    """Checkpoint state for retry-safe execution."""

    model_config = ConfigDict(extra="allow")

    last_completed_step: str | None = None
    next_step: str | None = None
    action_id: str | None = None
    action_state: ActionState = ActionState.NONE
    action_receipt_ref: str | None = None
    retry_disposition: RetryDisposition = RetryDisposition.NOT_APPLICABLE
    source_snapshot_ref: str | None = None
    resume_notes: str | None = None

    @model_validator(mode="after")
    def check_uncertain_reconciled(self) -> Checkpoint:
        if self.action_state == ActionState.UNCERTAIN and self.retry_disposition not in (
            RetryDisposition.RECONCILE_FIRST,
            RetryDisposition.BLOCKED,
        ):
            raise ValueError("uncertain action must be reconciled before retry")
        if self.action_state == ActionState.COMPLETED and not _is_filled(self.action_id):
            raise ValueError("completed action lacks ID")
        return self


class Handoff(BaseModel):
    """Stage handoff with readiness and artifact references."""

    model_config = ConfigDict(extra="allow")

    ready: bool = False
    artifact_manifest_ref: str | None = None
    validation_receipt_ref: str | None = None
    # Additional handoff fields per stage (extra="allow" captures them)

