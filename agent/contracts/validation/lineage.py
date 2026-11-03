"""Lineage validators — artifact chain, receipt subject, frozen equality."""

from __future__ import annotations

from agent.contracts.common import ArtifactRef


def validate_artifact_chain(refs: list[ArtifactRef]) -> list[str]:
    """Check that a chain of artifacts has consistent IDs and increasing revisions."""
    errors: list[str] = []
    for i in range(1, len(refs)):
        if refs[i].artifact_id != refs[i - 1].artifact_id:
            errors.append(f"artifact ID changed from {refs[i - 1].artifact_id} to {refs[i].artifact_id}")
        if refs[i].artifact_revision <= refs[i - 1].artifact_revision:
            errors.append(f"revision did not increase: {refs[i - 1].artifact_revision} -> {refs[i].artifact_revision}")
    return errors


def validate_receipt_subject(receipt_subject: str, expected_subject: str) -> list[str]:
    errors: list[str] = []
    if receipt_subject != expected_subject:
        errors.append(f"receipt subject mismatch: {receipt_subject} != {expected_subject}")
    return errors


def validate_frozen_candidate_equality(frozen_ref: ArtifactRef, candidate_ref: ArtifactRef) -> list[str]:
    errors: list[str] = []
    if frozen_ref.artifact_digest != candidate_ref.artifact_digest:
        errors.append("frozen digest does not match candidate digest")
    return errors


def validate_revision_invalidation(old_ref: ArtifactRef, new_ref: ArtifactRef, bytes_changed: bool) -> list[str]:
    errors: list[str] = []
    if bytes_changed and new_ref.artifact_revision <= old_ref.artifact_revision:
        errors.append("bytes changed but revision did not increase")
    if not bytes_changed and new_ref.artifact_revision != old_ref.artifact_revision:
        errors.append("bytes unchanged but revision changed")
    return errors
