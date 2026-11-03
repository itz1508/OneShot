"""Research stage contract — requirements, criteria, evidence, claims.

Extended with parent-child Research case lifecycle: ResearchRequest,
InputRequest, OutputResult, intents, admission, review, catalog matching,
fixture specifications, and requirement traceability.

Preserves existing ResearchRecord and related models for backward
compatibility with existing Audit Discovery consumers.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from agent.contracts.common import (
    ContractModel,
    CriterionId,
    EvidenceRef,
    RequirementId,
    StepResult,
)

# ---------------------------------------------------------------------------
# Existing status enums (preserved)
# ---------------------------------------------------------------------------


class AuthorizationStatus(StrEnum):
    GRANTED = "granted"
    PENDING = "pending"
    BLOCKED = "blocked"


class FeasibilityStatus(StrEnum):
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    UNCERTAIN = "uncertain"


class CriteriaStatus(StrEnum):
    DEFINED = "defined"
    PARTIAL = "partial"
    MISSING = "missing"


class EvidenceStatus(StrEnum):
    VALID = "valid"
    NOT_VALID = "not_valid"
    UNCERTAIN = "uncertain"


# ---------------------------------------------------------------------------
# New lifecycle enums
# ---------------------------------------------------------------------------


class ResearchIntent(StrEnum):
    """Primary intent for a Research input request."""

    INVESTIGATE_QUESTION = "investigate_question"
    VERIFY_INCOMING_PLAN = "verify_incoming_plan"
    VERIFY_PLANNING_INPUT = "verify_planning_input"
    INSPECT_CODEBASE = "inspect_codebase"
    VERIFY_CODE_PATTERN = "verify_code_pattern"
    CRAFT_FIXTURE = "craft_fixture"
    INVESTIGATE_FIXTURE_VALIDATION = "investigate_fixture_validation"


class AdmissionDisposition(StrEnum):
    """Host admission disposition for a Research input."""

    ACCEPTED = "accepted"
    ISOLATED = "isolated"
    REJECTED = "rejected"
    UNRESOLVED = "unresolved"


class ReviewDisposition(StrEnum):
    """Review outcome for a Research output."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    CORRECTION_REQUESTED = "correction_requested"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class CatalogMatchStatus(StrEnum):
    """Result of catalog template matching."""

    EXACT = "exact"
    MATCHED = "matched"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"
    NONE = "none"


class FixtureValidity(StrEnum):
    """Validity assessment for a fixture specification."""

    VALID = "valid"
    PARTIALLY_VALID = "partially_valid"
    INVALID = "invalid"
    UNRESOLVED = "unresolved"


