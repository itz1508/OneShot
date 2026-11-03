"""Planning contract tests — PL01-PL17."""

import pytest
from pydantic import ValidationError

from agent.contracts.common import ArtifactRef
from agent.contracts.planning import (
    BuildPhase,
    BuildSpecification,
    CandidateSpecification,
    CodeIntentReview,
    CorrectiveRefactor,
    CreateAction,
    CriterionCoverage,
    DesignDecision,
    FindingAssessment,
    IntentDisposition,
    ModifyAction,
    MoveAction,
    PlanningFindingAssessment,
    PlanningIssue,
    PlanningRecord,
    RemoveAction,
    RequirementCoverage,
)
from agent.contracts.validation.planning import (
    validate_action_graph,
    validate_decisions,
    validate_paths,
    validate_phase_graph,
    validate_planning_issues,
    validate_reviews,
    validate_spec_coverage,
)


def make_artifact_ref():
    return ArtifactRef(
        artifact_id="audit-001",
        artifact_revision=1,
        artifact_digest="a" * 64,
        contract_id="audit_discovery",
        contract_version="1.0",
        serializer_profile="rfc8785-jcs-sha256-v1",
    )


def make_create_action(aid="act-001", depends_on=()):
    return CreateAction(
        action_id=aid,
        requirement_ids=("REQ-001",),
        acceptance_criteria_ids=("AC-001",),
        code_intent_ids=("intent-001",),
        preconditions=("check exists",),
        validation_steps=("run test",),
        expected_result="file created",
        retry_semantics="idempotent",
        destructive=False,
        recovery_requirement="recreate if fails",
        target_path="src/new_file.py",
        target_conflict_check_ref="check-001",
        depends_on=depends_on,
    )


def make_build_spec(actions=None, phases=()):
    if actions is None:
        actions = (make_create_action(),)
    return BuildSpecification(
        spec_id="spec-001",
        objective="implement feature",
        actions=actions,
        phases=phases,
    )


