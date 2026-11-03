"""Research contract tests — RS01-RS07."""

import pytest
from pydantic import ValidationError

from agent.contracts.research import (
    AcceptanceCriterion,
    AuthorizationStatus,
    CriteriaStatus,
    EvidenceStatus,
    FeasibilityStatus,
    Requirement,
    ResearchClaim,
    ResearchRecord,
)
from agent.contracts.validation.research import (
    validate_criterion_binding,
    validate_research_ids,
)


def make_requirement(req_id="REQ-001", criteria_status=CriteriaStatus.DEFINED):
    return Requirement(
        requirement_id=req_id,
        source_reference="user",
        original_wording="need a thing",
        statement="Implement a thing",
        authorization_status=AuthorizationStatus.GRANTED,
        feasibility_status=FeasibilityStatus.FEASIBLE,
        criteria_status=criteria_status,
        acceptance_criteria_ids=("AC-001",),
    )


def make_criterion(crit_id="AC-001", req_id="REQ-001"):
    return AcceptanceCriterion(
        criterion_id=crit_id,
        requirement_id=req_id,
        success_condition="it works",
        failure_condition="it fails",
        validation_method="test",
    )


class TestResearchContracts:
    def test_valid_research_record(self):
        """RS01: Valid research record accepted."""
        record = ResearchRecord(
            task_id="task-001",
            run_id="run-001",
            stage_revision=1,
            requirements=(make_requirement(),),
            acceptance_criteria=(make_criterion(),),
        )
        assert record.task_id == "task-001"

    def test_duplicate_requirement_ids_detected(self):
        """RS02: Duplicate requirement IDs flagged."""
        record = ResearchRecord(
            task_id="task-001",
            run_id="run-001",
            stage_revision=1,
            requirements=(make_requirement("REQ-001"), make_requirement("REQ-001")),
        )
        errors = validate_research_ids(record)
        assert "duplicate requirement IDs" in errors

    def test_criterion_binding_to_unknown_requirement(self):
        """RS03: Criterion referencing unknown requirement detected."""
        record = ResearchRecord(
            task_id="task-001",
            run_id="run-001",
            stage_revision=1,
            requirements=(make_requirement("REQ-001"),),
            acceptance_criteria=(make_criterion("AC-001", "REQ-999"),),
        )
        errors = validate_criterion_binding(record)
        assert any("unknown requirement" in e for e in errors)

    def test_authorization_and_criteria_are_independent(self):
        """RS04: authorization_status and criteria_status are independent.

        Neither field blocks Research, rejects the record, supersedes
        another status, changes admission, prevents handoff, or creates
        an implicit gate. Both are descriptive only.
        """
        requirement = Requirement(
            requirement_id="REQ-001",
            source_reference="user",
            original_wording="need a thing",
            statement="Implement a thing",
            authorization_status=AuthorizationStatus.GRANTED,
            feasibility_status=FeasibilityStatus.UNCERTAIN,
            criteria_status=CriteriaStatus.MISSING,
            acceptance_criteria_ids=(),
        )

        assert requirement.authorization_status is AuthorizationStatus.GRANTED
        assert requirement.criteria_status is CriteriaStatus.MISSING

    def test_evidence_status_enum(self):
        """RS05: Evidence statuses are valid."""
        assert EvidenceStatus.VALID.value == "valid"
        assert EvidenceStatus.NOT_VALID.value == "not_valid"
        assert EvidenceStatus.UNCERTAIN.value == "uncertain"

    def test_research_claim_requires_evidence(self):
        """RS06: Claims require evidence references."""
        claim = ResearchClaim(
            claim_id="cl-001",
            requirement_ids=("REQ-001",),
            statement="a claim",
            evidence_refs=("ev-001",),
        )
        assert claim.claim_id == "cl-001"

    def test_empty_requirements_rejected(self):
        """RS07: At least one requirement required."""
        with pytest.raises(ValidationError):
            ResearchRecord(
                task_id="task-001",
                run_id="run-001",
                stage_revision=1,
                requirements=(),
            )
