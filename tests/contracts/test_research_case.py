"""Research case lifecycle contract tests — RC01-RC20.

Tests the parent-child ResearchRequest/InputRequest/OutputResult
lifecycle, admission gating, review gating, catalog matching,
fixture specifications, and negative/security cases.
"""

import pytest
from pydantic import ValidationError

from agent.contracts.research import (
    AdmissionDisposition,
    ExecutionStatus,
    FixtureSpecification,
    FixtureValidity,
    FixtureValidityAssessment,
    InputRequest,
    OutputResult,
    ResearchAdmission,
    ResearchIntent,
    ResearchPlan,
    ResearchRequest,
    ReviewDisposition,
    SourceReference,
)
from agent.contracts.validation.research import (
    validate_fixture_spec_completeness,
    validate_input_admission,
    validate_output_binding,
    validate_research_request,
    validate_review_gating,
    validate_stale_revision,
)


def make_admission(disposition=AdmissionDisposition.ACCEPTED, receipt="rec-001"):
    return ResearchAdmission(
        disposition=disposition,
        validation_receipt_ref=receipt if disposition == AdmissionDisposition.ACCEPTED else "",
        rejection_reason="bad input" if disposition == AdmissionDisposition.REJECTED else "",
    )


def make_request(req_id="RR-001"):
    return ResearchRequest(
        request_id=req_id,
        revision=1,
        created_from="USER-001",
        accepted_requirement_refs=("REQ-001",),
    )


def make_input(input_id="RR-IN-001", parent="RR-001", rev=1, disposition=None):
    return InputRequest(
        input_id=input_id,
        parent_request_id=parent,
        revision=rev,
        intent=ResearchIntent.INVESTIGATE_QUESTION,
        provenance_ref="USER-001",
        investigation_question="What exists?",
        expected_result="Findings",
        admission=make_admission(disposition or AdmissionDisposition.ACCEPTED),
    )


def make_output(output_id="RR-OUT-001", parent="RR-001", responds_to="RR-IN-001@1"):
    return OutputResult(
        output_id=output_id,
        parent_request_id=parent,
        revision=1,
        responds_to=responds_to,
        admission_receipt_ref="rec-001",
        execution_status=ExecutionStatus.COMPLETED,
        execution_receipt_ref="output-RR-OUT-001:abc",
        report_ref="report-001",
    )


class TestResearchRequestContract:
    def test_valid_request(self):
        """RC01: Valid ResearchRequest accepted."""
        req = make_request()
        assert req.request_id == "RR-001"
        assert req.revision == 1
        assert req.status == "active"

    def test_request_validation_no_errors(self):
        """RC02: Valid request passes validation."""
        req = make_request()
        errors = validate_research_request(req)
        assert errors == []

    def test_duplicate_child_refs_detected(self):
        """RC03: Duplicate child refs flagged."""
        req = ResearchRequest(
            request_id="RR-001",
            revision=1,
            created_from="USER-001",
            child_refs=("RR-IN-001@1", "RR-IN-001@1"),
        )
        errors = validate_research_request(req)
        assert any("duplicate" in e for e in errors)

    def test_invalid_status_rejected(self):
        """RC04: Invalid status flagged."""
        req = ResearchRequest(
            request_id="RR-001",
            revision=1,
            created_from="USER-001",
            status="unknown",
        )
        errors = validate_research_request(req)
        assert any("invalid" in e.lower() for e in errors)


