"""PRE/POST Discovery handoff contracts; neither mode grants Build authority."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from agent.contracts.common import ArtifactRef, ContractModel, Sha256


class InspectionStatus(StrEnum):
    CAPTURED = "captured"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class DiscoverySource(ContractModel):
    """A bounded, host-produced repository observation; not a Git source lock."""

    status: InspectionStatus
    root_label: str = Field(min_length=1)
    manifest_digest: Sha256
    inspected_paths: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


class DiscoveryPre(ContractModel):
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    thread_message_id: str = Field(min_length=1)
    message_revision: int = Field(ge=1)
    user_intent_ref: ArtifactRef
    source_ref: ArtifactRef
    intent_summary: str = Field(min_length=1)
    summary_method: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    template_version: str = Field(min_length=1)
    research_questions: tuple[str, ...] = Field(min_length=1)
    provisional_success_criteria: tuple[str, ...] = ()
    fixture_guidance: tuple[str, ...] = ()


class DiscoveryResearchRequest(ContractModel):
    """Host-composed Research request, preserving original message provenance."""

    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    thread_message_id: str = Field(min_length=1)
    request_revision: int = Field(ge=1)
    user_intent_ref: ArtifactRef
    discovery_pre_ref: ArtifactRef
    information_needed: str = Field(min_length=1)


class ReconciledResearchItem(ContractModel):
    claim_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = ()
    evidence_status: str = Field(min_length=1)
    repository_applicability: str = "unassessed"
    limitations: tuple[str, ...] = ()


class DiscoveryPost(ContractModel):
    """Read-only ingest for canonical Audit Discovery; never a BuildSpecification."""

    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    thread_message_id: str = Field(min_length=1)
    discovery_pre_ref: ArtifactRef
    research_ref: ArtifactRef
    source_at_pre_ref: ArtifactRef
    source_at_post_ref: ArtifactRef
    source_stable: bool
    research_items: tuple[ReconciledResearchItem, ...] = ()
    contradictions: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    requires_audit: bool = True