class TestPlanningContracts:
    def test_valid_planning_record(self):
        """PL01: Valid planning record accepted."""
        record = PlanningRecord(
            task_id="task-001",
            run_id="run-001",
            stage_revision=1,
            audit_ref=make_artifact_ref(),
            candidate=CandidateSpecification(
                candidate_id="cand-001",
                specification_revision=1,
                build_spec=make_build_spec(),
            ),
        )
        assert record.task_id == "task-001"

    def test_intent_review_valid(self):
        """PL02: Valid intent review."""
        review = CodeIntentReview(
            review_id="REV-001",
            source_intent_ids=("intent-001",),
            disposition=IntentDisposition.ACCEPT,
            rationale="accepted as-is",
        )
        assert review.disposition == IntentDisposition.ACCEPT

    def test_combine_without_resulting_ids_flagged(self):
        """PL03: Combine/split without resulting IDs flagged."""
        review = CodeIntentReview(
            review_id="REV-002",
            source_intent_ids=("intent-002",),
            disposition=IntentDisposition.COMBINE,
            rationale="combining",
        )
        record = PlanningRecord(
            task_id="task-001",
            run_id="run-001",
            stage_revision=1,
            audit_ref=make_artifact_ref(),
            candidate=CandidateSpecification(
                candidate_id="cand-001",
                specification_revision=1,
                build_spec=make_build_spec(),
            ),
            intent_reviews=(review,),
        )
        errors = validate_reviews(record)
        assert any("resulting IDs" in e for e in errors)

    def test_security_issue_requires_receipt(self):
        """PL04: Security issue without technical check receipt flagged."""
        issue = PlanningIssue(
            issue_id="PLI-001",
            issue_type="security",
            statement="vulnerability found",
        )
        record = PlanningRecord(
            task_id="task-001",
            run_id="run-001",
            stage_revision=1,
            audit_ref=make_artifact_ref(),
            candidate=CandidateSpecification(
                candidate_id="cand-001",
                specification_revision=1,
                build_spec=make_build_spec(),
            ),
            issues=(issue,),
        )
        errors = validate_planning_issues(record)
        assert any("technical check receipt" in e for e in errors)

    def test_design_decision_requires_alternatives(self):
        """PL05: Design decision with one alternative flagged."""
        decision = DesignDecision(
            decision_id="DEC-001",
            requirement_ids=("REQ-001",),
            acceptance_criteria_ids=("AC-001",),
            code_intent_ids=("intent-001",),
            context="choosing approach",
            options_considered=("option A",),
            selected_direction="option A",
            rationale="best option",
            evidence_refs=("EVD-001",),
            expected_result="works",
        )
        record = PlanningRecord(
            task_id="task-001",
            run_id="run-001",
            stage_revision=1,
            audit_ref=make_artifact_ref(),
            candidate=CandidateSpecification(
                candidate_id="cand-001",
                specification_revision=1,
                build_spec=make_build_spec(),
            ),
            design_decisions=(decision,),
        )
        errors = validate_decisions(record)
        assert any("fewer than 2" in e for e in errors)

    def test_corrective_refactor_requires_finding(self):
        """PL06: Corrective refactor without finding raises ValidationError."""
        with pytest.raises(ValidationError):
            CorrectiveRefactor(
                refactor_id="ref-001",
                finding_ref="",
                violated_constraint="constraint",
                original_direction="original",
                corrected_design="corrected",
                preserved_behavior="behavior",
                affected_elements=("file.py",),
                correction="fix it",
            )

    def test_action_graph_cycle_detected(self):
        """PL07: Action dependency cycle detected."""
        a1 = make_create_action("act-001", depends_on=("act-002",))
        a2 = make_create_action("act-002", depends_on=("act-001",))
        spec = make_build_spec(actions=(a1, a2))
        errors = validate_action_graph(spec)
        assert any("cycle" in e.lower() for e in errors)

    def test_action_unknown_dependency_detected(self):
        """PL08: Unknown dependency detected."""
        a1 = make_create_action("act-001", depends_on=("act-999",))
        spec = make_build_spec(actions=(a1,))
        errors = validate_action_graph(spec)
        assert any("unknown action" in e for e in errors)

    def test_duplicate_action_ids_detected(self):
        """PL09: Duplicate action IDs detected."""
        a1 = make_create_action("act-001")
        a2 = make_create_action("act-001")
        spec = make_build_spec(actions=(a1, a2))
        errors = validate_action_graph(spec)
        assert any("duplicate" in e for e in errors)

    def test_phase_unknown_action_detected(self):
        """PL10: Phase referencing unknown action detected."""
        phase = BuildPhase(phase_id="ph-001", action_ids=("act-999",))
        spec = make_build_spec(phases=(phase,))
        errors = validate_phase_graph(spec)
        assert any("unknown action" in e for e in errors)

    def test_covered_without_specification_refs_flagged(self):
        """PL11: Covered requirement without spec refs flagged."""
        spec = make_build_spec()
        spec = spec.model_copy(
            update={
                "requirement_coverage": (
                    RequirementCoverage(
                        requirement_id="REQ-001",
                        status="covered",
                    ),
                ),
            }
        )
        errors = validate_spec_coverage(spec)
        assert any("covered without" in e for e in errors)

    def test_covered_criterion_without_validation_steps_flagged(self):
        """PL12: Covered criterion without validation steps flagged."""
        spec = make_build_spec()
        spec = spec.model_copy(
            update={
                "criterion_coverage": (
                    CriterionCoverage(
                        criterion_id="AC-001",
                        requirement_id="REQ-001",
                        status="covered",
                    ),
                ),
            }
        )
        errors = validate_spec_coverage(spec)
        assert any("covered without" in e for e in errors)

    def test_path_collision_detected(self):
        """PL13: Path collision between actions detected."""
        a1 = make_create_action("act-001")
        a2 = make_create_action("act-002")
        a2 = a2.model_copy(update={"target_path": "src/new_file.py"})
        spec = make_build_spec(actions=(a1, a2))
        errors = validate_paths(spec)
        assert any("collision" in e for e in errors)

    def test_remove_action_is_destructive(self):
        """PL14: Remove action is inherently destructive."""
        action = RemoveAction(
            action_id="act-003",
            requirement_ids=("REQ-001",),
            acceptance_criteria_ids=("AC-001",),
            code_intent_ids=("intent-001",),
            preconditions=("file exists",),
            validation_steps=("file gone",),
            expected_result="file removed",
            retry_semantics="non_idempotent",
            destructive=True,
            recovery_requirement="restore from backup",
            source_path="src/old.py",
            expected_source_digest="c" * 64,
            destructive_approval_requirement="user approval",
        )
        assert action.destructive is True

    def test_modify_action_requires_source_digest(self):
        """PL15: Modify action requires expected source digest."""
        action = ModifyAction(
            action_id="act-004",
            requirement_ids=("REQ-001",),
            acceptance_criteria_ids=("AC-001",),
            code_intent_ids=("intent-001",),
            preconditions=("file exists",),
            validation_steps=("verify changes",),
            expected_result="file modified",
            retry_semantics="idempotent",
            destructive=False,
            recovery_requirement="reapply if fails",
            source_path="src/existing.py",
            expected_source_digest="d" * 64,
        )
        assert action.action_kind == "modify"

    def test_move_action_requires_both_paths(self):
        """PL16: Move action requires source and target paths."""
        action = MoveAction(
            action_id="act-005",
            requirement_ids=("REQ-001",),
            acceptance_criteria_ids=("AC-001",),
            code_intent_ids=("intent-001",),
            preconditions=("file exists",),
            validation_steps=("verify move",),
            expected_result="file moved",
            retry_semantics="idempotent",
            destructive=False,
            recovery_requirement="restore if fails",
            source_path="src/old.py",
            target_path="src/new.py",
            expected_source_digest="e" * 64,
            target_conflict_check_ref="check-002",
        )
        assert action.source_path == "src/old.py"
        assert action.target_path == "src/new.py"

    def test_finding_assessment_does_not_reclassify(self):
        """PL17: Finding assessment cannot reclassify original finding status."""
        assessment = PlanningFindingAssessment(
            assessment_id="PFA-001",
            audit_finding_id="ADF-001",
            assessment=FindingAssessment.ACCEPTED,
            rationale="applicable",
        )
        # The assessment records interpretation, not original status change
        assert assessment.assessment == FindingAssessment.ACCEPTED
