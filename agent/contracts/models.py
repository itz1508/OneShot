"""Pydantic v2 models for OneShot Research/Plan/Build contract records.

These models mirror the YAML schemas in research.yaml, plan.yaml, build.yaml
and the validation rules in check_contracts.py. They provide structured
validation with typed errors instead of the manual string-based checks.

Usage:
    from agent.contracts.models import ResearchRecord, PlanRecord, BuildRecord

    # Validate a single record (structural + type checks)
    try:
        research = ResearchRecord.model_validate(data)
    except ValidationError as e:
        print(e)

    # Cross-record validation with evidence resolution
    from agent.contracts.models import validate_pipeline
    errors = validate_pipeline(research_data, plan_data, build_data,
                               resolve=my_evidence_resolver)

Note: Evidence reference resolution (content-addressed SHA-256 checks) is a
runtime concern and is NOT enforced by Pydantic field validators. Use
validate_pipeline() for cross-record and evidence checks.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Shared types and helpers
# ---------------------------------------------------------------------------

EvidenceCheck = Callable[[str], bool]


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


# ---------------------------------------------------------------------------
# Research record models
# ---------------------------------------------------------------------------


class Requirement(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    statement: str = ""
    authority_ref: str | None = None
    scope: Literal["in_scope", "out_of_scope"] = "in_scope"

    @field_validator("authority_ref")
    @classmethod
    def authority_not_placeholder(cls, v):
        if v is not None and not _is_filled(v):
            raise ValueError("authority_ref must not be a placeholder")
        return v


class ResearchSource(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    location: str
    revision_or_hash: str
    authority: str | None = None
    inspected_at: str | None = None
    evidence_ref: str | None = None


class Finding(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    claim: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    assessment: FindingAssessment = FindingAssessment.NOT_CHECKED
    limitations: str | None = None


class Contradiction(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    competing_evidence_refs: list[str] = Field(default_factory=list)
    disposition: Literal["resolved", "unresolved", "not_checked"] = "not_checked"
    resolution_ref: str | None = None


class Uncertainty(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    impact: str | None = None
    owner: str | None = None
    researchable: bool | None = None
    resolution: str | None = None
    blocking: bool = False


class ResearchPurpose(BaseModel):
    model_config = ConfigDict(extra="allow")

    user_outcome: str
    original_request_ref: str | None = None
    accepted_requirements: list[Requirement] = Field(default_factory=list)
    scope: list[Any] = Field(default_factory=list)
    constraints: list[Any] = Field(default_factory=list)
    superseded_requirements: list[Any] = Field(default_factory=list)


class ResearchSearch(BaseModel):
    model_config = ConfigDict(extra="allow")

    todo_search_ref: str | None = None
    questions: list[Any] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    uncertainties: list[Uncertainty] = Field(default_factory=list)


class RequirementTrace(BaseModel):
    model_config = ConfigDict(extra="allow")

    requirement_id: str
    finding_ids: list[str] = Field(default_factory=list)
    fixture_ids: list[str] = Field(default_factory=list)
    criterion_ids: list[str] = Field(default_factory=list)
    disposition: str | None = None


class ResearchOutputs(BaseModel):
    model_config = ConfigDict(extra="allow")

    evidence_refs: list[str] = Field(default_factory=list)
    candidate_plan_ref: str | None = None
    fixture_refs: list[str] = Field(default_factory=list)
    success_criteria_refs: list[str] = Field(default_factory=list)
    requirement_trace: list[RequirementTrace] = Field(default_factory=list)


class ResearchReview(BaseModel):
    model_config = ConfigDict(extra="allow")

    coverage: ReviewCoverage = ReviewCoverage.NOT_CHECKED
    evidence_grounding: EvidenceGrounding = EvidenceGrounding.NOT_CHECKED
    unsupported_claims: list[Any] = Field(default_factory=list)
    unresolved_issues: list[Any] = Field(default_factory=list)
    blockers: list[Any] = Field(default_factory=list)
    disposition: ReviewDisposition = ReviewDisposition.NOT_CHECKED
    review_receipt_ref: str | None = None


class ResearchRecord(BaseModel):
    """Pydantic model for the Research contract record."""

    model_config = ConfigDict(extra="allow")

    kind: Literal["research"] = "research"
    task_id: str
    record_id: str
    revision: int = Field(ge=1)
    status: RecordStatus = RecordStatus.DRAFT
    updated_at: str | None = None

    purpose: ResearchPurpose
    workspace: dict[str, Any] = Field(default_factory=dict)
    search: ResearchSearch = Field(default_factory=ResearchSearch)
    outputs: ResearchOutputs = Field(default_factory=ResearchOutputs)
    review: ResearchReview = Field(default_factory=ResearchReview)

    progress_log: list[Any] = Field(default_factory=list)
    decision_log: list[Any] = Field(default_factory=list)
    checkpoint: Checkpoint = Field(default_factory=Checkpoint)

    handoff: dict[str, Any] = Field(default_factory=lambda: {"to": "plan", "ready": False})

    @field_validator("task_id", "record_id")
    @classmethod
    def not_placeholder(cls, v):
        if not _is_filled(v):
            raise ValueError("must not be empty or a placeholder")
        return v

    @model_validator(mode="after")
    def check_completion(self) -> ResearchRecord:
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
# Build record models
# ---------------------------------------------------------------------------


class BuildPlanInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    record_ref: str | None = None
    record_id: str | None = None
    record_revision: int | None = None
    artifact_manifest_ref: str | None = None
    accepted_milestone_ids: list[str] = Field(default_factory=list)
    accepted_criterion_ids: list[str] = Field(default_factory=list)


class CommandReceipt(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    command: str
    cwd: str
    exit_code: int
    stdout_ref: str | None = None
    stderr_ref: str | None = None
    receipt_ref: str | None = None
    at: str | None = None


class MilestoneResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    status: Literal["passed", "failed", "blocked", "not_run"] = "not_run"
    changed_files: list[str] = Field(default_factory=list)
    command_receipts: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)


class BuildExecution(BaseModel):
    model_config = ConfigDict(extra="allow")

    workspace_snapshot_ref: str | None = None
    environment_ref: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    milestone_results: list[MilestoneResult] = Field(default_factory=list)
    changes: list[Any] = Field(default_factory=list)
    command_receipts: list[CommandReceipt] = Field(default_factory=list)
    artifact_manifest_ref: str | None = None
    cleanup: list[Any] = Field(default_factory=list)


class ImplementationValidation(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Literal["not_run", "failed", "passed", "blocked"] = "not_run"
    checks: list[Any] = Field(default_factory=list)
    regressions: list[Any] = Field(default_factory=list)


class E2ECase(BaseModel):
    model_config = ConfigDict(extra="allow")

    fixture_ref: str | None = None
    expected_ref: str | None = None
    observed_ref: str | None = None
    receipt_ref: str | None = None
    status: Literal["passed", "failed", "blocked", "not_run"] = "not_run"


class ChaosCase(BaseModel):
    model_config = ConfigDict(extra="allow")

    chaos_ref: str | None = None
    injected_fault: str | None = None
    expected_recovery: str | None = None
    observed_ref: str | None = None
    receipt_ref: str | None = None
    status: Literal["passed", "failed", "blocked", "not_run"] = "not_run"


class IndependentResultCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    criterion_id: str | None = None
    expected_ref: str | None = None
    observed_ref: str | None = None
    receipt_ref: str | None = None
    status: Literal["passed", "failed", "blocked", "not_run"] = "not_run"


class PostBuildE2E(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Literal["not_run", "failed", "passed", "blocked"] = "not_run"
    real_entrypoint_ref: str | None = None
    environment_ref: str | None = None
    cases: list[E2ECase] = Field(default_factory=list)
    chaos_cases: list[ChaosCase] = Field(default_factory=list)
    independent_result_checks: list[IndependentResultCheck] = Field(default_factory=list)
    coverage_gaps: list[Any] = Field(default_factory=list)


class IssuesAndCorrections(BaseModel):
    model_config = ConfigDict(extra="allow")

    findings: list[Any] = Field(default_factory=list)
    gap_fix_receipt_refs: list[str] = Field(default_factory=list)
    revalidation_receipt_refs: list[str] = Field(default_factory=list)
    blockers: list[Any] = Field(default_factory=list)


class Outcome(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: OutcomeStatus = OutcomeStatus.NOT_VERIFIED
    user_visible_result_ref: str | None = None
    criterion_results: list[Any] = Field(default_factory=list)
    remaining_limitations: list[Any] = Field(default_factory=list)
    summary: str | None = None


class ManifestBinding(BaseModel):
    """G07 — immutable binding of a Build attempt to the records,
    detectors, fixtures, and receipts it was authorised against.

    Required at COMPLETE Build status; omitted (or empty) at DRAFT /
    IN_PROGRESS. `validate_pipeline` cross-checks `plan_revision` and
    `research_revision` against the sibling records' current revisions,
    so a Build attempt pinned to a stale Plan or stale Research is
    rejected before it can be reported VERIFIED.
    """

    model_config = ConfigDict(extra="allow")

    task_id: str
    research_revision: int = Field(ge=1)
    plan_revision: int = Field(ge=1)
    scanner_identity: str
    detector_identities: dict[str, str] = Field(default_factory=dict)
    fixture_oracle_sha: str
    oracle_revision: int = Field(ge=1)
    build_receipt_sha: str

    @field_validator("task_id", "scanner_identity", "fixture_oracle_sha", "build_receipt_sha")
    @classmethod
    def not_placeholder(cls, v):
        if not _is_filled(v):
            raise ValueError("manifest field must not be empty or a placeholder")
        # G07 reopen (reviewer finding on 9d2ce25): reject the specific
        # placeholder literals the previous build_plan fallback emitted,
        # so a stored manifest cannot carry them even if a legacy caller
        # tries to resurrect them.
        if v in {"unknown", "no_oracle_module"}:
            raise ValueError(
                f"manifest placeholder literal {v!r} is not an acceptable "
                "identity. Compute the real sha-256 before binding."
            )
        return v

    @field_validator("detector_identities")
    @classmethod
    def detector_identities_no_empty(cls, v):
        # G07 reopen (reviewer finding): detector_identities would
        # previously accept an empty string per detector (satisfying the
        # non-empty-field check at the dict level while leaving the
        # entry itself unbound). Every value must be a non-empty, non-
        # placeholder sha so each detector is pinned.
        if not isinstance(v, dict):
            raise ValueError("detector_identities must be a dict")
        if not v:
            raise ValueError(
                "detector_identities must bind at least one detector"
            )
        for tool_ref, ident in v.items():
            if not _is_filled(ident):
                raise ValueError(
                    f"detector_identities[{tool_ref!r}] must be a non-empty sha"
                )
            if ident in {"unknown", "no_oracle_module"}:
                raise ValueError(
                    f"detector_identities[{tool_ref!r}] placeholder literal "
                    f"{ident!r} is not an acceptable identity"
                )
        return v


class BuildRecord(BaseModel):
    """Pydantic model for the Build contract record."""

    model_config = ConfigDict(extra="allow")

    kind: Literal["build"] = "build"
    task_id: str
    record_id: str
    revision: int = Field(ge=1)
    status: RecordStatus = RecordStatus.DRAFT
    updated_at: str | None = None

    plan_input: BuildPlanInput
    execution: BuildExecution
    implementation_validation: ImplementationValidation
    post_build_e2e: PostBuildE2E
    issues_and_corrections: IssuesAndCorrections
    outcome: Outcome
    manifest_binding: ManifestBinding | None = None

    progress_log: list[Any] = Field(default_factory=list)
    decision_log: list[Any] = Field(default_factory=list)
    checkpoint: Checkpoint = Field(default_factory=Checkpoint)
    handoff: dict[str, Any] = Field(default_factory=lambda: {"to": "complete", "ready": False})

    @field_validator("task_id", "record_id")
    @classmethod
    def not_placeholder(cls, v):
        if not _is_filled(v):
            raise ValueError("must not be empty or a placeholder")
        return v

    @model_validator(mode="after")
    def check_completion(self) -> BuildRecord:
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
            # Build-specific completion checks (mirror check_contracts L291, L301, L307, L342)
            if not self.execution.command_receipts:
                raise ValueError("no executed command receipts")
            if self.implementation_validation.status != "passed":
                raise ValueError("implementation validation not passed")
            if self.post_build_e2e.status != "passed":
                raise ValueError("post-Build E2E not passed")
            if self.outcome.status != OutcomeStatus.VERIFIED:
                raise ValueError("outcome not verified")
            # G07 — a verified Build must carry a complete manifest.
            if self.manifest_binding is None:
                raise ValueError("missing manifest_binding on complete build")
        return self


# ---------------------------------------------------------------------------
# Cross-record validation (mirrors check_contracts.validate_records)
# ---------------------------------------------------------------------------


def _check_imperative_invariants(
    research: dict[str, Any],
    plan: dict[str, Any],
    build: dict[str, Any],
    r_complete: bool,
    p_complete: bool,
    b_complete: bool,
) -> list[str]:
    """Imperative cross-record invariants not captured by Pydantic structure.

    Each check emits an error string containing one semantic phrase callers
    (and the migrated check_contracts tests) assert on via substring match.
    Phrases produced here:

      - "trace coverage": research requirement_trace must cover every
        in-scope accepted requirement.
      - "unsupported finding": a research finding whose assessment is not
        'supported' must still have evidence_refs.
      - "planned fixtures not covered": plan's fixture_validation_chaos must
        reference non-empty fixture_refs when complete.
      - "Scanner result stale": the last scanner_call's input_revision must
        equal plan.revision.
      - "missing required chaos": chaos_applicability='required' needs
        chaos_case_refs.
      - "real E2E": build.post_build_e2e must include at least one real
        E2E case.
      - "actual user result": build.outcome must carry an independently
        validated user_visible_result_ref.
      - "duplicate IDs": no stage may contain duplicate IDs within a
        single collection.
      - "unfinished checkpoint": any stage's checkpoint cannot be left
        pending/uncertain while that stage is complete.
    """
    errors: list[str] = []

    def _duplicates(rows, name: str) -> None:
        if not isinstance(rows, list):
            return
        ids = [row.get("id") for row in rows if isinstance(row, dict) and "id" in row]
        if len(ids) != len(set(ids)):
            errors.append(f"{name}: duplicate IDs")

    def _unfinished(record: dict, stage: str, complete: bool) -> None:
        if not complete:
            return
        cp = record.get("checkpoint") or {}
        if cp.get("action_state") in ("pending", "uncertain"):
            # 'uncertain' already errors in Pydantic Checkpoint validator when
            # retry_disposition is not 'not_applicable'; add the shorter
            # 'unfinished checkpoint' phrasing for completeness.
            errors.append(f"{stage}: unfinished checkpoint")

    # Research invariants
    if r_complete:
        purpose = research.get("purpose") or {}
        reqs = [
            r
            for r in (purpose.get("accepted_requirements") or [])
            if isinstance(r, dict) and r.get("scope") == "in_scope"
        ]
        _duplicates(purpose.get("accepted_requirements"), "research.requirements")

        search = research.get("search") or {}
        findings = search.get("findings") or []
        _duplicates(findings, "research.findings")
        for f in findings:
            if not isinstance(f, dict):
                continue
            if f.get("assessment") != "supported":
                # Gate B04: a plan DO_NOT_USE or VALIDATE_FIRST decision
                # retains an unsupported finding without blocking Research.
                # The finding itself MUST still carry evidence_refs — otherwise
                # it is noise, not a retained claim.
                fid = f.get("id")
                decisions = plan.get("claim_decisions") or []
                bound = [
                    d
                    for d in decisions
                    if isinstance(d, dict)
                    and d.get("source_finding_id") == fid
                    and d.get("applicability") in ("DO_NOT_USE", "VALIDATE_FIRST")
                ]
                has_evidence = bool(f.get("evidence_refs"))
                if not bound or not has_evidence:
                    reason = (
                        "missing evidence_refs"
                        if not has_evidence
                        else "no plan DO_NOT_USE/VALIDATE_FIRST decision"
                    )
                    errors.append(f"research: unsupported finding {fid} — {reason}")

        outputs = research.get("outputs") or {}
        trace = outputs.get("requirement_trace") or []
        traced_ids = {t.get("requirement_id") for t in trace if isinstance(t, dict)}
        req_ids = {r.get("id") for r in reqs}
        if traced_ids != req_ids:
            errors.append("research: requirement trace coverage mismatch")

        _unfinished(research, "research", True)

    # Plan invariants
    if p_complete:
        gap = plan.get("gap_analysis") or {}
        scanner_calls = gap.get("scanner_calls") or []
        _duplicates(scanner_calls, "plan.scanner_calls")
        if scanner_calls:
            last = scanner_calls[-1]
            if isinstance(last, dict) and last.get("input_revision") != plan.get("revision"):
                errors.append("plan: Scanner result stale after revision")

        # Every non-false_positive gap finding needs a fix receipt and a recheck
        # receipt. Phrases "<id>.fix" / "<id>.recheck" match the retired
        # check_contracts assertions.
        for f in gap.get("findings") or []:
            if not isinstance(f, dict):
                continue
            fid = f.get("id")
            if f.get("status") in ("open", "resolved") and not f.get("fix_receipt_ref"):
                errors.append(f"plan.gap.{fid}.fix: missing fix receipt")
            if f.get("status") == "resolved" and not f.get("recheck_receipt_ref"):
                errors.append(f"plan.gap.{fid}.recheck: missing Scanner recheck receipt")

        fix = plan.get("fixture_validation_chaos") or {}
        if not (fix.get("fixture_refs") or []):
            errors.append("plan: planned fixtures not covered")
        if fix.get("chaos_applicability") == "required" and not (fix.get("chaos_case_refs") or []):
            errors.append("plan: missing required chaos cases")

        impl = plan.get("implementation") or {}
        _duplicates(impl.get("milestones"), "plan.milestones")
        _duplicates(plan.get("purpose", {}).get("acceptance_criteria"), "plan.acceptance_criteria")

        _unfinished(plan, "plan", True)

    # Build invariants
    if b_complete:
        execution = build.get("execution") or {}
        _duplicates(execution.get("command_receipts"), "build.command_receipts")

        e2e = build.get("post_build_e2e") or {}
        cases = e2e.get("cases") or []
        if not cases:
            errors.append("build: missing/failing real E2E cases")
        else:
            # Planned fixtures must each be referenced from an E2E case.
            planned = set()
            if p_complete:
                planned = set(
                    (plan.get("fixture_validation_chaos") or {}).get("fixture_refs") or []
                )
            exercised = {c.get("fixture_ref") for c in cases if isinstance(c, dict)}
            missing = planned - exercised
            if missing:
                errors.append(
                    f"build: planned fixtures not covered by post-Build E2E ({sorted(missing)!r})"
                )

        outcome = build.get("outcome") or {}
        if not outcome.get("user_visible_result_ref"):
            errors.append("build: actual user result not independently validated")
        # Independent result checks are the second half of "actual user result":
        # without them the user-visible result is not independently validated.
        if not (e2e.get("independent_result_checks") or []):
            errors.append("build: actual user result not independently validated by E2E")

        _unfinished(build, "build", True)

        # G07 — manifest-binding cross-record consistency.
        manifest = build.get("manifest_binding")
        if manifest is None:
            errors.append("build: missing manifest_binding (G07)")
        elif isinstance(manifest, dict):
            if manifest.get("task_id") and manifest["task_id"] != build.get("task_id"):
                errors.append(
                    f"build.manifest_binding.task_id mismatch: "
                    f"{manifest['task_id']!r} != {build.get('task_id')!r}"
                )
            if p_complete and manifest.get("plan_revision") not in (
                plan.get("revision"),
                None,
            ):
                errors.append(
                    f"build.manifest_binding.plan_revision mismatch: "
                    f"{manifest['plan_revision']!r} != {plan.get('revision')!r}"
                )
            if r_complete and manifest.get("research_revision") not in (
                research.get("revision"),
                None,
            ):
                errors.append(
                    f"build.manifest_binding.research_revision mismatch: "
                    f"{manifest['research_revision']!r} != "
                    f"{research.get('revision')!r}"
                )
            # Required scalar manifest fields must be present and non-empty.
            for key in (
                "scanner_identity",
                "fixture_oracle_sha",
                "build_receipt_sha",
            ):
                val = manifest.get(key)
                if not val or (isinstance(val, str) and not val.strip()):
                    errors.append(f"build.manifest_binding.{key}: missing or empty")

    # Gate B02-B08: Plan applicability decision cross-record checks.
    decisions = plan.get("claim_decisions") or []
    if decisions:
        # (a) duplicate decision IDs within the Plan.
        _duplicates(decisions, "plan.claim_decisions")

        # (b) at most one decision per source finding.
        seen_findings: dict[str, str] = {}
        for d in decisions:
            if not isinstance(d, dict):
                continue
            fid = d.get("source_finding_id")
            if not isinstance(fid, str):
                continue
            if fid in seen_findings:
                errors.append(
                    f"plan.claim_decisions: one per finding ({fid}) — "
                    f"ids {seen_findings[fid]} and {d.get('id')}"
                )
            else:
                seen_findings[fid] = d.get("id") or "?"

        # (c) each decision must reference an existing finding on Research.
        research_findings = {
            f.get("id")
            for f in (research.get("search") or {}).get("findings") or []
            if isinstance(f, dict)
        }
        plan_milestone_ids = {
            m.get("id")
            for m in (plan.get("implementation") or {}).get("milestones") or []
            if isinstance(m, dict)
        }
        for d in decisions:
            if not isinstance(d, dict):
                continue
            did = d.get("id") or "?"
            fid = d.get("source_finding_id")
            if fid not in research_findings:
                errors.append(f"plan.decision {did}: unknown finding {fid}")
            for sid in d.get("affected_step_ids") or []:
                if sid not in plan_milestone_ids:
                    errors.append(f"plan.decision {did}: unknown step {sid}")

        # (d) Build admission: a milestone accepted by the Build whose
        # provenance includes a DO_NOT_USE or VALIDATE_FIRST decision is
        # rejected. We treat `plan_input.accepted_milestone_ids` as the
        # Build's provenance claim; any decision whose `affected_step_ids`
        # names an accepted milestone blocks it.
        accepted_milestones = set(
            (build.get("plan_input") or {}).get("accepted_milestone_ids") or []
        )
        if accepted_milestones:
            for d in decisions:
                if not isinstance(d, dict):
                    continue
                mode = d.get("applicability")
                if mode not in ("DO_NOT_USE", "VALIDATE_FIRST"):
                    continue
                for sid in d.get("affected_step_ids") or []:
                    if sid in accepted_milestones:
                        errors.append(f"build: {mode} blocks step {sid} (decision {d.get('id')})")
    return errors


def validate_pipeline(
    research: dict[str, Any],
    plan: dict[str, Any],
    build: dict[str, Any],
    resolve: EvidenceCheck | None = None,
) -> list[str]:
    """Validate all three records with cross-record and evidence checks.

    Returns a list of error strings (empty if valid). This complements the
    Pydantic structural validation with cross-record invariants that
    require comparing fields across records and resolving evidence refs.

    Args:
        research: Research record dict
        plan: Plan record dict
        build: Build record dict
        resolve: Optional evidence resolver callable

    Example::

        errors = validate_pipeline(r_data, p_data, b_data,
                                   resolve=lambda ref: os.path.exists(ref))
        if errors:
            print("Validation errors:", errors)
    """
    errors: list[str] = []

    # Structural validation via Pydantic (collect, don't raise)
    research_model: ResearchRecord | None = None
    plan_model: PlanRecord | None = None
    build_model: BuildRecord | None = None

    try:
        research_model = ResearchRecord.model_validate(research)
    except Exception as e:
        errors.extend(_canonicalize_error(x) for x in _format_pydantic_errors(e, "research"))

    try:
        plan_model = PlanRecord.model_validate(plan)
    except Exception as e:
        errors.extend(_canonicalize_error(x) for x in _format_pydantic_errors(e, "plan"))

    try:
        build_model = BuildRecord.model_validate(build)
    except Exception as e:
        errors.extend(_canonicalize_error(x) for x in _format_pydantic_errors(e, "build"))

    # Handoff destination checks
    handoff_dests = {"research": "plan", "plan": "build", "build": "complete"}
    for kind, record in [("research", research), ("plan", plan), ("build", build)]:
        to = record.get("handoff", {}).get("to")
        if to != handoff_dests[kind]:
            errors.append(
                f"{kind}: invalid handoff destination (expected {handoff_dests[kind]}, got {to})"
            )

    # Task ID consistency
    task_ids = {r.get("task_id") for r in [research, plan, build]}
    if len(task_ids) != 1:
        errors.append("task_id mismatch across records")

    # Completion ordering
    r_complete = research_model is not None and research.get("status") == "complete"
    p_complete = plan_model is not None and plan.get("status") == "complete"
    b_complete = build_model is not None and build.get("status") == "complete"

    # Imperative invariants run on the raw dict, so they fire even when
    # Pydantic rejected the structural shape (the test's expected phrases
    # must still surface in that case). Gate on declared status, not on
    # structural validity, so a complete-but-malformed record still gets
    # the semantic diagnostics it needs.
    r_declared = research.get("status") == "complete"
    p_declared = plan.get("status") == "complete"
    b_declared = build.get("status") == "complete"
    errors.extend(
        _check_imperative_invariants(research, plan, build, r_declared, p_declared, b_declared)
    )
    if not r_complete and (p_complete or b_complete):
        errors.append("downstream complete while Research not ready")
    if not p_complete and b_complete:
        errors.append("Build complete while Plan not ready")

    # Cross-record identity checks
    if r_complete and p_complete:
        ri = plan.get("research_input", {})
        if ri.get("record_id") != research.get("record_id"):
            errors.append("plan: Research identity mismatch")
        if ri.get("record_revision") != research.get("revision"):
            errors.append("plan: stale Research revision")
        if ri.get("artifact_manifest_ref") != research.get("handoff", {}).get(
            "artifact_manifest_ref"
        ):
            errors.append("plan: Research manifest changed")

    if p_complete and b_complete:
        pi = build.get("plan_input", {})
        if pi.get("record_id") != plan.get("record_id"):
            errors.append("build: Plan identity mismatch")
        if pi.get("record_revision") != plan.get("revision"):
            errors.append("build: stale Plan revision")
        if pi.get("artifact_manifest_ref") != plan.get("handoff", {}).get("artifact_manifest_ref"):
            errors.append("build: Plan manifest changed")

    # Evidence resolution checks — fail closed when resolve is None
    if resolve is None and (r_complete or p_complete or b_complete):
        errors.append("no evidence resolver configured — completed records require resolution")
    elif resolve is not None:
        errors.extend(
            _check_evidence_refs(
                research,
                plan,
                build,
                resolve,
                r_complete,
                p_complete,
                b_complete,
            )
        )

    return errors


def _format_pydantic_errors(exc: Exception, stage: str) -> list[str]:
    """Convert Pydantic ValidationError into a list of error strings."""
    from pydantic import ValidationError

    if isinstance(exc, ValidationError):
        return [f"{stage}: {err['loc']}: {err['msg']}" for err in exc.errors()]
    return [f"{stage}: {exc}"]


def _check_evidence_refs(
    research: dict,
    plan: dict,
    build: dict,
    resolve: EvidenceCheck,
    r_complete: bool,
    p_complete: bool,
    b_complete: bool,
) -> list[str]:
    """Check that all evidence references resolve."""
    errors: list[str] = []

    def _ref(value: Any, name: str):
        if not _is_filled(value):
            errors.append(f"{name}: missing reference")
        elif not resolve(value):
            errors.append(f"{name}: unresolved evidence {value!r}")

    if r_complete:
        s = research.get("search", {})
        for src in s.get("sources", []):
            _ref(src.get("evidence_ref"), f"research.source.{src.get('id')}.evidence")
        outputs = research.get("outputs", {})
        _ref(outputs.get("candidate_plan_ref"), "research.candidate_plan")
        for ref in outputs.get("fixture_refs", []):
            _ref(ref, "research.fixtures")
        for ref in outputs.get("success_criteria_refs", []):
            _ref(ref, "research.criteria")
        _ref(research.get("handoff", {}).get("artifact_manifest_ref"), "research.manifest")
        # Checkpoint evidence refs
        cp = research.get("checkpoint", {})
        _ref(cp.get("action_receipt_ref"), "research.checkpoint.action_receipt_ref")
        _ref(cp.get("source_snapshot_ref"), "research.checkpoint.source_snapshot_ref")

    if p_complete and r_complete:
        impl = plan.get("implementation", {})
        _ref(impl.get("proposed_final_tree_ref"), "plan.final_tree")
        _ref(impl.get("command_environment_ref"), "plan.command_environment")
        for call in plan.get("gap_analysis", {}).get("scanner_calls", []):
            _ref(call.get("tool_ref"), "plan.scanner.tool")
            _ref(call.get("scope_ref"), "plan.scanner.scope")
            _ref(call.get("receipt_ref"), "plan.scanner.receipt")
            _ref(call.get("findings_ref"), "plan.scanner.findings")
        h = plan.get("handoff", {})
        _ref(h.get("plan_artifact_ref"), "plan.execplan")
        _ref(h.get("artifact_manifest_ref"), "plan.manifest")
        # Checkpoint evidence refs
        cp = plan.get("checkpoint", {})
        _ref(cp.get("action_receipt_ref"), "plan.checkpoint.action_receipt_ref")
        _ref(cp.get("source_snapshot_ref"), "plan.checkpoint.source_snapshot_ref")

    if b_complete and p_complete:
        execution = build.get("execution", {})
        for name in ("workspace_snapshot_ref", "environment_ref", "artifact_manifest_ref"):
            _ref(execution.get(name), f"build.execution.{name}")
        # Each command receipt must resolve independently.
        for cr in execution.get("command_receipts", []) or []:
            if not isinstance(cr, dict):
                continue
            _ref(cr.get("receipt_ref"), f"build.command.{cr.get('id')}.receipt")
        _ref(build.get("outcome", {}).get("user_visible_result_ref"), "build.user_result")
        _ref(build.get("handoff", {}).get("completion_receipt_ref"), "build.completion_receipt")
        # Checkpoint evidence refs
        cp = build.get("checkpoint", {})
        _ref(cp.get("action_receipt_ref"), "build.checkpoint.action_receipt_ref")
        _ref(cp.get("source_snapshot_ref"), "build.checkpoint.source_snapshot_ref")

    return errors


# ---------------------------------------------------------------------------
# Per-stage validators (compat API) — DO NOT EDIT ABOVE THIS BLOCK WITHOUT
# re-reading _check_evidence_refs() and validate_pipeline() for invariants.
# ---------------------------------------------------------------------------
#
# These wrappers return a flat list[str] of error strings for one stage,
# matching the historical check_contracts module's signature. They are a
# compatibility surface for tests migrated from the retired check_contracts
# module; new callers should prefer validate_pipeline() directly, since it
# runs cross-record invariants (task_id, handoff destinations, revision
# bindings) in one place.
#
# Two safety properties the wrappers MUST preserve:
#
#   (a) A record with status == "complete" and no resolve function is a
#       validation error ("no evidence resolver configured"). This mirrors
#       validate_pipeline's fail-closed behavior for completed records.
#
#   (b) Canonical-token prefixes are applied ONLY to the specific Pydantic
#       error messages they describe. A generic substring match like
#       "milestone" would mislabel every Milestone error as "unexecutable",
#       which is wrong — "milestone missing expected_observations" is not
#       the same defect as "no executable milestones" or "missing steps".

_CANONICAL_TOKENS: list[tuple[str, str]] = [
    # Each needle MUST be specific enough that it maps to exactly one
    # semantic defect. Prefer whole-phrase matches over single words.
    ("must not be empty or a placeholder", "missing task_id"),
    ("missing steps", "unexecutable"),
    ("no executable milestones", "unexecutable"),
    ("gap analysis must be resolved", "gap analysis incomplete"),
    ("cannot be deferred", "critical finding deferred"),
]


def _canonicalize_error(msg: str) -> str:
    for needle, token in _CANONICAL_TOKENS:
        if needle in msg:
            return f"{token}: {msg}"
    return msg


def _canonicalize_errors(errs: list[str]) -> list[str]:
    return [_canonicalize_error(e) for e in errs]


def validate_research(
    record: dict[str, Any] | None,
    resolve: EvidenceCheck | None = None,
    *,
    preflight: bool = False,
) -> list[str]:
    """Validate one Research record, returning a list of error strings.

    Replacement for the retired ``check_contracts.validate_research``.

    Modes:
      - Default: full validation (Pydantic + evidence resolution + fail-closed
        when the record is marked ``status: complete`` without a resolver).
      - ``preflight=True`` (two-step receipt protocol step 1): skip the
        ``validation_receipt_ref`` enforcement and the receiver-side
        evidence checks that depend on it. Structural and semantic
        invariants still run; only the receipt-related path is relaxed.

    ``None`` record and malformed top-level sections are reported with
    stable, substring-friendly phrases ("research: not an object",
    "research: missing or malformed search").
    """
    if record is None or not isinstance(record, dict):
        return ["research: not an object"]
    # Early malformed-section check so a non-dict nested slot surfaces a
    # clear phrase rather than a Pydantic shape error.
    nested_sections = {
        "search": "missing or malformed search",
        "purpose": "missing or malformed purpose",
        "outputs": "missing or malformed outputs",
        "review": "missing or malformed review",
    }
    for key, phrase in nested_sections.items():
        if key in record and record[key] is not None and not isinstance(record[key], dict):
            return [f"research: {phrase}"]

    try:
        ResearchRecord.model_validate(record)
    except Exception as exc:
        return _canonicalize_errors(_format_pydantic_errors(exc, "research"))

    r_complete = record.get("status") == "complete"
    errors: list[str] = []

    # Imperative invariants are stage-local for research — they can run
    # on raw dicts regardless of preflight mode.
    errors.extend(_check_imperative_invariants(record, {}, {}, r_complete, False, False))

    # Fail-closed only when the record is complete and NOT in preflight.
    if r_complete and resolve is None and not preflight:
        errors.append(
            "research: no evidence resolver configured — completed records require resolution"
        )
    elif r_complete and resolve is not None:
        errors.extend(_check_evidence_refs(record, {}, {}, resolve, True, False, False))

    # Receipt enforcement: full mode requires validation_receipt_ref on complete records.
    if r_complete and not preflight and not record.get("handoff", {}).get("validation_receipt_ref"):
        errors.append("research.handoff.validation_receipt_ref: missing")

    return errors


def validate_plan(
    plan: dict[str, Any] | None,
    research: dict[str, Any] | None = None,
    resolve: EvidenceCheck | None = None,
    *,
    preflight: bool = False,
) -> list[str]:
    """Validate one Plan record (with optional research context).

    Modes:
      - ``research=None``: single-stage mode. Cross-stage ordering checks
        (``downstream complete while Research not ready``) and cross-stage
        identity checks are skipped. Pydantic structural validation and
        plan-local imperative invariants still run.
      - ``preflight=True``: skip the ``validation_receipt_ref`` enforcement
        (step 1 of the two-step receipt protocol).
    """
    if plan is None or not isinstance(plan, dict):
        return ["plan: not an object"]

    try:
        PlanRecord.model_validate(plan)
    except Exception as exc:
        return _canonicalize_errors(_format_pydantic_errors(exc, "plan"))

    errors: list[str] = []

    # Handoff destination check (same semantics as validate_pipeline).
    if plan.get("handoff", {}).get("to") != "build":
        got = plan.get("handoff", {}).get("to")
        errors.append(f"plan: invalid handoff destination (expected build, got {got!r})")

    cross_stage = research is not None
    research = research or {}

    # Task-id consistency (only meaningful once research has one).
    if cross_stage:
        r_task = research.get("task_id")
        if r_task and plan.get("task_id") != r_task:
            errors.append("plan: task_id mismatch with research")

    # Research-side gating — cross-stage only.
    r_complete = False
    if cross_stage:
        try:
            ResearchRecord.model_validate(research)
            r_valid = True
        except Exception:
            r_valid = False
        r_complete = r_valid and research.get("status") == "complete"
    p_complete = plan.get("status") == "complete"
    if cross_stage and p_complete and not r_complete:
        errors.append("plan: downstream complete while Research not ready")

    # Research identity / revision binding (only meaningful cross-stage).
    if cross_stage and p_complete and r_complete:
        ri = plan.get("research_input", {}) or {}
        if ri.get("record_id") != research.get("record_id"):
            errors.append("plan: Research identity mismatch")
        if ri.get("record_revision") != research.get("revision"):
            errors.append("plan: stale Research revision")
        if ri.get("artifact_manifest_ref") != research.get("handoff", {}).get(
            "artifact_manifest_ref"
        ):
            errors.append("plan: Research manifest changed")

    # Plan-local imperative invariants (duplicate IDs, Scanner recency, gap fixes, etc.).
    errors.extend(_check_imperative_invariants(research, plan, {}, r_complete, p_complete, False))

    # Evidence resolution — fail-closed for complete records with no resolver,
    # but only in full-validation mode (preflight relaxes this gate).
    if p_complete and resolve is None and not preflight:
        errors.append(
            "plan: no evidence resolver configured — completed records require resolution"
        )
    elif resolve is not None:
        errors.extend(
            _check_evidence_refs(
                research,
                plan,
                {},
                resolve,
                r_complete,
                p_complete,
                False,
            )
        )

    # Receipt enforcement: full mode requires validation_receipt_ref on complete records.
    if p_complete and not preflight and not plan.get("handoff", {}).get("validation_receipt_ref"):
        errors.append("plan.handoff.validation_receipt_ref: missing")

    return errors


def validate_build(
    build: dict[str, Any] | None,
    plan: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    resolve: EvidenceCheck | None = None,
    *,
    preflight: bool = False,
) -> list[str]:
    """Validate one Build record (with optional plan+research context).

    Modes:
      - ``plan=None`` and/or ``research=None``: single-stage mode (skip the
        corresponding cross-stage ordering and identity checks).
      - ``preflight=True``: skip the ``validation_receipt_ref`` enforcement.
    """
    if build is None or not isinstance(build, dict):
        return ["build: not an object"]
    # Guard against a record that is NOT a build at all (e.g. the caller
    # passed a research record by mistake). The historical phrase is
    # "kind mismatch".
    if build.get("kind") and build["kind"] != "build":
        return [f"build: kind mismatch (expected 'build', got {build['kind']!r})"]

    try:
        BuildRecord.model_validate(build)
    except Exception as exc:
        return _canonicalize_errors(_format_pydantic_errors(exc, "build"))

    errors: list[str] = []

    # Handoff destination check.
    if build.get("handoff", {}).get("to") != "complete":
        got = build.get("handoff", {}).get("to")
        errors.append(f"build: invalid handoff destination (expected complete, got {got!r})")

    cross_plan = plan is not None
    cross_research = research is not None
    plan = plan or {}
    research = research or {}

    # Task-id consistency (across whichever records were provided).
    task_ids = {build.get("task_id")}
    if cross_plan:
        task_ids.add(plan.get("task_id"))
    if cross_research:
        task_ids.add(research.get("task_id"))
    task_ids.discard(None)
    if len(task_ids) > 1:
        errors.append("build: task_id mismatch across records")

    r_complete = False
    p_complete = False
    if cross_research:
        try:
            ResearchRecord.model_validate(research)
            r_valid = True
        except Exception:
            r_valid = False
        r_complete = r_valid and research.get("status") == "complete"
    if cross_plan:
        try:
            PlanRecord.model_validate(plan)
            p_valid = True
        except Exception:
            p_valid = False
        p_complete = p_valid and plan.get("status") == "complete"
    b_complete = build.get("status") == "complete"

    # Completion ordering (same semantics as validate_pipeline) — only when the
    # upstream record is actually provided.
    if cross_research and b_complete and not r_complete:
        errors.append("build: downstream complete while Research not ready")
    if cross_plan and b_complete and not p_complete:
        errors.append("build: downstream complete while Plan not ready")

    # Plan identity / revision binding — cross-plan only.
    if cross_plan and b_complete and p_complete:
        pi = build.get("plan_input", {}) or {}
        if pi.get("record_id") != plan.get("record_id"):
            errors.append("build: Plan identity mismatch")
        if pi.get("record_revision") != plan.get("revision"):
            errors.append("build: stale Plan revision")
        if pi.get("artifact_manifest_ref") != plan.get("handoff", {}).get("artifact_manifest_ref"):
            errors.append("build: Plan manifest changed")

    # Build-local imperative invariants.
    errors.extend(
        _check_imperative_invariants(research, plan, build, r_complete, p_complete, b_complete)
    )

    # Fail-closed for complete records with no resolver.
    if b_complete and resolve is None and not preflight:
        errors.append(
            "build: no evidence resolver configured — completed records require resolution"
        )
    elif resolve is not None:
        errors.extend(
            _check_evidence_refs(
                research,
                plan,
                build,
                resolve,
                r_complete,
                p_complete,
                b_complete,
            )
        )

    # Receipt enforcement: full mode requires validation_receipt_ref on complete records.
    if b_complete and not preflight and not build.get("handoff", {}).get("validation_receipt_ref"):
        errors.append("build.handoff.validation_receipt_ref: missing")

    return errors


# ---------------------------------------------------------------------------
# Compatibility aliases for the retired check_contracts module.
# ---------------------------------------------------------------------------


def validate_records(
    research: dict[str, Any],
    plan: dict[str, Any],
    build: dict[str, Any],
    resolve: EvidenceCheck | None = None,
) -> list[str]:
    """Alias for validate_pipeline.

    The retired check_contracts.validate_records had this signature; callers
    migrated to this module should prefer validate_pipeline for clarity.
    """
    return validate_pipeline(research, plan, build, resolve=resolve)


def preflight_check(
    record: dict[str, Any], stage: str, resolve: EvidenceCheck | None = None
) -> list[str]:
    """Dispatch a single-stage preflight validation.

    Step 1 of the two-step receipt protocol in the retired check_contracts
    module — validate substantive evidence without requiring the
    ``validation_receipt_ref``. Returns the error list from the matching
    per-stage validator; empty list means substantively ready.

    Unknown stage names produce an ``unknown stage`` error consistent with
    the historical API.
    """
    if stage == "research":
        return validate_research(record, resolve, preflight=True)
    if stage == "plan":
        return validate_plan(record, resolve=resolve, preflight=True)
    if stage == "build":
        return validate_build(record, resolve=resolve, preflight=True)
    return [f"unknown stage: {stage}"]


def evidence_index_resolver(index: dict[str, dict[str, str]], root: Path) -> EvidenceCheck:
    """SHA-256-backed resolver that verifies a file-backed artifact reference.

    Ported from the retired check_contracts module unchanged. Rejects symlinks
    at any path component, paths that escape ``root``, missing files, and
    digest mismatches. Opaque artifact-store IDs require the host's own
    resolver instead.
    """
    import hashlib

    base = Path(root).resolve()

    def resolve(ref: str) -> bool:
        item = index.get(ref)
        if not isinstance(item, dict):
            return False
        sha = item.get("sha256", "")
        path = item.get("path", "")
        if not isinstance(sha, str) or len(sha) != 64 or not isinstance(path, str):
            return False
        raw = base / path
        target = raw.resolve()
        if not target.is_relative_to(base) or not target.is_file():
            return False
        if raw.is_symlink() or any(
            parent.is_symlink()
            for parent in raw.parents
            if parent != base and parent.is_relative_to(base)
        ):
            return False
        return hashlib.sha256(target.read_bytes()).hexdigest() == sha

    return resolve
