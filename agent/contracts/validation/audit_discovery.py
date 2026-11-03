"""Semantic validators for Audit Discovery."""

from __future__ import annotations

from agent.contracts.audit_discovery import AuditDiscoveryPackage
from agent.contracts.common import ArtifactRef


def validate_research_lineage(package: AuditDiscoveryPackage, expected_research_ref: ArtifactRef) -> list[str]:
    errors: list[str] = []
    if package.research_ref.artifact_id != expected_research_ref.artifact_id:
        errors.append("research artifact ID mismatch")
    if package.research_ref.artifact_digest != expected_research_ref.artifact_digest:
        errors.append("research artifact digest mismatch")
    return errors


def validate_repository_identity_pair(package: AuditDiscoveryPackage) -> list[str]:
    errors: list[str] = []
    if package.start_identity.commit_object_id != package.end_identity.commit_object_id and not package.contradictions:
        errors.append("start/end identity mismatch without recorded contradictions")
    return errors


def validate_requirement_assessments(package: AuditDiscoveryPackage, accepted_req_ids: tuple[str, ...]) -> list[str]:
    errors: list[str] = []
    assessed_ids = {a.requirement_id for a in package.assessments}
    for req_id in accepted_req_ids:
        if req_id not in assessed_ids:
            errors.append(f"accepted requirement {req_id} not assessed")
    return errors


def validate_code_intents(package: AuditDiscoveryPackage) -> list[str]:
    errors: list[str] = []
    for intent in package.code_intents:
        if intent.intent_origin == "existing_implementation_gap":
            if not intent.finding_ids:
                errors.append(f"existing gap intent {intent.intent_id} has no findings")
            if not intent.verified_paths:
                errors.append(f"existing gap intent {intent.intent_id} has no verified paths")
        elif intent.intent_origin == "new_feature":
            if not intent.destination_responsibility:
                errors.append(f"new feature intent {intent.intent_id} missing destination responsibility")
    return errors


def validate_evidence_digests(package: AuditDiscoveryPackage) -> list[str]:
    errors: list[str] = []
    for ev in package.evidence:
        if not ev.content_digest:
            errors.append(f"evidence {ev.evidence_id} has empty digest")
    return errors
