"""Research lifecycle E2E tests — LC01-LC20.

Tests the connected host lifecycle: create → admit → produce → review →
handoff, plus corrections, crash-safe reconciliation, and adversarial
security cases (receipt forgery, stale revision, duplicate IDs,
unverified claims, and invalid inputs).
"""

import pytest
from pydantic import BaseModel

from agent.contracts.research import (
    AdmissionDisposition,
    CatalogMatchStatus,
    ExecutionStatus,
    FixtureSpecification,
    FixtureValidity,
    FixtureValidityAssessment,
    ResearchIntent,
    ReviewDisposition,
)
from agent.runtime.artifact_store import ArtifactStore
from agent.runtime.event_store import EventStore
from agent.runtime.receipt_store import ReceiptStore
from agent.runtime.research_lifecycle import ResearchLifecycle, ResearchLifecycleError


class _DummyReport(BaseModel):
    """Minimal model for storing a report artifact in tests."""

    title: str = "report"


def _store_report(store: ArtifactStore, report_id: str = "report-001") -> str:
    """Store a dummy report artifact and return its ID."""
    report = _DummyReport(title=f"report-{report_id}")
    store.put_immutable(report, report_id, 1, "research_report", "1.0")
    return report_id


@pytest.fixture
def lifecycle(tmp_path):
    store = ArtifactStore(tmp_path)
    receipts = ReceiptStore(tmp_path)
    events = EventStore(tmp_path)
    # Pre-store the default report artifact
    _store_report(store, "report-001")
    lc = ResearchLifecycle(store, receipts, events)
    lc._test_store = store
    lc._test_receipts = receipts
    return lc


class TestLifecycleBasics:
    def test_create_request(self, lifecycle):
        """LC01: Create ResearchRequest parent case."""
        req = lifecycle.create_request("RR-001", "USER-001", ("REQ-001",))
        assert req.request_id == "RR-001"
        assert req.revision == 1
        assert req.status == "active"

    def test_admit_input(self, lifecycle):
        """LC02: Admit an InputRequest with host receipt."""
        lifecycle.create_request("RR-001", "USER-001")
        inp = lifecycle.admit_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.INVESTIGATE_QUESTION,
            "USER-001",
            "What exists?",
            "Findings",
            related_requirement_refs=("REQ-001",),
            keywords=("code", "pattern"),
        )
        assert inp.admission.disposition == AdmissionDisposition.ACCEPTED
        assert inp.admission.validation_receipt_ref
        assert len(inp.catalog_matches) == 1

    def test_produce_output(self, lifecycle):
        """LC03: Produce OutputResult bound to exact input revision."""
        lifecycle.create_request("RR-001", "USER-001")
        lifecycle.admit_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.INVESTIGATE_QUESTION,
            "USER-001",
            "What?",
            "Findings",
        )
        out = lifecycle.produce_output(
            "RR-OUT-001",
            "RR-001",
            "RR-IN-001",
            1,
            report_ref="report-001",
        )
        assert out.execution_status == ExecutionStatus.COMPLETED
        assert out.responds_to == "RR-IN-001@1"

    def test_review_accepted(self, lifecycle):
        """LC04: Review acceptance with host receipt."""
        lifecycle.create_request("RR-001", "USER-001")
        lifecycle.admit_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.INVESTIGATE_QUESTION,
            "USER-001",
            "What?",
            "Findings",
        )
        lifecycle.produce_output(
            "RR-OUT-001",
            "RR-001",
            "RR-IN-001",
            1,
            report_ref="report-001",
        )
        reviewed = lifecycle.review_output("RR-OUT-001", ReviewDisposition.ACCEPTED)
        assert reviewed.review_disposition == ReviewDisposition.ACCEPTED
        assert reviewed.review_receipt_ref

    def test_handoff_to_planning(self, lifecycle):
        """LC05: Accepted output handoff to Planning."""
        lifecycle.create_request("RR-001", "USER-001")
        lifecycle.admit_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.INVESTIGATE_QUESTION,
            "USER-001",
            "What?",
            "Findings",
        )
        lifecycle.produce_output(
            "RR-OUT-001",
            "RR-001",
            "RR-IN-001",
            1,
            report_ref="report-001",
        )
        lifecycle.review_output("RR-OUT-001", ReviewDisposition.ACCEPTED)
        handed = lifecycle.handoff_to_planning("RR-OUT-001")
        assert handed.review_disposition == ReviewDisposition.ACCEPTED


