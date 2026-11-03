"""OneShot planning contracts extracted from the former models.py monolith.

Keep stage fields and validators compatible; YAML record templates remain intact.
"""

from __future__ import annotations

from typing import Any, Literal
from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .shared import (Checkpoint, RecordStatus, GapStatus, FixtureValidationStatus, ChaosApplicability, PlanApplicability, _is_filled)

# ---------------------------------------------------------------------------
# Plan record models
# ---------------------------------------------------------------------------


class AcceptanceCriterion(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    requirement_id: str
    expected_result: str
    oracle_ref: str | None = None


class Milestone(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    goal: str = ""
    files: list[Any] = Field(default_factory=list)
    steps: list[Any] = Field(default_factory=list)
    commands: list[Any] = Field(default_factory=list)
    expected_observations: list[Any] = Field(default_factory=list)
    status: str | None = None

    @model_validator(mode="after")
    def check_executable(self) -> Milestone:
        if not self.steps:
            raise ValueError(f"milestone {self.id}: missing steps")
        if not self.expected_observations:
            raise ValueError(f"milestone {self.id}: missing expected_observations")
        return self


class PlanImplementation(BaseModel):
    model_config = ConfigDict(extra="allow")

    proposed_final_tree_ref: str | None = None
    file_actions: list[Any] = Field(default_factory=list)
    milestones: list[Milestone] = Field(default_factory=list)
    dependencies: list[Any] = Field(default_factory=list)
    command_environment_ref: str | None = None
    rollback_or_recovery: str | None = None

    @model_validator(mode="after")
    def check_milestones_exist(self) -> PlanImplementation:
        if not self.milestones:
            raise ValueError("no executable milestones")
        if not _is_filled(self.rollback_or_recovery):
            raise ValueError("missing recovery guidance")
        return self


class ScannerCall(BaseModel):
    model_config = ConfigDict(extra="allow")

    at: str | None = None
    tool_ref: str | None = None
    scope_ref: str | None = None
    input_revision: int | None = None
    findings_ref: str | None = None
    receipt_ref: str | None = None
    outcome: Literal["passed", "failed", "not_checked"] = "not_checked"


class GapFinding(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    type: str | None = None
    severity: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    root_cause: str | None = None
    owner: str | None = None
    action: str | None = None
    status: Literal["open", "resolved", "false_positive", "deferred", "blocked"] = "open"
    fix_receipt_ref: str | None = None
    recheck_ref: str | None = None
    disposition_reason: str | None = None
    approval_ref: str | None = None

    @model_validator(mode="after")
    def check_status_rules(self) -> GapFinding:
        if self.status == "deferred" and self.severity == "critical":
            raise ValueError(f"critical finding {self.id} cannot be deferred")
        if self.status == "false_positive" and not (self.disposition_reason and self.evidence_refs):
            raise ValueError(f"false positive {self.id} needs justification and evidence")
        return self


class ClaimDecision(BaseModel):
    """Plan applicability decision bound to a single Research finding.

    One decision per source finding (enforced in cross-record validation).
    DO_NOT_USE forbids dependent Build steps; VALIDATE_FIRST gates them
    pending new evidence; USE admits them.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    source_finding_id: str
    applicability: PlanApplicability
    reason: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    affected_step_ids: list[str] = Field(default_factory=list)
    revision: int = Field(ge=1)
    recorded_at: str | None = None


class GapAnalysis(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: GapStatus = GapStatus.NOT_CHECKED
    scanner_calls: list[ScannerCall] = Field(default_factory=list)
    findings: list[GapFinding] = Field(default_factory=list)
    unresolved_critical_ids: list[str] = Field(default_factory=list)
    last_recheck_ref: str | None = None

    @model_validator(mode="after")
    def check_resolved(self) -> GapAnalysis:
        if self.status != GapStatus.RESOLVED:
            raise ValueError("gap analysis must be resolved")
        if not self.scanner_calls:
            raise ValueError("Scanner was not invoked")
        if self.unresolved_critical_ids:
            raise ValueError(f"unresolved critical gaps: {self.unresolved_critical_ids}")
        return self


class FixtureValidationChaos(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: FixtureValidationStatus = FixtureValidationStatus.NOT_CHECKED
    fixture_refs: list[str] = Field(default_factory=list)
    oracle_evidence_refs: list[str] = Field(default_factory=list)
    chaos_applicability: ChaosApplicability = ChaosApplicability.NOT_CHECKED
    chaos_case_refs: list[str] = Field(default_factory=list)
    chaos_exclusion_reason: str | None = None
    prebuild_validation_receipt_refs: list[str] = Field(default_factory=list)
    coverage_gaps: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_passed(self) -> FixtureValidationChaos:
        if self.status != FixtureValidationStatus.PASSED:
            raise ValueError("fixture validation not passed")
        if (
            not self.fixture_refs
            or not self.oracle_evidence_refs
            or not self.prebuild_validation_receipt_refs
        ):
            raise ValueError("fixtures/oracles not independently prevalidated")
        if self.chaos_applicability == ChaosApplicability.REQUIRED and not self.chaos_case_refs:
            raise ValueError("missing required chaos cases")
        if self.chaos_applicability == ChaosApplicability.NOT_APPLICABLE and not _is_filled(
            self.chaos_exclusion_reason
        ):
            raise ValueError("chaos exclusion not justified")
        if self.chaos_applicability not in (
            ChaosApplicability.REQUIRED,
            ChaosApplicability.NOT_APPLICABLE,
        ):
            raise ValueError("chaos applicability not decided")
        if any(isinstance(x, dict) and x.get("blocking") for x in self.coverage_gaps):
            raise ValueError("blocking fixture/chaos coverage gaps")
        return self


class PlanPurpose(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_outcome: str
    acceptance_criteria: list[AcceptanceCriterion] = Field(default_factory=list)
    assumptions: list[Any] = Field(default_factory=list)
    constraints: list[Any] = Field(default_factory=list)


class PlanResearchInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    record_ref: str | None = None
    record_id: str | None = None
    record_revision: int | None = None
    artifact_manifest_ref: str | None = None
    accepted_requirement_ids: list[str] = Field(default_factory=list)
    accepted_criterion_ids: list[str] = Field(default_factory=list)


class PlanRecord(BaseModel):
    """Pydantic model for the Plan contract record."""

    model_config = ConfigDict(extra="allow")

    kind: Literal["plan"] = "plan"
    task_id: str
    record_id: str
    revision: int = Field(ge=1)
    status: RecordStatus = RecordStatus.DRAFT
    updated_at: str | None = None

    research_input: PlanResearchInput
    purpose: PlanPurpose
    implementation: PlanImplementation
    gap_analysis: GapAnalysis
    fixture_validation_chaos: FixtureValidationChaos
    claim_decisions: list[ClaimDecision] = Field(default_factory=list)

    progress_log: list[Any] = Field(default_factory=list)
    decision_log: list[Any] = Field(default_factory=list)
    checkpoint: Checkpoint = Field(default_factory=Checkpoint)
    handoff: dict[str, Any] = Field(default_factory=lambda: {"to": "build", "ready": False})

    @field_validator("task_id", "record_id")
    @classmethod
    def not_placeholder(cls, v):
        if not _is_filled(v):
            raise ValueError("must not be empty or a placeholder")
        return v

    @model_validator(mode="after")
    def check_completion(self) -> PlanRecord:
        ready = self.handoff.get("ready")
        if self.status == RecordStatus.COMPLETE or ready is True:
            if not (ready is True and self.status == RecordStatus.COMPLETE):
                raise ValueError("complete status and handoff.ready must agree")
            if not self.progress_log:
                raise ValueError("no progress log")
            if not self.decision_log:
                raise ValueError("no decision log")
            if not self.updated_at:
                raise ValueError("missing UTC updated_at")
        return self


# ---------------------------------------------------------------------------
# Planning record models (migrated from Plan; legacy kind:plan compatible)
# ---------------------------------------------------------------------------


class TodoValidation(BaseModel):
    model_config = ConfigDict(extra="allow")

    method: str
    expected: str


class Todo(BaseModel):
    model_config = ConfigDict(extra="allow")

    todo_id: str
    requirement_ids: list[str] = Field(default_factory=list)
    action: str = ""
    target_paths: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    criterion_ids: list[str] = Field(default_factory=list)
    validation: TodoValidation | None = None


class AuthorizedTool(BaseModel):
    model_config = ConfigDict(extra="allow")

    tool_id: str
    version: str = ""
    allowed_paths: list[str] = Field(default_factory=list)


class BuildAdmission(BaseModel):
    """Verified receipt binding the accepted Planning revision, audit
    disposition, fixture/chaos evidence, authorized tools, and criteria.

    Required before Build stage entry. A SELECT choice alone is
    insufficient — this receipt is the authorization artifact.
    """

    model_config = ConfigDict(extra="allow")

    receipt_ref: str | None = None
    accepted_plan_revision: int = Field(ge=1)
    audit_disposition: Literal["SELECT", "UPDATE", "BLOCK", "REJECT"] = "SELECT"
    fixture_chaos_status: Literal["passed", "failed", "not_checked"] = "not_checked"
    unresolved_blockers: list[str] = Field(default_factory=list)
    authorized_tools: list[AuthorizedTool] = Field(default_factory=list)
    accepted_criterion_ids: list[str] = Field(default_factory=list)
    admission_receipt_ref: str | None = None

    @model_validator(mode="after")
    def check_admission(self) -> BuildAdmission:
        if self.audit_disposition in ("BLOCK", "REJECT"):
            raise ValueError(
                f"Build admission cannot proceed with audit disposition {self.audit_disposition}"
            )
        if self.fixture_chaos_status != "passed":
            raise ValueError(
                "Build admission requires fixture/chaos status 'passed'"
            )
        if self.unresolved_blockers:
            raise ValueError(
                f"Build admission has unresolved blockers: {self.unresolved_blockers}"
            )
        if not _is_filled(self.admission_receipt_ref):
            raise ValueError("Build admission requires admission_receipt_ref")
        return self


class PlanningRecord(BaseModel):
    """Pydantic model for the Planning contract record.

    Migrated from PlanRecord with additional fields for TODOs, criterion
    propagation, and Build admission. Legacy kind:plan records validate
    via PlanRecord; new records use kind:planning.
    """

    model_config = ConfigDict(extra="allow")

    kind: Literal["planning", "plan"] = "planning"
    task_id: str
    record_id: str
    revision: int = Field(ge=1)
    status: RecordStatus = RecordStatus.DRAFT
    updated_at: str | None = None

    research_input: PlanResearchInput
    todos: list[Todo] = Field(default_factory=list)
    purpose: PlanPurpose
    implementation: PlanImplementation
    gap_analysis: GapAnalysis
    fixture_validation_chaos: FixtureValidationChaos
    build_admission: BuildAdmission | None = None
    claim_decisions: list[ClaimDecision] = Field(default_factory=list)

    progress_log: list[Any] = Field(default_factory=list)
    decision_log: list[Any] = Field(default_factory=list)
    checkpoint: Checkpoint = Field(default_factory=Checkpoint)
    handoff: dict[str, Any] = Field(default_factory=lambda: {"to": "build", "ready": False})

    @field_validator("task_id", "record_id")
    @classmethod
    def not_placeholder(cls, v):
        if not _is_filled(v):
            raise ValueError("must not be empty or a placeholder")
        return v

    @model_validator(mode="after")
    def check_completion(self) -> PlanningRecord:
        ready = self.handoff.get("ready")
        if self.status == RecordStatus.COMPLETE or ready is True:
            if not (ready is True and self.status == RecordStatus.COMPLETE):
                raise ValueError("complete status and handoff.ready must agree")
            if not self.progress_log:
                raise ValueError("no progress log")
            if not self.decision_log:
                raise ValueError("no decision log")
            if not self.updated_at:
                raise ValueError("missing UTC updated_at")
        return self


