"""Gate B red tests — Plan applicability decisions (USE / DO_NOT_USE / VALIDATE_FIRST).

These tests describe the behavior Gate B must deliver. They are intentionally
RED on the baseline source (bba1a26 + Gate A commit 5283614) and must flip
GREEN once Gate B lands, without breaking any existing test.

The behavior under test:

1. The Plan contract exposes a `claim_decisions` collection (one decision per
   externally-sourced Research claim). Each decision has:
     - `id`
     - `source_finding_id` — references `research.search.findings[].id`
     - `applicability` — one of USE / DO_NOT_USE / VALIDATE_FIRST
     - `reason`
     - `evidence_refs` (resolver-verifiable)
     - `affected_step_ids` — the Plan milestone / step IDs the decision governs
     - `revision` and `recorded_at`

2. Cross-record validation (`validate_pipeline` / `validate_records`) rejects:
     - unsupported Research findings that have NO corresponding Plan decision
     - decisions that reference a non-existent finding
     - decisions whose `affected_step_ids` reference a non-existent milestone
     - a Build step whose provenance traces to a `DO_NOT_USE`-decided claim

3. The existing structural invariant stays: an unsupported finding MUST have
   `evidence_refs` (noise is still rejected at the Research layer).

4. The migrated `test_unsupported_research_finding` behavior: an unsupported
   finding is PERMITTED when the Plan binds a DO_NOT_USE decision to it; it
   remains REJECTED when no such decision exists.

These tests use the same fixture triple as `tests/test_workflow_contracts.py`
to anchor the "triple that passes today" and vary ONE aspect at a time.
"""

from __future__ import annotations

import copy
import unittest

# Reuse the known-valid fixture from the baseline suite (which imports from
# agent/contracts/models.py via the pythonpath configured in pyproject.toml).
from tests.test_workflow_contracts import ContractTest as _BaselineContractTest


class ClaimDecisionShapeTest(_BaselineContractTest):
    """The Plan must accept and validate a `claim_decisions` field."""

    def test_valid_use_decision_passes(self):
        """A plan carrying a USE decision for a supported finding validates."""
        self.p["claim_decisions"] = [
            {
                "id": "d1",
                "source_finding_id": "F1",
                "applicability": "USE",
                "reason": "supported by direct source observation",
                "evidence_refs": ["source"],
                "affected_step_ids": ["m1"],
                "revision": 2,
                "recorded_at": "2026-10-30T03:00:00Z",
            }
        ]
        self.assertEqual(self.check(), [])

    def test_decision_references_unknown_finding_fails(self):
        """A decision referencing a finding ID not present in Research is rejected."""
        self.p["claim_decisions"] = [
            {
                "id": "d1",
                "source_finding_id": "F_DOES_NOT_EXIST",
                "applicability": "USE",
                "reason": "x",
                "evidence_refs": [],
                "affected_step_ids": ["m1"],
                "revision": 2,
                "recorded_at": "2026-10-30T03:00:00Z",
            }
        ]
        errors = self.check()
        self.assertTrue(
            any("decision" in e.lower() and "unknown finding" in e.lower() for e in errors),
            f"expected 'unknown finding' error; got: {errors}",
        )

    def test_decision_references_unknown_step_fails(self):
        """A decision whose `affected_step_ids` points at a non-existent milestone is rejected."""
        self.p["claim_decisions"] = [
            {
                "id": "d1",
                "source_finding_id": "F1",
                "applicability": "USE",
                "reason": "x",
                "evidence_refs": ["source"],
                "affected_step_ids": ["m_DOES_NOT_EXIST"],
                "revision": 2,
                "recorded_at": "2026-10-30T03:00:00Z",
            }
        ]
        errors = self.check()
        self.assertTrue(
            any("decision" in e.lower() and "unknown step" in e.lower() for e in errors),
            f"expected 'unknown step' error; got: {errors}",
        )

    def test_decision_bad_applicability_fails(self):
        """Only USE / DO_NOT_USE / VALIDATE_FIRST are permitted applicability values."""
        self.p["claim_decisions"] = [
            {
                "id": "d1",
                "source_finding_id": "F1",
                "applicability": "MAYBE_USE",  # invalid
                "reason": "x",
                "evidence_refs": ["source"],
                "affected_step_ids": ["m1"],
                "revision": 2,
                "recorded_at": "2026-10-30T03:00:00Z",
            }
        ]
        errors = self.check()
        self.assertTrue(
            any("applicability" in e.lower() for e in errors),
            f"expected 'applicability' error; got: {errors}",
        )