class TestLifecycleCorrection:
    def test_correction_preserves_prior_revision(self, lifecycle):
        """LC06: Corrections preserve prior revisions."""
        lifecycle.create_request("RR-001", "USER-001")
        lifecycle.admit_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.INVESTIGATE_QUESTION,
            "USER-001",
            "Original question?",
            "Original findings",
        )
        # Create correction
        corr = lifecycle.create_correction_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.INVESTIGATE_QUESTION,
            "USER-001",
            "Updated question?",
            "Updated findings",
        )
        assert corr.revision == 2
        # Original revision still exists
        orig = lifecycle.get_input("RR-IN-001", 1)
        assert orig.investigation_question == "Original question?"

    def test_parent_indexes_updated(self, lifecycle):
        """LC07: Parent indexes updated with new child references."""
        lifecycle.create_request("RR-001", "USER-001")
        lifecycle.admit_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.INVESTIGATE_QUESTION,
            "USER-001",
            "What?",
            "Findings",
        )
        req = lifecycle.get_request("RR-001")
        assert any("RR-IN-001@1" in c for c in req.child_refs)
        assert req.current_input_ref == "RR-IN-001@1"


class TestLifecycleCrashRecovery:
    def test_reconcile_after_restart(self, lifecycle, tmp_path):
        """LC08: Reconcile loads latest state after restart."""
        lifecycle.create_request("RR-001", "USER-001")
        lifecycle.admit_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.INVESTIGATE_QUESTION,
            "USER-001",
            "What?",
            "Findings",
        )
        lifecycle.produce_output(
            "RR-OUT-001",
            "RR-001",
            "RR-IN-001",
            1,
            report_ref="report-001",
        )
        lifecycle.review_output("RR-OUT-001", ReviewDisposition.ACCEPTED)

        # Simulate restart with new lifecycle instance
        store2 = ArtifactStore(tmp_path)
        receipts2 = ReceiptStore(tmp_path)
        events2 = EventStore(tmp_path)
        lc2 = ResearchLifecycle(store2, receipts2, events2)

        req = lc2.reconcile("RR-001")
        assert req.current_accepted_result_ref is not None
        assert "RR-OUT-001" in req.current_accepted_result_ref

    def test_parent_child_persist_and_reload(self, lifecycle, tmp_path):
        """LC09: Parent and child records persist and reload."""
        lifecycle.create_request("RR-001", "USER-001")
        lifecycle.admit_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.INVESTIGATE_QUESTION,
            "USER-001",
            "What?",
            "Findings",
        )
        lifecycle.produce_output(
            "RR-OUT-001",
            "RR-001",
            "RR-IN-001",
            1,
            report_ref="report-001",
        )

        # Reload from new stores
        store2 = ArtifactStore(tmp_path)
        receipts2 = ReceiptStore(tmp_path)
        events2 = EventStore(tmp_path)
        lc2 = ResearchLifecycle(store2, receipts2, events2)

        req = lc2.get_request("RR-001")
        inp = lc2.get_input("RR-IN-001")
        out = lc2.get_output("RR-OUT-001")
        assert req.request_id == "RR-001"
        assert inp.input_id == "RR-IN-001"
        assert out.output_id == "RR-OUT-001"


