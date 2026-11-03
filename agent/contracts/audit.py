"""OneShot audit contracts extracted from the former models.py monolith.

Keep stage fields and validators compatible; YAML record templates remain intact.
"""

from __future__ import annotations

from typing import Any, Literal
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .shared import _is_filled

# ---------------------------------------------------------------------------
# Audit addon models (reusable evaluation, NOT a workflow stage)
# ---------------------------------------------------------------------------


class AuditOutcome(str, Enum):
    SELECT = "SELECT"
    UPDATE = "UPDATE"
    BLOCK = "BLOCK"
    REJECT = "REJECT"


class AuditTarget(BaseModel):
    """Exact target identity for an audit evaluation."""

    model_config = ConfigDict(extra="allow")

    output_id: str
    source_output_id: str | None = None
    input_id: str | None = None
    target_kind: str = ""
    target_record_id: str | None = None
    target_revision: int | None = None
    source_snapshot_ref: str | None = None


class AuditRubricCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    check_id: str
    description: str = ""
    weight: float = 1.0
    required: bool = True
    evidence_type: str | None = None


class AuditRubric(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: str = "1.0"
    checks: list[AuditRubricCheck] = Field(default_factory=list)
    score_range: dict[str, int] = Field(default_factory=lambda: {"min": 0, "max": 100})
    selection_threshold: float | None = None
    required_checks: list[str] = Field(default_factory=list)


class AuditFinding(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    check_id: str | None = None
    severity: Literal["blocker", "major", "minor"] = "minor"
    description: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    recommendation: str = ""
    status: Literal["open", "resolved", "deferred"] = "open"


class AuditRecord(BaseModel):
    """Reusable audit evaluation addon bound to exact output identity.

    Does NOT authorize workflow transitions. Reports findings and typed
    outcomes. The Planner interprets the outcome and the controller gates
    transitions through validate_pipeline + Task Management.
    """

    model_config = ConfigDict(extra="allow")

    kind: Literal["audit"] = "audit"
    task_id: str
    audit_id: str
    audit_revision: int = Field(ge=1)
    status: Literal["not_checked", "in_progress", "complete", "blocked"] = "not_checked"
    updated_at: str | None = None

    target: AuditTarget
    rubric: AuditRubric = Field(default_factory=AuditRubric)
    findings: list[AuditFinding] = Field(default_factory=list)

    outcome: AuditOutcome | None = None
    outcome_reason: str | None = None
    outcome_score: float | None = None

    receipts: list[Any] = Field(default_factory=list)
    auditor_ref: str | None = None
    audit_receipt_ref: str | None = None

    progress_log: list[Any] = Field(default_factory=list)

    @field_validator("task_id", "audit_id")
    @classmethod
    def not_placeholder(cls, v):
        if not _is_filled(v):
            raise ValueError("must not be empty or a placeholder")
        return v

    @model_validator(mode="after")
    def check_blocker_override(self) -> AuditRecord:
        if self.outcome == AuditOutcome.SELECT and self.outcome_score is not None:
            if self.selection_threshold_active() and self.outcome_score < self.rubric.selection_threshold:
                raise ValueError(
                    "SELECT outcome score below selection threshold"
                )
        if self.findings:
            blockers = [f for f in self.findings if f.severity == "blocker" and f.status == "open"]
            if blockers and self.outcome == AuditOutcome.SELECT:
                raise ValueError(
                    "SELECT outcome not permitted with open blocker findings"
                )
        return self

    def selection_threshold_active(self) -> bool:
        return self.rubric.selection_threshold is not None


