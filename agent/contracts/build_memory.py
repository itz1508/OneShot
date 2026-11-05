"""Verified, reusable Build knowledge, never ordinary working memory."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from agent.contracts.common import ArtifactRef, ContractModel
from agent.contracts.host import ReceiptRef


class KnowledgeKind(StrEnum):
    IMPLEMENTATION_PATTERN = "implementation_pattern"
    COMMAND_PROFILE = "command_profile"
    COMPATIBILITY_FACT = "compatibility_fact"
    RECOVERY_PROCEDURE = "recovery_procedure"
    REPOSITORY_CONVENTION = "repository_convention"
    TOOLCHAIN_PATTERN = "toolchain_pattern"
    DEPENDENCY_COMBINATION = "dependency_combination"
    BUILD_PROCEDURE = "build_procedure"


class VerifiedBuildKnowledge(ContractModel):
    memory_id: str = Field(min_length=1)
    memory_revision: int = Field(ge=1)
    kind: KnowledgeKind
    summary: str = Field(min_length=1)
    reusable_scope: str = Field(min_length=1)
    evidence_refs: tuple[ArtifactRef, ...] = Field(min_length=1)
    source_build_ref: ArtifactRef
    build_validation_ref: ArtifactRef
    source_plan_template_ref: ArtifactRef
    verification_receipt_ref: ReceiptRef
    approval_receipt_ref: ReceiptRef

    @model_validator(mode="after")
    def no_duplicate_sources(self) -> VerifiedBuildKnowledge:
        keys = [(ref.artifact_id, ref.artifact_revision) for ref in self.evidence_refs]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate evidence references")
        return self