class TestAdversarialSecurity:
    def test_duplicate_input_id_rejected(self, lifecycle):
        """LC10: Duplicate input ID rejected."""
        lifecycle.create_request("RR-001", "USER-001")
        lifecycle.admit_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.INVESTIGATE_QUESTION,
            "USER-001",
            "What?",
            "Findings",
        )
        with pytest.raises(ResearchLifecycleError, match="already exists"):
            lifecycle.admit_input(
                "RR-IN-001",
                "RR-001",
                ResearchIntent.INVESTIGATE_QUESTION,
                "USER-001",
                "Again?",
                "More findings",
            )

    def test_output_to_nonexistent_parent_rejected(self, lifecycle):
        """LC11: Output to nonexistent parent rejected."""
        with pytest.raises(ResearchLifecycleError, match="not found"):
            lifecycle.produce_output(
                "RR-OUT-001",
                "NONEXISTENT",
                "RR-IN-001",
                1,
                report_ref="r",
            )

    def test_output_to_unadmitted_input_rejected(self, lifecycle):
        """LC12: Output to unadmitted input rejected (unverified claim)."""
        lifecycle.create_request("RR-001", "USER-001")
        # Manually store an unadmitted input by writing to artifact store
        from agent.contracts.research import InputRequest, ResearchAdmission

        unadmitted = InputRequest(
            input_id="RR-IN-BAD",
            parent_request_id="RR-001",
            revision=1,
            intent=ResearchIntent.INVESTIGATE_QUESTION,
            provenance_ref="USER-001",
            investigation_question="What?",
            expected_result="Result",
            admission=ResearchAdmission(
                disposition=AdmissionDisposition.ISOLATED,
            ),
        )
        lifecycle._artifacts.put_immutable(
            unadmitted,
            "RR-IN-BAD",
            1,
            "research_input",
            "1.0",
        )
        with pytest.raises(ResearchLifecycleError, match="not admitted"):
            lifecycle.produce_output(
                "RR-OUT-001",
                "RR-001",
                "RR-IN-BAD",
                1,
                report_ref="r",
            )

    def test_handoff_without_acceptance_rejected(self, lifecycle):
        """LC13: Handoff without review acceptance rejected."""
        lifecycle.create_request("RR-001", "USER-001")
        lifecycle.admit_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.INVESTIGATE_QUESTION,
            "USER-001",
            "What?",
            "Findings",
        )
        lifecycle.produce_output(
            "RR-OUT-001",
            "RR-001",
            "RR-IN-001",
            1,
            report_ref="report-001",
        )
        # Output is completed but not reviewed (pending)
        with pytest.raises(ResearchLifecycleError, match="not accepted"):
            lifecycle.handoff_to_planning("RR-OUT-001")

    def test_handoff_with_rejected_review_rejected(self, lifecycle):
        """LC14: Handoff after rejected review is rejected."""
        lifecycle.create_request("RR-001", "USER-001")
        lifecycle.admit_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.INVESTIGATE_QUESTION,
            "USER-001",
            "What?",
            "Findings",
        )
        lifecycle.produce_output(
            "RR-OUT-001",
            "RR-001",
            "RR-IN-001",
            1,
            report_ref="report-001",
        )
        lifecycle.review_output("RR-OUT-001", ReviewDisposition.REJECTED)
        with pytest.raises(ResearchLifecycleError, match="not accepted"):
            lifecycle.handoff_to_planning("RR-OUT-001")

    def test_output_to_wrong_input_revision_rejected(self, lifecycle):
        """LC15: Output binding to wrong input revision rejected."""
        lifecycle.create_request("RR-001", "USER-001")
        lifecycle.admit_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.INVESTIGATE_QUESTION,
            "USER-001",
            "What?",
            "Findings",
        )
        # Try to produce output claiming input is at revision 99
        with pytest.raises(Exception):
            lifecycle.produce_output(
                "RR-OUT-001",
                "RR-001",
                "RR-IN-001",
                99,
                report_ref="r",
            )

    def test_receipt_forgery_detected(self, lifecycle, tmp_path):
        """LC16: Forged review receipt is rejected at handoff."""
        lifecycle.create_request("RR-001", "USER-001")
        lifecycle.admit_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.INVESTIGATE_QUESTION,
            "USER-001",
            "What?",
            "Findings",
        )
        lifecycle.produce_output(
            "RR-OUT-001",
            "RR-001",
            "RR-IN-001",
            1,
            report_ref="report-001",
        )
        # Manually create an output with a forged review receipt
        from agent.contracts.research import OutputResult

        forged = OutputResult(
            output_id="RR-OUT-001",
            parent_request_id="RR-001",
            revision=3,
            responds_to="RR-IN-001@1",
            admission_receipt_ref="rec-001",
            execution_status=ExecutionStatus.COMPLETED,
            execution_receipt_ref="output-RR-OUT-001:fake",
            report_ref="report-001",
            review_disposition=ReviewDisposition.ACCEPTED,
            review_receipt_ref="forged:0" * 32,
        )
        lifecycle._artifacts.put_immutable(
            forged,
            "RR-OUT-001",
            3,
            "research_output",
            "1.0",
        )
        with pytest.raises(ResearchLifecycleError, match="verification failed"):
            lifecycle.handoff_to_planning("RR-OUT-001")