class TestInputAdmissionContract:
    def test_valid_admitted_input(self):
        """RC05: Valid admitted input accepted."""
        inp = make_input()
        req = make_request()
        errors = validate_input_admission(inp, req)
        assert errors == []

    def test_parent_mismatch_detected(self):
        """RC06: Parent mismatch detected."""
        inp = make_input(parent="WRONG-001")
        req = make_request()
        errors = validate_input_admission(inp, req)
        assert any("parent mismatch" in e for e in errors)

    def test_accepted_requires_receipt(self):
        """RC07: Accepted input requires validation receipt."""
        with pytest.raises(ValidationError):
            ResearchAdmission(
                disposition=AdmissionDisposition.ACCEPTED,
                validation_receipt_ref="",
            )

    def test_rejected_requires_reason(self):
        """RC08: Rejected admission requires reason."""
        with pytest.raises(ValidationError):
            ResearchAdmission(
                disposition=AdmissionDisposition.REJECTED,
                rejection_reason="",
            )

    def test_rejected_input_no_plan(self):
        """RC09: Rejected input should not have research plan."""
        inp = InputRequest(
            input_id="RR-IN-001",
            parent_request_id="RR-001",
            revision=1,
            intent=ResearchIntent.INVESTIGATE_QUESTION,
            provenance_ref="USER-001",
            investigation_question="What?",
            expected_result="Result",
            admission=make_admission(AdmissionDisposition.REJECTED),
            research_plan=ResearchPlan(
                investigation_question="What?",
                completion_criteria="done",
            ),
        )
        req = make_request()
        errors = validate_input_admission(inp, req)
        assert any("research plan" in e for e in errors)

    def test_all_intents_valid(self):
        """RC10: All 7 research intents are valid enums."""
        assert len(ResearchIntent) == 7
        assert ResearchIntent.INVESTIGATE_QUESTION.value == "investigate_question"
        assert ResearchIntent.CRAFT_FIXTURE.value == "craft_fixture"
        assert ResearchIntent.VERIFY_INCOMING_PLAN.value == "verify_incoming_plan"
        assert ResearchIntent.INVESTIGATE_FIXTURE_VALIDATION.value == "investigate_fixture_validation"


class TestOutputBindingContract:
    def test_valid_output_binding(self):
        """RC11: Valid output binding to exact input revision."""
        inp = make_input()
        out = make_output(responds_to="RR-IN-001@1")
        errors = validate_output_binding(out, inp)
        assert errors == []

    def test_stale_revision_rejected(self):
        """RC12: Output binding to wrong input revision detected."""
        inp = make_input(rev=1)
        out = make_output(responds_to="RR-IN-001@2")  # wrong revision
        errors = validate_output_binding(out, inp)
        assert any("mismatch" in e for e in errors)

    def test_parent_mismatch_in_output(self):
        """RC13: Output parent mismatch detected."""
        inp = make_input(parent="RR-001")
        out = make_output(parent="WRONG-001")
        errors = validate_output_binding(out, inp)
        assert any("parent mismatch" in e for e in errors)

    def test_output_requires_admission_receipt(self):
        """RC14: Output missing admission receipt rejected at model level."""
        with pytest.raises(ValidationError):
            OutputResult(
                output_id="RR-OUT-001",
                parent_request_id="RR-001",
                revision=1,
                responds_to="RR-IN-001@1",
                admission_receipt_ref="",
                execution_status=ExecutionStatus.PENDING,
            )


class TestReviewGatingContract:
    def test_completion_does_not_imply_acceptance(self):
        """RC15: Completed output can be pending review."""
        out = make_output()
        errors = validate_review_gating(out)
        assert errors == []  # pending review on completed output is valid

    def test_accepted_requires_receipt(self):
        """RC16: Accepted review requires receipt (enforced at model level)."""
        with pytest.raises(ValidationError):
            OutputResult(
                output_id="RR-OUT-001",
                parent_request_id="RR-001",
                revision=1,
                responds_to="RR-IN-001@1",
                admission_receipt_ref="rec-001",
                execution_status=ExecutionStatus.COMPLETED,
                report_ref="report-001",
                review_disposition=ReviewDisposition.ACCEPTED,
                review_receipt_ref="",
            )

    def test_accepted_requires_completion(self):
        """RC17: Accepted review requires completed execution."""
        out = OutputResult(
            output_id="RR-OUT-001",
            parent_request_id="RR-001",
            revision=1,
            responds_to="RR-IN-001@1",
            admission_receipt_ref="rec-001",
            execution_status=ExecutionStatus.PENDING,
            review_disposition=ReviewDisposition.ACCEPTED,
            review_receipt_ref="rev-001:abc",
        )
        errors = validate_review_gating(out)
        assert any("not completed" in e for e in errors)

    def test_completed_requires_report(self):
        """RC18: Completed output requires report reference."""
        with pytest.raises(ValidationError):
            OutputResult(
                output_id="RR-OUT-001",
                parent_request_id="RR-001",
                revision=1,
                responds_to="RR-IN-001@1",
                admission_receipt_ref="rec-001",
                execution_status=ExecutionStatus.COMPLETED,
                execution_receipt_ref="output-001:abc",
                report_ref="",
            )


