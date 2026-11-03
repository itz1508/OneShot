"""Test cross-stage validation: audit lineage and build specification."""

from agent.contracts.audit_discovery import (
    AssessmentStatus,
    AuditDiscoveryPackage,
    NewFeatureIntent,
    RepositoryIdentity,
    RequirementAssessment,
)
from agent.contracts.common import ArtifactRef
from agent.contracts.planning import (
    BuildSpecification,
    RequirementCoverage,
)
from agent.contracts.research import (
    AcceptanceCriterion,
    AuthorizationStatus,
    Requirement,
    ResearchRecord,
)
from agent.contracts.validation import validate_audit_lineage, validate_build_specification

HEX = "a" * 64


def make_records():
    research = ResearchRecord(
        task_id="task",
        run_id="r",
        stage_revision=1,
        requirements=(
            Requirement(
                requirement_id="REQ-001",
                source_reference="u",
                original_wording="x",
                statement="x",
                authorization_status=AuthorizationStatus.GRANTED,
                acceptance_criteria_ids=("AC-001",),
            ),
        ),
        acceptance_criteria=(
            AcceptanceCriterion(
                criterion_id="AC-001",
                requirement_id="REQ-001",
                success_condition="yes",
                failure_condition="no",
                validation_method="test",
            ),
        ),
    )
    identity = RepositoryIdentity(
        commit_object_id="b" * 40,
        tracked_manifest_digest=HEX,
        clean_state=True,
        capture_timestamp="now",
        host_capture_receipt="r",
    )
    intent = NewFeatureIntent(
        intent_id="INT-001",
        requirement_ids=("REQ-001",),
        acceptance_criteria_ids=("AC-001",),
        evidence_refs=("EVD-001",),
        objective="add",
        candidate_direction="add",
        expected_behavior="yes",
        expected_results=("yes",),
        ownership_inspection_ref="own",
        conflict_inspection_ref="conf",
    )
    audit = AuditDiscoveryPackage(
        task_id="task",
        run_id="a",
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
        assessments=(
            RequirementAssessment(
                assessment_id="ASM-001",
                requirement_id="REQ-001",
                acceptance_criteria_ids=("AC-001",),
                status=AssessmentStatus.UNSATISFIED,
                current_implementation="none",
                expected_behavior="yes",
                code_intent_required=True,
                rationale="new",
            ),
        ),
        code_intents=(intent,),
    )
    return research, audit


def test_cross_stage_lineage():
    research, audit = make_records()
    validate_audit_lineage(research, audit)


def test_build_spec_validation():
    research, audit = make_records()
    from agent.contracts.planning import CreateAction

    spec = BuildSpecification(
        spec_id="spec-001",
        objective="build",
        actions=(
            CreateAction(
                action_id="ACT-001",
                requirement_ids=("REQ-001",),
                acceptance_criteria_ids=("AC-001",),
                code_intent_ids=("INT-001",),
                preconditions=("start",),
                validation_steps=("run tests",),
                expected_result="works",
                recovery_requirement="restore",
                target_path="app/new.py",
                target_conflict_check_ref="check",
            ),
        ),
        requirement_coverage=(
            RequirementCoverage(
                requirement_id="REQ-001",
                status="covered",
                criterion_refs=("AC-001",),
                specification_refs=("ACT-001",),
            ),
        ),
    )
    validate_build_specification(spec, research, audit)