class TestFixtureSupport:
    def test_fixture_spec_in_output(self, lifecycle):
        """LC17: Fixture specification in output."""
        lifecycle.create_request("RR-001", "USER-001")
        lifecycle.admit_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.CRAFT_FIXTURE,
            "USER-001",
            "Need fixture",
            "Fixture spec",
            keywords=("fixture", "test"),
        )
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
        validity = FixtureValidityAssessment(
            fixture_ref="FIX-001",
            validity=FixtureValidity.VALID,
        )
        out = lifecycle.produce_output(
            "RR-OUT-001",
            "RR-001",
            "RR-IN-001",
            1,
            report_ref="report-001",
            fixture_specs=(spec,),
            fixture_validity=(validity,),
        )
        assert len(out.fixture_specs) == 1
        assert out.fixture_specs[0].fixture_id == "FIX-001"
        assert len(out.fixture_validity) == 1
        assert out.fixture_validity[0].validity == FixtureValidity.VALID

    def test_fixture_validity_independent_of_execution(self):
        """LC18: Fixture validity is independent of product validation."""
        assessment = FixtureValidityAssessment(
            fixture_ref="FIX-001",
            validity=FixtureValidity.PARTIALLY_VALID,
            assessment_notes="missing false-positive protections",
            gaps=("no false-positive check",),
        )
        assert assessment.validity != FixtureValidity.VALID
        assert len(assessment.gaps) > 0


class TestCatalogInLifecycle:
    def test_catalog_match_in_admitted_input(self, lifecycle):
        """LC19: Catalog match recorded in admitted input."""
        lifecycle.create_request("RR-001", "USER-001")
        inp = lifecycle.admit_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.CRAFT_FIXTURE,
            "USER-001",
            "Need fixture",
            "Spec",
            keywords=("fixture", "test"),
        )
        assert len(inp.catalog_matches) == 1
        match = inp.catalog_matches[0]
        assert match.catalog_id == "SAMPLE-FIXTURE-001"
        assert match.match_status == CatalogMatchStatus.EXACT
        assert match.is_synthetic is True

    def test_no_match_continues_research(self, lifecycle):
        """LC20: No-match continues with task-specific investigation."""
        lifecycle.create_request("RR-001", "USER-001")
        inp = lifecycle.admit_input(
            "RR-IN-001",
            "RR-001",
            ResearchIntent.INVESTIGATE_QUESTION,
            "USER-001",
            "What?",
            "Findings",
            keywords=("cooking", "recipe"),
        )
        # Research continues regardless of match status
        assert inp.admission.disposition == AdmissionDisposition.ACCEPTED
        # Match is partial (intent matches, keywords don't)
        assert inp.catalog_matches[0].match_status == CatalogMatchStatus.PARTIAL
