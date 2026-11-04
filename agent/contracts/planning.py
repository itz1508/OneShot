"""Planning stage contract — analysis, decisions, BuildSpecification."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from agent.contracts.common import (
    ArtifactRef,
    ContractModel,
    CriterionId,
    DecisionId,
    DiagnosticStatus,
    IssueId,
    RequirementId,
    ReviewId,
    Sha256,
    StepResult,
)
from agent.contracts.tool_registry import ToolInvocation


class IntentDisposition(StrEnum):
    ACCEPT = "accept"
    REVISE = "revise"
    COMBINE = "combine"
    SPLIT = "split"
    DEFER = "defer"
    REJECT = "reject"


class FindingAssessment(StrEnum):
    ACCEPTED = "accepted"
    DISPUTED = "disputed"
    NOT_APPLICABLE = "not_applicable_to_design"
    REQUIRES_NEW_EVIDENCE = "requires_new_evidence"


class IssueResolutionStatus(StrEnum):
    """Lifecycle of a planning issue from open to resolved."""

    OPEN = "open"
    CORRECTED = "corrected"
    ACCEPTED_RISK = "accepted_risk"
    DEFERRED = "deferred"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


IssueEvidenceStatus = DiagnosticStatus


IssueType = Literal[
    "compatibility",
    "dependency",
    "interface",
    "concurrency",
    "security",
    "recovery",
    "buildability",
    "verifiability",
]


class CodeIntentReview(ContractModel):
    """Planner review of a CodeIntent with disposition and resulting IDs."""

    review_id: ReviewId
    source_intent_ids: tuple[str, ...] = Field(min_length=1)
    disposition: IntentDisposition
    rationale: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = ()
    resulting_review_ids: tuple[str, ...] = ()
    resulting_decision_ids: tuple[str, ...] = ()
    resulting_action_ids: tuple[str, ...] = ()


class PlanningFindingAssessment(ContractModel):
    """Planner assessment of an audit finding."""

    assessment_id: str = Field(min_length=1)
    audit_finding_id: str = Field(min_length=1)
    assessment: FindingAssessment
    rationale: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = ()
    planning_effect: str = ""
    renewed_audit_requested: bool = False


class PlanningIssue(ContractModel):
    """Issue discovered during planning with evidence and resolution tracking."""

    issue_id: IssueId
    issue_type: IssueType
    statement: str = Field(min_length=1)
    requirement_ids: tuple[RequirementId, ...] = ()
    acceptance_criteria_ids: tuple[CriterionId, ...] = ()
    originating_intent_ids: tuple[str, ...] = ()
    evidence_status: IssueEvidenceStatus = IssueEvidenceStatus.UNCERTAINTY
    resolution_status: IssueResolutionStatus = IssueResolutionStatus.OPEN
    check_id: str | None = None
    method: str | None = None
    environment_ref: str | None = None
    output_digest: Sha256 | None = None
    receipt_ref: str | None = None
    violated_constraint: str = ""
    affected_elements: tuple[str, ...] = ()
    resolution: str = ""
    remaining_risk: str = ""

    @model_validator(mode="after")
    def check_resolution(self) -> PlanningIssue:
        if self.resolution_status is IssueResolutionStatus.CORRECTED and not self.resolution:
            raise ValueError("corrected issue requires resolution")
        if (
            self.evidence_status is IssueEvidenceStatus.UNCERTAINTY
            and self.resolution_status is IssueResolutionStatus.CORRECTED
        ):
            raise ValueError("uncertain evidence cannot authorize correction")
        return self


class CodingAnalysis(ContractModel):
    analysis_id: str = Field(min_length=1)
    intent_id: str = Field(min_length=1)
    source_inspection: str = Field(min_length=1)
    dependency_constraints: tuple[str, ...] = ()
    technical_check_refs: tuple[str, ...] = ()
    impact: str = ""
    tradeoffs: str = ""
    current_behavior: str = ""
    expected_behavior: str = ""
    verifiability: str = ""


class DesignDecision(ContractModel):
    """Design decision with options, selected direction, and traceability."""

    decision_id: DecisionId
    requirement_ids: tuple[RequirementId, ...] = Field(min_length=1)
    acceptance_criteria_ids: tuple[CriterionId, ...] = Field(min_length=1)
    code_intent_ids: tuple[str, ...] = Field(min_length=1)
    audit_finding_ids: tuple[str, ...] = ()
    planning_issue_ids: tuple[str, ...] = ()
    context: str = Field(min_length=1)
    options_considered: tuple[str, ...] = Field(min_length=1)
    selected_direction: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    affected_elements: tuple[str, ...] = ()
    expected_result: str = Field(min_length=1)


class CorrectiveRefactor(ContractModel):
    """Corrective refactor preserving behavior while fixing a violation."""

    refactor_id: str = Field(min_length=1)
    finding_ref: str = Field(min_length=1)
    violated_constraint: str = Field(min_length=1)
    original_direction: str = Field(min_length=1)
    corrected_design: str = Field(min_length=1)
    preserved_behavior: str = Field(min_length=1)
    affected_elements: tuple[str, ...] = Field(min_length=1)
    correction: str = Field(min_length=1)


class SpecificationTrace(ContractModel):
    """Bidirectional traceability between requirements, criteria, intents, decisions."""

    requirement_ids: tuple[RequirementId, ...] = ()
    acceptance_criteria_ids: tuple[CriterionId, ...] = ()
    code_intent_ids: tuple[str, ...] = ()
    design_decision_ids: tuple[str, ...] = ()
    finding_ids: tuple[str, ...] = ()
    issue_ids: tuple[str, ...] = ()


class ValidationStep(ContractModel):
    """Executable validation step with expected result and failure observation."""

    check_id: str = Field(min_length=1)
    order: int = Field(ge=1)
    invocation: ToolInvocation
    expected_result: str = Field(min_length=1)
    failure_observation: str = ""


class PlanningWorkItem(ContractModel):
    item_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    dependencies: tuple[str, ...] = ()
    scope: str = Field(min_length=1)
    status: str = "not_run"
    outcome: str = ""


class ActionBase(ContractModel):
    action_id: str = Field(min_length=1)
    requirement_ids: tuple[RequirementId, ...] = Field(min_length=1)
    acceptance_criteria_ids: tuple[CriterionId, ...] = Field(min_length=1)
    code_intent_ids: tuple[str, ...] = Field(min_length=1)
    supporting_issue_or_finding_refs: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = Field(min_length=1)
    depends_on: tuple[str, ...] = ()
    validation_steps: tuple[str, ...] = Field(min_length=1)  # expected checks, NEVER executable argv
    verification_tools: tuple[ToolInvocation, ...] = ()
    expected_result: str = Field(min_length=1)
    effect_scope: Literal["filesystem"] = "filesystem"
    retry_semantics: Literal["idempotent", "non_idempotent"] = "idempotent"
    destructive: bool = False
    recovery_requirement: str = Field(min_length=1)


class CreateAction(ActionBase):
    action_kind: Literal["create"] = "create"
    target_path: str = Field(min_length=1)
    target_conflict_check_ref: str = Field(min_length=1)


class ModifyAction(ActionBase):
    action_kind: Literal["modify"] = "modify"
    source_path: str = Field(min_length=1)
    expected_source_digest: Sha256


class MoveAction(ActionBase):
    action_kind: Literal["move"] = "move"
    source_path: str = Field(min_length=1)
    target_path: str = Field(min_length=1)
    expected_source_digest: Sha256
    target_conflict_check_ref: str = Field(min_length=1)


class RemoveAction(ActionBase):
    action_kind: Literal["remove"] = "remove"
    source_path: str = Field(min_length=1)
    expected_source_digest: Sha256
    destructive_approval_requirement: str = Field(min_length=1)
    destructive: Literal[True] = True


BuildAction = Annotated[
    CreateAction | ModifyAction | MoveAction | RemoveAction,
    Field(discriminator="action_kind"),
]


class BuildPhase(ContractModel):
    phase_id: str = Field(min_length=1)
    action_ids: tuple[str, ...] = Field(min_length=1)
    depends_on: tuple[str, ...] = ()


class FixtureSpecification(ContractModel):
    fixture_id: str = Field(min_length=1)
    oracle_ref: str = Field(min_length=1)
    oracle_provenance: str = Field(min_length=1)
    test_inputs: str = Field(min_length=1)
    expected_results: tuple[str, ...] = Field(min_length=1)


class ChaosSpecification(ContractModel):
    chaos_id: str = Field(min_length=1)
    fault_type: str = Field(min_length=1)
    target_step: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)


class RequirementCoverage(ContractModel):
    requirement_id: RequirementId
    status: Literal["covered", "blocked", "not_run"] = "not_run"
    criterion_refs: tuple[CriterionId, ...] = ()
    specification_refs: tuple[str, ...] = ()
    reason: str = ""


class CriterionCoverage(ContractModel):
    criterion_id: CriterionId
    requirement_id: RequirementId
    status: Literal["covered", "blocked", "not_run"] = "not_run"
    validation_step_refs: tuple[str, ...] = ()
    reason: str = ""


class BuildSpecification(ContractModel):
    spec_id: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    actions: tuple[BuildAction, ...] = Field(min_length=1)
    phases: tuple[BuildPhase, ...] = ()
    fixtures: tuple[FixtureSpecification, ...] = ()
    chaos_specs: tuple[ChaosSpecification, ...] = ()
    protected_surfaces: tuple[str, ...] = ()
    requirement_coverage: tuple[RequirementCoverage, ...] = ()
    criterion_coverage: tuple[CriterionCoverage, ...] = ()


class CandidateSpecification(ContractModel):
    candidate_id: str = Field(min_length=1)
    specification_revision: int = Field(ge=1)
    build_spec: BuildSpecification
    planning_report: str = ""


class PlanningRecord(ContractModel):
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    stage_revision: int = Field(ge=1)
    audit_ref: ArtifactRef
    candidate: CandidateSpecification
    final_scanner_receipt_ref: str | None = None
    freeze_receipt_ref: str | None = None
    intent_reviews: tuple[CodeIntentReview, ...] = ()
    finding_assessments: tuple[PlanningFindingAssessment, ...] = ()
    issues: tuple[PlanningIssue, ...] = ()
    coding_analyses: tuple[CodingAnalysis, ...] = ()
    design_decisions: tuple[DesignDecision, ...] = ()
    corrective_refactors: tuple[CorrectiveRefactor, ...] = ()
    work_items: tuple[PlanningWorkItem, ...] = ()
    step_results: tuple[StepResult, ...] = ()