class TestFixtureSpecContract:
    def test_valid_fixture_spec(self):
        """RC19: Valid fixture specification accepted."""
        spec = FixtureSpecification(
            fixture_id="FIX-001",
            requirement_ref="REQ-001",
            purpose="test behavior",
            preconditions=("system running",),
            triggering_action="call API",
            expected_behavior="returns 200",
            failure_observations="returns 500",
            required_evidence=("http log",),
        )
        assert spec.fixture_id == "FIX-001"

    def test_fixture_spec_completeness_validation(self):
        """RC20: Incomplete fixture spec rejected at model level."""
        with pytest.raises(ValidationError):
            FixtureSpecification(
                fixture_id="FIX-001",
                requirement_ref="REQ-001",
                purpose="test",
                preconditions=(),  # empty — rejected by min_length=1
                triggering_action="call",
                expected_behavior="ok",
                failure_observations="fail",
                required_evidence=(),  # empty — rejected by min_length=1
            )

    def test_fixture_validity_assessment(self):
        """RC21: Fixture validity assessment works."""
        assessment = FixtureValidityAssessment(
            fixture_ref="FIX-001",
            validity=FixtureValidity.VALID,
            assessment_notes="all fields present",
        )
        assert assessment.validity == FixtureValidity.VALID

    def test_fixture_validity_unknown_ref_detected(self):
        """RC22: Fixture validity referencing unknown fixture detected."""
        assessment = FixtureValidityAssessment(
            fixture_ref="FIX-999",
            validity=FixtureValidity.INVALID,
        )
        out = make_output()
        out_with_assessment = out.model_copy(update={"fixture_validity": (assessment,)})
        errors = validate_fixture_spec_completeness(out_with_assessment)
        assert any("unknown fixture" in e for e in errors)

    def test_all_fixture_validity_values(self):
        """RC23: All 4 fixture validity values are valid."""
        assert len(FixtureValidity) == 4
        assert FixtureValidity.VALID.value == "valid"
        assert FixtureValidity.PARTIALLY_VALID.value == "partially_valid"
        assert FixtureValidity.INVALID.value == "invalid"
        assert FixtureValidity.UNRESOLVED.value == "unresolved"


class TestStaleRevision:
    def test_stale_revision_detected(self):
        """RC24: Stale input revision detected."""
        inp = make_input(rev=1)
        errors = validate_stale_revision(inp, latest_revision=3)
        assert any("stale" in e for e in errors)

    def test_current_revision_ok(self):
        """RC25: Current input revision passes."""
        inp = make_input(rev=3)
        errors = validate_stale_revision(inp, latest_revision=3)
        assert errors == []


class TestSourceAndInformationClassification:
    def test_source_reference(self):
        """RC26: Source reference defaults to unverified."""
        src = SourceReference(
            source_id="src-001",
            source_type="file",
            identity="agent/contracts/research.py",
            version="1.0",
            content_digest="abc123",
        )
        assert src.is_authoritative is False

    def test_information_classifications(self):
        """RC27: All 6 information classifications valid."""
        from agent.contracts.research import InformationClass

        assert len(InformationClass) == 6
        assert InformationClass.VERIFIED_EVIDENCE.value == "verified_evidence"
        assert InformationClass.PROPOSED_OR_SYNTHETIC.value == "proposed_or_synthetic"
        assert InformationClass.CONTRADICTION.value == "contradiction"
