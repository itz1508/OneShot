"""OneShot research contracts extracted from the former models.py monolith.

Keep stage fields and validators compatible; YAML record templates remain intact.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .shared import (Checkpoint, RecordStatus, ReviewCoverage, EvidenceGrounding, ReviewDisposition, FindingAssessment, _is_filled)

# ---------------------------------------------------------------------------
# Research record models
# ---------------------------------------------------------------------------


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)

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
    model_config = ConfigDict(extra="forbid", validate_default=True)

    id: str
    location: str
    revision_or_hash: str
    authority: str | None = None
    inspected_at: str | None = None
    evidence_ref: str | None = None


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)

    id: str
    claim: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    assessment: FindingAssessment = FindingAssessment.NOT_CHECKED
    limitations: str | None = None


class Contradiction(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)

    id: str
    competing_evidence_refs: list[str] = Field(default_factory=list)
    disposition: Literal["resolved", "unresolved", "not_checked"] = "not_checked"
    resolution_ref: str | None = None


class Uncertainty(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)

    id: str
    impact: str | None = None
    owner: str | None = None
    researchable: bool | None = None
    resolution: str | None = None
    blocking: bool = False


class ResearchPurpose(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)

    user_outcome: str
    original_request_ref: str | None = None
    accepted_requirements: list[Requirement] = Field(default_factory=list)
    scope: list[Any] = Field(default_factory=list)
    constraints: list[Any] = Field(default_factory=list)
    superseded_requirements: list[Any] = Field(default_factory=list)


class ResearchSearch(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)

    todo_search_ref: str | None = None
    questions: list[Any] = Field(default_factory=list)
    sources: list[ResearchSource] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    uncertainties: list[Uncertainty] = Field(default_factory=list)


class RequirementTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)

    requirement_id: str
    finding_ids: list[str] = Field(default_factory=list)
    fixture_ids: list[str] = Field(default_factory=list)
    criterion_ids: list[str] = Field(default_factory=list)
    disposition: str | None = None


class ResearchOutputs(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)

    evidence_refs: list[str] = Field(default_factory=list)
    candidate_plan_ref: str | None = None
    fixture_refs: list[str] = Field(default_factory=list)
    success_criteria_refs: list[str] = Field(default_factory=list)
    # Inline criteria are an existing legacy form. Keep lightweight mappings
    # compatible; validate relationships/field presence at the stage boundary.
    # This explicit field ensures normalized JSON and generated schemas agree
    # with research.yaml and validate_pipeline's existing handling.
    success_criteria: list[dict[str, Any]] = Field(default_factory=list)
    requirement_trace: list[RequirementTrace] = Field(default_factory=list)


class ResearchReview(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)

    coverage: ReviewCoverage = ReviewCoverage.NOT_CHECKED
    evidence_grounding: EvidenceGrounding = EvidenceGrounding.NOT_CHECKED
    unsupported_claims: list[Any] = Field(default_factory=list)
    unresolved_issues: list[Any] = Field(default_factory=list)
    blockers: list[Any] = Field(default_factory=list)
    disposition: ReviewDisposition = ReviewDisposition.NOT_CHECKED
    review_receipt_ref: str | None = None



class ResearchWorkspace(BaseModel):
    """Known Research workspace keys; unverified paths remain null."""

    model_config = ConfigDict(extra="forbid", validate_default=True)

    repo_root: str | None = None
    active_source_root: str | None = None
    git_revision: str | None = None
    dirty_tree_ref: str | None = None
    environment_ref: str | None = None


class ResearchHandoff(BaseModel):
    """Handoff data, not permission to advance a workflow stage."""

    model_config = ConfigDict(extra="forbid", validate_default=True)

    to: str = "plan"
    ready: bool = Field(default=False, strict=True)
    artifact_manifest_ref: str | None = None
    validation_receipt_ref: str | None = None


class ResearchCheckpoint(Checkpoint):
    """Research-specific strict view of the shared Checkpoint."""

    model_config = ConfigDict(extra="forbid", validate_default=True)


class ResearchRecord(BaseModel):
    """Pydantic model for the Research contract record."""

    model_config = ConfigDict(extra="forbid", validate_default=True)

    kind: Literal["research"] = "research"
    contract_version: str | None = None  # existing legacy record field
    task_id: str
    record_id: str
    revision: int = Field(ge=1, strict=True)
    # G09 same-task continuation sets these lineage identifiers.
    preceding_record_id: str | None = None
    preceding_revision: int | None = Field(default=None, ge=1, strict=True)
    status: RecordStatus = RecordStatus.DRAFT
    updated_at: str | None = None

    purpose: ResearchPurpose
    workspace: ResearchWorkspace = Field(default_factory=ResearchWorkspace)
    search: ResearchSearch = Field(default_factory=ResearchSearch)
    outputs: ResearchOutputs = Field(default_factory=ResearchOutputs)
    review: ResearchReview = Field(default_factory=ResearchReview)

    progress_log: list[Any] = Field(default_factory=list)
    decision_log: list[Any] = Field(default_factory=list)
    checkpoint: ResearchCheckpoint = Field(default_factory=ResearchCheckpoint)

    handoff: ResearchHandoff = Field(default_factory=ResearchHandoff)

    @field_validator("task_id", "record_id")
    @classmethod
    def not_placeholder(cls, v):
        if not _is_filled(v):
            raise ValueError("must not be empty or a placeholder")
        return v

    @model_validator(mode="after")
    def check_completion(self) -> ResearchRecord:
        ready = self.handoff.ready
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

    @model_validator(mode="after")
    def check_research_relationships(self) -> ResearchRecord:
        """Validate only local IDs; external evidence belongs to the host."""

        def unique(label: str, ids: list[str]) -> None:
            if len(ids) != len(set(ids)):
                raise ValueError(f"duplicate {label} IDs")

        requirements = [r.id for r in self.purpose.accepted_requirements]
        findings = [f.id for f in self.search.findings]
        sources = [s.id for s in self.search.sources]
        traces = [t.requirement_id for t in self.outputs.requirement_trace]
        unique("requirement", requirements)
        unique("finding", findings)
        unique("source", sources)
        unique("requirement trace", traces)
        for trace in self.outputs.requirement_trace:
            if trace.requirement_id not in requirements:
                raise ValueError(f"unknown requirement trace: {trace.requirement_id}")
            unknown = set(trace.finding_ids) - set(findings)
            if unknown:
                raise ValueError(
                    f"unknown findings for {trace.requirement_id}: {sorted(unknown)}"
                )
        return self



