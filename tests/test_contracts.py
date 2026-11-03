"""Test contract validation for CodeIntent and PlanningIssue."""

import pytest
from pydantic import ValidationError

from agent.contracts.audit_discovery import (
    AuditDiscoveryPackage,
    ExistingGapIntent,
    NewFeatureIntent,
    RepositoryIdentity,
)
from agent.contracts.common import ArtifactRef
from agent.contracts.planning import IssueEvidenceStatus, IssueResolutionStatus, PlanningIssue
from agent.contracts.validation import validate_code_intents

HEX = "a" * 64


def test_new_feature_does_not_require_finding():
    intent = NewFeatureIntent(
        intent_id="INT-001",
        requirement_ids=("REQ-001",),
        acceptance_criteria_ids=("AC-001",),
        evidence_refs=("EVD-001",),
        objective="add behavior",
        candidate_direction="add",
        expected_behavior="observable",
        expected_results=("works",),
        ownership_inspection_ref="own",
        conflict_inspection_ref="conf",
    )
    assert intent.finding_ids == ()


def test_existing_gap_without_findings_flagged_by_validator():
    """ExistingGapIntent with empty finding_ids is constructible but flagged by validate_code_intents."""
    identity = RepositoryIdentity(
        commit_object_id="b" * 40,
        tracked_manifest_digest=HEX,
        clean_state=True,
        capture_timestamp="now",
        host_capture_receipt="r",
    )
    pkg = AuditDiscoveryPackage(
        task_id="t",
        run_id="r",
        stage_revision=1,
        research_ref=ArtifactRef(
            artifact_id="research",
            artifact_revision=1,
            artifact_digest=HEX,
            contract_id="research",
            contract_version="1.0",
            serializer_profile="jcs",
        ),
        start_identity=identity,
        end_identity=identity,
        code_intents=(
            ExistingGapIntent(
                intent_id="INT-002",
                requirement_ids=("REQ-001",),
                acceptance_criteria_ids=("AC-001",),
                evidence_refs=("EVD-001",),
                objective="fix",
                candidate_direction="fix",
                expected_behavior="works",
                expected_results=("works",),
                finding_ids=(),
                verified_paths=("src/main.py",),
                current_behavior="broken",
                identified_gap="gap",
            ),
        ),
    )
    errors = validate_code_intents(pkg)
    assert any("finding" in e.lower() for e in errors)


def test_uncertain_issue_cannot_be_corrected():
    with pytest.raises(ValidationError):
        PlanningIssue(
            issue_id="PLI-001",
            issue_type="compatibility",
            statement="uncertain",
            evidence_status=IssueEvidenceStatus.UNCERTAINTY,
            resolution_status=IssueResolutionStatus.CORRECTED,
            resolution="changed",
        )