class ExecutionStatus(StrEnum):
    """Execution lifecycle of a Research output."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class InformationClass(StrEnum):
    """Classification of research information."""

    ACCEPTED_REQUIREMENT = "accepted_requirement"
    VERIFIED_EVIDENCE = "verified_evidence"
    SUBMITTED_CLAIM = "submitted_claim"
    PROPOSED_OR_SYNTHETIC = "proposed_or_synthetic"
    CONTRADICTION = "contradiction"
    UNRESOLVED = "unresolved"


# ---------------------------------------------------------------------------
# Existing models (preserved)
# ---------------------------------------------------------------------------


class AcceptanceCriterion(ContractModel):
    criterion_id: CriterionId
    requirement_id: RequirementId
    success_condition: str = Field(min_length=1)
    failure_condition: str = Field(min_length=1)
    validation_method: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = ()


class Requirement(ContractModel):
    requirement_id: RequirementId
    source_reference: str = Field(min_length=1)
    original_wording: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    authorization_status: AuthorizationStatus = AuthorizationStatus.PENDING
    feasibility_status: FeasibilityStatus = FeasibilityStatus.UNCERTAIN
    criteria_status: CriteriaStatus = CriteriaStatus.MISSING
    acceptance_criteria_ids: tuple[CriterionId, ...] = ()
    constraints: tuple[str, ...] = ()


class ResearchClaim(ContractModel):
    claim_id: str = Field(min_length=1)
    requirement_ids: tuple[RequirementId, ...] = Field(min_length=1)
    statement: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    status: EvidenceStatus = EvidenceStatus.UNCERTAIN


class ResearchEvidence(ContractModel):
    evidence_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    content_digest: str = Field(min_length=1)
    location: str = Field(min_length=1)
    description: str = ""
    status: EvidenceStatus = EvidenceStatus.UNCERTAIN


class ResearchRecord(ContractModel):
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    stage_revision: int = Field(ge=1)
    requirements: tuple[Requirement, ...] = Field(min_length=1)
    acceptance_criteria: tuple[AcceptanceCriterion, ...] = ()
    claims: tuple[ResearchClaim, ...] = ()
    evidence: tuple[ResearchEvidence, ...] = ()
    constraints: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    step_results: tuple[StepResult, ...] = ()


# ---------------------------------------------------------------------------
# New lifecycle models
# ---------------------------------------------------------------------------


class SourceReference(ContractModel):
    """Reference to a source with provenance.

    New sources default to unverified (is_authoritative=False).
    Promotion to authoritative requires provenance and verified
    source content. Catalog samples are explicitly synthetic.
    """

    source_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    identity: str = Field(min_length=1)
    version: str = ""
    retrieval_info: str = ""
    content_digest: str = ""
    limitations: tuple[str, ...] = ()
    is_authoritative: bool = False


class CatalogMatch(ContractModel):
    """Result of matching an input against synthetic catalog templates."""

    catalog_id: str = Field(min_length=1)
    catalog_version: str = Field(min_length=1)
    match_status: CatalogMatchStatus
    matched_conditions: tuple[str, ...] = ()
    is_synthetic: bool = True


class ResearchPlan(ContractModel):
    """Bounded research plan for an admitted input."""

    investigation_question: str = Field(min_length=1)
    related_requirement_refs: tuple[str, ...] = ()
    evidence_to_obtain: tuple[str, ...] = ()
    expected_findings: tuple[str, ...] = ()
    contradictions_to_resolve: tuple[str, ...] = ()
    explicit_unknowns: tuple[str, ...] = ()
    completion_criteria: str = Field(min_length=1)
    prohibited_conclusions: tuple[str, ...] = ()


class ResearchFinding(ContractModel):
    """Structured research finding."""

    finding_id: str = Field(min_length=1)
    requirement_refs: tuple[str, ...] = ()
    statement: str = Field(min_length=1)
    information_class: InformationClass
    evidence_refs: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()


class ResearchContradiction(ContractModel):
    """Recorded contradiction between sources or claims."""

    contradiction_id: str = Field(min_length=1)
    finding_refs: tuple[str, ...] = Field(min_length=1)
    description: str = Field(min_length=1)
    resolution: str = ""
    preserved: bool = True


class ResearchUnresolved(ContractModel):
    """Unresolved question from research."""

    unresolved_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    related_finding_refs: tuple[str, ...] = ()
    reason: str = ""


class RequirementTrace(ContractModel):
    """Traceability from requirement to research evidence."""

    requirement_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = ()
    finding_refs: tuple[str, ...] = ()
    coverage_status: str = "not_covered"


class ResearchFollowup(ContractModel):
    """Proposed follow-up investigation."""

    followup_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    related_finding_refs: tuple[str, ...] = ()


class FixtureSpecification(ContractModel):
    """Evidence-grounded fixture specification.

    Research may specify fixtures but must not report downstream test
    execution as successful. A valid specification is not evidence that
    the built product passed.
    """

    fixture_id: str = Field(min_length=1)
    requirement_ref: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    preconditions: tuple[str, ...] = Field(min_length=1)
    triggering_action: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    failure_observations: str = Field(min_length=1)
    required_evidence: tuple[str, ...] = Field(min_length=1)
    false_positive_protections: tuple[str, ...] = ()
    setup_failure_conditions: tuple[str, ...] = ()
    known_limitations: tuple[str, ...] = ()


class FixtureValidityAssessment(ContractModel):
    """Independent validity assessment of a fixture specification."""

    fixture_ref: str = Field(min_length=1)
    validity: FixtureValidity
    assessment_notes: str = ""
    gaps: tuple[str, ...] = ()


class ResearchAdmission(ContractModel):
    """Host admission result for a Research input."""

    disposition: AdmissionDisposition
    validation_receipt_ref: str = ""
    rejection_reason: str = ""

    @model_validator(mode="after")
    def check_admission(self) -> ResearchAdmission:
        if self.disposition == AdmissionDisposition.ACCEPTED and not self.validation_receipt_ref:
            raise ValueError("accepted admission requires validation receipt")
        if self.disposition == AdmissionDisposition.REJECTED and not self.rejection_reason:
            raise ValueError("rejected admission requires rejection reason")
        return self


class ResearchRequest(ContractModel):
    """Parent Research case — one per Research cycle.

    Maintains child references to InputRequest and OutputResult revisions.
    Only reviewed and accepted outputs qualify for Planning handoff.
    """

    request_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    status: str = "active"
    created_from: str = Field(min_length=1)
    accepted_requirement_refs: tuple[str, ...] = ()
    child_refs: tuple[str, ...] = ()
    current_input_ref: str | None = None
    current_accepted_result_ref: str | None = None


class InputRequest(ContractModel):
    """Child input to a Research case.

    One primary intent per input. Host validates provenance, scope,
    and admission before Research may execute.
    """

    input_id: str = Field(min_length=1)
    parent_request_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    intent: ResearchIntent
    provenance_ref: str = Field(min_length=1)
    related_requirement_refs: tuple[str, ...] = ()

    investigation_question: str = Field(min_length=1)
    expected_result: str = Field(min_length=1)

    supporting_input_refs: tuple[str, ...] = ()
    catalog_matches: tuple[CatalogMatch, ...] = ()
    research_plan: ResearchPlan | None = None

    admission: ResearchAdmission

    @model_validator(mode="after")
    def check_admission_binding(self) -> InputRequest:
        if self.admission.disposition == AdmissionDisposition.ACCEPTED and not self.admission.validation_receipt_ref:
            raise ValueError("accepted input requires validation receipt")
        return self


class OutputResult(ContractModel):
    """Child output from Research — binds to exact admitted input revision.

    Execution completion does not imply review acceptance. Only accepted
    results are eligible for Planning handoff.
    """

    output_id: str = Field(min_length=1)
    parent_request_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    responds_to: str = Field(min_length=1)
    admission_receipt_ref: str = Field(min_length=1)

    execution_status: ExecutionStatus = ExecutionStatus.PENDING
    execution_receipt_ref: str = ""
    report_ref: str = ""

    evidence_refs: tuple[EvidenceRef, ...] = ()
    finding_refs: tuple[str, ...] = ()
    contradiction_refs: tuple[str, ...] = ()
    unresolved_refs: tuple[str, ...] = ()
    requirement_trace: tuple[RequirementTrace, ...] = ()
    proposed_followup_refs: tuple[str, ...] = ()
    fixture_specs: tuple[FixtureSpecification, ...] = ()
    fixture_validity: tuple[FixtureValidityAssessment, ...] = ()

    review_disposition: ReviewDisposition = ReviewDisposition.PENDING
    review_receipt_ref: str = ""

    @model_validator(mode="after")
    def check_review_binding(self) -> OutputResult:
        if self.review_disposition == ReviewDisposition.ACCEPTED and not self.review_receipt_ref:
            raise ValueError("accepted review requires receipt")
        if self.execution_status == ExecutionStatus.COMPLETED:
            if not self.report_ref:
                raise ValueError("completed output requires report reference")
            if not self.execution_receipt_ref:
                raise ValueError("completed output requires execution receipt")
        return self