class UnsupportedFindingDecisionGatingTest(_BaselineContractTest):
    """B04 — the key semantic change.

    Current (baseline) rule: `assessment != 'supported'` → block Research
    completion.

    New rule: an unsupported Research finding is PERMITTED to be retained in
    a COMPLETE Research record IFF the Plan carries a DO_NOT_USE (or
    VALIDATE_FIRST) decision binding that finding. Without such a decision,
    the finding is rejected.

    Research-level structural check (unsupported finding must have
    `evidence_refs`) remains in force.
    """

    def test_unsupported_finding_with_do_not_use_decision_passes(self):
        """S2 case: Research retains an unsupported external claim; Plan binds DO_NOT_USE."""
        self.r["search"]["findings"][0]["assessment"] = "uncertain"
        # The finding retains evidence (unchanged); the Plan now carries the gate.
        self.p["claim_decisions"] = [
            {
                "id": "d1",
                "source_finding_id": "F1",
                "applicability": "DO_NOT_USE",
                "reason": "external claim unsupported by source inspection",
                "evidence_refs": ["source"],
                "affected_step_ids": [],
                "revision": 2,
                "recorded_at": "2026-10-30T03:00:00Z",
            }
        ]
        errors = self.check()
        self.assertEqual(
            errors, [], f"expected clean validation after DO_NOT_USE decision; got: {errors}"
        )

    def test_unsupported_finding_without_decision_still_fails(self):
        """Without any Plan decision, an unsupported finding remains blocking."""
        self.r["search"]["findings"][0]["assessment"] = "uncertain"
        # No Plan decision bound.
        errors = self.check()
        self.assertTrue(
            any("unsupported finding" in e for e in errors),
            f"expected 'unsupported finding' error without decision; got: {errors}",
        )

    def test_unsupported_finding_with_validate_first_passes(self):
        """VALIDATE_FIRST is also a legitimate way to retain an unsupported finding.

        While the gate is active, the Build must not have accepted the
        affected milestone — otherwise it is a stale admission (that is
        the shape of the Scenario-3 negative control). The passing case
        is: VALIDATE_FIRST declared, Build has not yet accepted m1.
        """
        self.r["search"]["findings"][0]["assessment"] = "uncertain"
        # Build has not resumed yet (S3 handoff shape).
        self.b["plan_input"]["accepted_milestone_ids"] = []
        self.p["claim_decisions"] = [
            {
                "id": "d1",
                "source_finding_id": "F1",
                "applicability": "VALIDATE_FIRST",
                "reason": "evidence inconclusive; dependent step gated pending new evidence",
                "evidence_refs": ["source"],
                "affected_step_ids": ["m1"],
                "revision": 2,
                "recorded_at": "2026-10-30T03:00:00Z",
            }
        ]
        errors = self.check()
        self.assertEqual(
            errors, [], f"expected clean validation after VALIDATE_FIRST decision; got: {errors}"
        )

    def test_unsupported_finding_decision_still_requires_evidence_refs(self):
        """Even with a decision, the finding itself must still carry evidence_refs."""
        self.r["search"]["findings"][0]["assessment"] = "uncertain"
        self.r["search"]["findings"][0]["evidence_refs"] = []  # strip evidence
        self.p["claim_decisions"] = [
            {
                "id": "d1",
                "source_finding_id": "F1",
                "applicability": "DO_NOT_USE",
                "reason": "x",
                "evidence_refs": ["source"],
                "affected_step_ids": [],
                "revision": 2,
                "recorded_at": "2026-10-30T03:00:00Z",
            }
        ]
        errors = self.check()
        self.assertTrue(
            any("evidence" in e.lower() for e in errors),
            f"expected an evidence-related error; got: {errors}",
        )


