"""Audit Discovery stage contract — grounded source observations, findings, CodeIntent."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from agent.contracts.common import (
    ArtifactRef,
    AssessmentId,
    ContractModel,
    CriterionId,
    DiagnosticStatus,
    FindingId,
    RequirementId,
    StepResult,
)

FindingStatus = DiagnosticStatus


class AssessmentStatus(StrEnum):
    """Requirement assessment status in audit discovery."""

    SATISFIED_EXISTING = "satisfied_existing"
    PARTIALLY_SATISFIED = "partially_satisfied"
    UNSATISFIED = "unsatisfied"
    CONTRADICTORY = "contradictory"
    UNCERTAINTY = "uncertainty"
    NOT_APPLICABLE = "not_applicable"


class WorktreeEntry(ContractModel):
    path: str = Field(min_length=1)
    is_tracked: bool = True
    is_ignored: bool = False
    is_symlink: bool = False
    content_digest: str | None = None


class RepositoryIdentity(ContractModel):
    commit_object_id: str = Field(min_length=1)
    hash_algorithm: Literal["sha1", "sha256"] = "sha1"
    tracked_manifest_digest: str = Field(min_length=1)
    clean_state: bool = True
    capture_timestamp: str = Field(min_length=1)
    host_capture_receipt: str = Field(min_length=1)


class AuditEvidence(ContractModel):
    evidence_id: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    line_range: tuple[int, int] | None = None
    content_digest: str = Field(min_length=1)
    description: str = ""


class RequirementAssessment(ContractModel):
    """Assessment of a requirement against current implementation."""

    assessment_id: AssessmentId
    requirement_id: RequirementId
    acceptance_criteria_ids: tuple[CriterionId, ...] = ()
    status: AssessmentStatus = AssessmentStatus.UNCERTAINTY
    current_implementation: str = ""
    expected_behavior: str = ""
    evidence_refs: tuple[str, ...] = ()
    gap_summary: str = ""
    code_intent_required: bool = False
    rationale: str = ""


class ImplementationFinding(ContractModel):
    """Diagnostic finding about the implementation."""

    finding_id: FindingId
    requirement_ids: tuple[RequirementId, ...] = ()
    acceptance_criteria_ids: tuple[CriterionId, ...] = ()
    observation: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    status: FindingStatus = FindingStatus.UNCERTAINTY
    inspected_scope: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()


class IntentBase(ContractModel):
    intent_id: str = Field(min_length=1)
    requirement_ids: tuple[RequirementId, ...] = Field(min_length=1)
    acceptance_criteria_ids: tuple[CriterionId, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    objective: str = Field(min_length=1)
    candidate_direction: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    expected_results: tuple[str, ...] = Field(min_length=1)
    constraints: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()


class ExistingGapIntent(IntentBase):
    intent_origin: Literal["existing_implementation_gap"] = "existing_implementation_gap"
    finding_ids: tuple[str, ...] = ()
    verified_paths: tuple[str, ...] = ()
    current_behavior: str = Field(min_length=1)
    identified_gap: str = Field(min_length=1)


class NewFeatureIntent(IntentBase):
    intent_origin: Literal["new_feature"] = "new_feature"
    finding_ids: tuple[str, ...] = ()
    verified_paths: tuple[str, ...] = ()
    candidate_paths: tuple[str, ...] = ()
    destination_responsibility: str = ""
    ownership_inspection_ref: str = Field(min_length=1)
    conflict_inspection_ref: str = Field(min_length=1)


class CompatibilityChangeIntent(IntentBase):
    """Intent to change compatibility behavior (API, platform, dependency)."""

    intent_origin: Literal["compatibility_change"] = "compatibility_change"
    finding_ids: tuple[str, ...] = ()
    verified_paths: tuple[str, ...] = ()
    compatibility_constraints: tuple[str, ...] = ()
    dependency_constraints: tuple[str, ...] = ()


class MigrationIntent(IntentBase):
    """Intent to migrate from one implementation/approach to another."""

    intent_origin: Literal["migration"] = "migration"
    finding_ids: tuple[str, ...] = ()
    verified_paths: tuple[str, ...] = ()
    source_behavior: str = Field(min_length=1)
    target_behavior: str = Field(min_length=1)


class RecoveryRequirementIntent(IntentBase):
    """Intent to add or fix recovery behavior for fault tolerance."""

    intent_origin: Literal["recovery_requirement"] = "recovery_requirement"
    finding_ids: tuple[str, ...] = ()
    verified_paths: tuple[str, ...] = ()
    failure_scenario: str = Field(min_length=1)
    expected_recovery: str = Field(min_length=1)


CodeIntent = Annotated[
    ExistingGapIntent | NewFeatureIntent | CompatibilityChangeIntent | MigrationIntent | RecoveryRequirementIntent,
    Field(discriminator="intent_origin"),
]


class AuditDiscoveryInput(ContractModel):
    research_artifact: ArtifactRef
    research_receipt_ref: str = Field(min_length=1)
    accepted_requirement_ids: tuple[RequirementId, ...] = Field(min_length=1)


class AuditDiscoveryPackage(ContractModel):
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    stage_revision: int = Field(ge=1)
    research_ref: ArtifactRef
    start_identity: RepositoryIdentity
    end_identity: RepositoryIdentity
    assessments: tuple[RequirementAssessment, ...] = ()
    findings: tuple[ImplementationFinding, ...] = ()
    code_intents: tuple[CodeIntent, ...] = ()
    evidence: tuple[AuditEvidence, ...] = ()
    contradictions: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    step_results: tuple[StepResult, ...] = ()
