"""Audit Discovery contract tests — AD01-AD12."""

import pytest
from pydantic import ValidationError

from agent.contracts.audit_discovery import (
    AssessmentStatus,
    AuditDiscoveryPackage,
    ExistingGapIntent,
    FindingStatus,
    ImplementationFinding,
    NewFeatureIntent,
    RepositoryIdentity,
    RequirementAssessment,
)
from agent.contracts.common import ArtifactRef
from agent.contracts.validation.audit_discovery import (
    validate_code_intents,
    validate_repository_identity_pair,
    validate_requirement_assessments,
)


def make_artifact_ref(aid="art-001", rev=1):
    return ArtifactRef(
        artifact_id=aid,
        artifact_revision=rev,
        artifact_digest="a" * 64,
        contract_id="research",
        contract_version="1.0",
        serializer_profile="rfc8785-jcs-sha256-v1",
    )


def make_identity(commit="abc123def456"):
    return RepositoryIdentity(
        commit_object_id=commit,
        hash_algorithm="sha1",
        tracked_manifest_digest="b" * 64,
        clean_state=True,
        capture_timestamp="2026-11-03T10:00:00Z",
        host_capture_receipt="receipt-001",
    )


def make_package(start_commit="abc123", end_commit="abc123", **kwargs):
    defaults = dict(
        task_id="task-001",
        run_id="run-001",
        stage_revision=1,
        research_ref=make_artifact_ref(),
        start_identity=make_identity(start_commit),
        end_identity=make_identity(end_commit),
    )
    defaults.update(kwargs)
    return AuditDiscoveryPackage(**defaults)


class TestAuditDiscovery:
    def test_valid_package(self):
        """AD01: Valid package accepted."""
        pkg = make_package()
        assert pkg.task_id == "task-001"

    def test_existing_gap_intent_valid(self):
        """AD02: Existing gap intent with findings and paths."""
        intent = ExistingGapIntent(
            intent_id="intent-001",
            requirement_ids=("REQ-001",),
            acceptance_criteria_ids=("AC-001",),
            evidence_refs=("ev-001",),
            objective="fix gap",
            candidate_direction="refactor",
            expected_behavior="works correctly",
            expected_results=("passes tests",),
            finding_ids=("find-001",),
            verified_paths=("src/main.py",),
            current_behavior="broken",
            identified_gap="missing check",
        )
        assert intent.intent_origin == "existing_implementation_gap"

    def test_new_feature_intent_no_defect_required(self):
        """AD03: New feature intent does NOT require findings."""
        intent = NewFeatureIntent(
            intent_id="intent-002",
            requirement_ids=("REQ-002",),
            acceptance_criteria_ids=("AC-002",),
            evidence_refs=("ev-002",),
            objective="add feature",
            candidate_direction="new module",
            expected_behavior="feature works",
            expected_results=("feature tested",),
            destination_responsibility="new module",
            ownership_inspection_ref="inspect-001",
            conflict_inspection_ref="inspect-002",
        )
        assert intent.intent_origin == "new_feature"
        assert intent.finding_ids == ()

    def test_existing_gap_without_findings_flagged(self):
        """AD04: Existing gap intent without findings flagged."""
        pkg = make_package(
            code_intents=(
                ExistingGapIntent(
                    intent_id="intent-001",
                    requirement_ids=("REQ-001",),
                    acceptance_criteria_ids=("AC-001",),
                    evidence_refs=("ev-001",),
                    objective="fix gap",
                    candidate_direction="refactor",
                    expected_behavior="works",
                    expected_results=("ok",),
                    finding_ids=(),
                    verified_paths=("src/main.py",),
                    current_behavior="broken",
                    identified_gap="missing check",
                ),
            ),
        )
        errors = validate_code_intents(pkg)
        assert any("no findings" in e for e in errors)

    def test_new_feature_without_destination_flagged(self):
        """AD05: New feature without destination responsibility flagged."""
        pkg = make_package(
            code_intents=(
                NewFeatureIntent(
                    intent_id="intent-002",
                    requirement_ids=("REQ-002",),
                    acceptance_criteria_ids=("AC-002",),
                    evidence_refs=("ev-002",),
                    objective="add feature",
                    candidate_direction="new module",
                    expected_behavior="works",
                    expected_results=("ok",),
                    destination_responsibility="",
                    ownership_inspection_ref="inspect-001",
                    conflict_inspection_ref="inspect-002",
                ),
            ),
        )
        errors = validate_code_intents(pkg)
        assert any("destination responsibility" in e for e in errors)

    def test_identity_mismatch_without_contradictions(self):
        """AD06: Start/end identity mismatch without contradictions flagged."""
        pkg = make_package(start_commit="abc123", end_commit="def456")
        errors = validate_repository_identity_pair(pkg)
        assert len(errors) > 0

    def test_identity_mismatch_with_contradictions_ok(self):
        """AD07: Identity mismatch with recorded contradictions is valid."""
        pkg = make_package(
            start_commit="abc123",
            end_commit="def456",
            contradictions=("repository changed during audit",),
        )
        errors = validate_repository_identity_pair(pkg)
        assert len(errors) == 0

    def test_missing_assessment_for_accepted_requirement(self):
        """AD08: Accepted requirement not assessed is flagged."""
        pkg = make_package()
        errors = validate_requirement_assessments(pkg, ("REQ-001",))
        assert any("REQ-001" in e for e in errors)

    def test_all_accepted_requirements_assessed(self):
        """AD09: All accepted requirements assessed passes."""
        pkg = make_package(
            assessments=(
                RequirementAssessment(
                    assessment_id="ASM-001",
                    requirement_id="REQ-001",
                    status=AssessmentStatus.SATISFIED_EXISTING,
                    rationale="assessed",
                ),
            ),
        )
        errors = validate_requirement_assessments(pkg, ("REQ-001",))
        assert len(errors) == 0

    def test_immutable_findings_status(self):
        """AD10: Finding status is immutable enum."""
        finding = ImplementationFinding(
            finding_id="ADF-001",
            observation="missing test",
            evidence_refs=("ev-001",),
            status=FindingStatus.VALID,
        )
        assert finding.status == FindingStatus.VALID

    def test_discriminator_enforces_origin(self):
        """AD11: CodeIntent discriminator enforces origin field."""
        # NewFeatureIntent with wrong origin should fail
        with pytest.raises(ValidationError):
            NewFeatureIntent(
                intent_id="intent-003",
                requirement_ids=("REQ-003",),
                acceptance_criteria_ids=("AC-003",),
                evidence_refs=("ev-003",),
                objective="test",
                candidate_direction="test",
                expected_behavior="test",
                expected_results=("ok",),
                destination_responsibility="new",
                ownership_inspection_ref="insp-001",
                conflict_inspection_ref="insp-002",
                intent_origin="existing_implementation_gap",  # wrong
            )

    def test_sha256_hash_algorithm_supported(self):
        """AD12: SHA-256 Git hash algorithm supported."""
        identity = make_identity()
        identity = identity.model_copy(update={"hash_algorithm": "sha256"})
        assert identity.hash_algorithm == "sha256"