class BuildAdmissionProvenanceTest(_BaselineContractTest):
    """A Build step whose provenance traces to a DO_NOT_USE-decided claim is rejected."""

    def test_do_not_use_blocks_dependent_build_step(self):
        """S2 negative control: a build milestone claiming provenance from
        an unsupported, DO_NOT_USE-decided finding is rejected at validate_pipeline."""
        self.r["search"]["findings"][0]["assessment"] = "uncertain"
        self.p["claim_decisions"] = [
            {
                "id": "d1",
                "source_finding_id": "F1",
                "applicability": "DO_NOT_USE",
                "reason": "x",
                "evidence_refs": ["source"],
                "affected_step_ids": ["m1"],
                "revision": 2,
                "recorded_at": "2026-10-30T03:00:00Z",
            }
        ]
        # Build claims milestone m1 is accepted — this must be refused because
        # the Plan has decided the finding m1 depends on is DO_NOT_USE.
        errors = self.check()
        self.assertTrue(
            any("do_not_use" in e.lower() and "m1" in e.lower() for e in errors),
            f"expected 'DO_NOT_USE' admission error referencing step m1; got: {errors}",
        )


class ValidateFirstGatingTest(_BaselineContractTest):
    """VALIDATE_FIRST blocks a dependent build step until evidence is updated."""

    def test_validate_first_blocks_dependent_build_step(self):
        """S3 case: a VALIDATE_FIRST decision gates the dependent milestone."""
        self.r["search"]["findings"][0]["assessment"] = "uncertain"
        self.p["claim_decisions"] = [
            {
                "id": "d1",
                "source_finding_id": "F1",
                "applicability": "VALIDATE_FIRST",
                "reason": "evidence inconclusive",
                "evidence_refs": ["source"],
                "affected_step_ids": ["m1"],
                "revision": 2,
                "recorded_at": "2026-10-30T03:00:00Z",
            }
        ]
        # Build claims milestone m1 passed, but Plan says validate first.
        errors = self.check()
        self.assertTrue(
            any("validate_first" in e.lower() and "m1" in e.lower() for e in errors),
            f"expected 'VALIDATE_FIRST' gating error referencing step m1; got: {errors}",
        )


class DuplicateDecisionsTest(_BaselineContractTest):
    """Decisions must have unique IDs and at most one decision per source finding."""

    def test_duplicate_decision_ids_fail(self):
        decision = {
            "id": "d1",
            "source_finding_id": "F1",
            "applicability": "USE",
            "reason": "x",
            "evidence_refs": ["source"],
            "affected_step_ids": [],
            "revision": 2,
            "recorded_at": "2026-10-30T03:00:00Z",
        }
        self.p["claim_decisions"] = [decision, copy.deepcopy(decision)]
        errors = self.check()
        self.assertTrue(
            any("duplicate" in e.lower() and "decision" in e.lower() for e in errors),
            f"expected duplicate-decision error; got: {errors}",
        )

    def test_two_decisions_same_finding_fail(self):
        self.p["claim_decisions"] = [
            {
                "id": "d1",
                "source_finding_id": "F1",
                "applicability": "USE",
                "reason": "x",
                "evidence_refs": ["source"],
                "affected_step_ids": [],
                "revision": 2,
                "recorded_at": "2026-10-30T03:00:00Z",
            },
            {
                "id": "d2",
                "source_finding_id": "F1",
                "applicability": "DO_NOT_USE",
                "reason": "x",
                "evidence_refs": ["source"],
                "affected_step_ids": [],
                "revision": 2,
                "recorded_at": "2026-10-30T03:00:00Z",
            },
        ]
        errors = self.check()
        self.assertTrue(
            any(
                "decision" in e.lower()
                and ("one per finding" in e.lower() or "duplicate finding" in e.lower())
                for e in errors
            ),
            f"expected 'one per finding' error; got: {errors}",
        )


if __name__ == "__main__":
    unittest.main()
