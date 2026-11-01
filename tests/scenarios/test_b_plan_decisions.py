"""Decision-contract tests for Plan applicability (USE / DO_NOT_USE / VALIDATE_FIRST).

Uses composition (``make_valid_triple``) instead of subclassing the baseline
``ContractTest`` so inherited baseline tests are not double-collected.

These tests exercise ``agent/contracts/models.validate_pipeline`` on dicts
only — they are PydanticValidation receipts, NOT end-to-end execution evidence.
The real S1-S5 scenario tests live under ``tests/scenarios/test_s*.py`` and
execute OneShot through its real entrypoint.
"""

from __future__ import annotations

import copy
import unittest

import models as module  # type: ignore[import-not-found]

from ._fixtures import make_valid_triple


class _TripleCase(unittest.TestCase):
    """Shared setUp for decision contract tests — no inherited tests."""

    def setUp(self) -> None:
        self.r, self.p, self.b, self.refs = make_valid_triple()

    def check(self) -> list[str]:
        return module.validate_records(self.r, self.p, self.b, self.refs.__contains__)


class ClaimDecisionShapeTest(_TripleCase):
    def test_valid_use_decision_passes(self):
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
        self.p["claim_decisions"] = [
            {
                "id": "d1",
                "source_finding_id": "F1",
                "applicability": "MAYBE_USE",
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


class UnsupportedFindingDecisionGatingTest(_TripleCase):
    def test_unsupported_finding_with_do_not_use_decision_passes(self):
        self.r["search"]["findings"][0]["assessment"] = "uncertain"
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
        self.assertEqual(errors, [], f"expected clean validation; got: {errors}")

    def test_unsupported_finding_without_decision_still_fails(self):
        self.r["search"]["findings"][0]["assessment"] = "uncertain"
        errors = self.check()
        self.assertTrue(
            any("unsupported finding" in e for e in errors),
            f"expected 'unsupported finding' error without decision; got: {errors}",
        )

    def test_unsupported_finding_with_validate_first_passes(self):
        self.r["search"]["findings"][0]["assessment"] = "uncertain"
        # VALIDATE_FIRST means Build cannot have accepted the affected milestone
        # yet; S3 shape is "Build not resumed".
        self.b["plan_input"]["accepted_milestone_ids"] = []
        self.p["claim_decisions"] = [
            {
                "id": "d1",
                "source_finding_id": "F1",
                "applicability": "VALIDATE_FIRST",
                "reason": "evidence inconclusive; dependent step gated",
                "evidence_refs": ["source"],
                "affected_step_ids": ["m1"],
                "revision": 2,
                "recorded_at": "2026-10-30T03:00:00Z",
            }
        ]
        errors = self.check()
        self.assertEqual(errors, [], f"expected clean validation; got: {errors}")

    def test_unsupported_finding_decision_still_requires_evidence_refs(self):
        self.r["search"]["findings"][0]["assessment"] = "uncertain"
        self.r["search"]["findings"][0]["evidence_refs"] = []
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
            f"expected evidence-related error; got: {errors}",
        )


class BuildAdmissionProvenanceTest(_TripleCase):
    def test_do_not_use_blocks_dependent_build_step(self):
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
        errors = self.check()
        self.assertTrue(
            any("do_not_use" in e.lower() and "m1" in e.lower() for e in errors),
            f"expected DO_NOT_USE admission error referencing m1; got: {errors}",
        )


class ValidateFirstGatingTest(_TripleCase):
    def test_validate_first_blocks_dependent_build_step(self):
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
        errors = self.check()
        self.assertTrue(
            any("validate_first" in e.lower() and "m1" in e.lower() for e in errors),
            f"expected VALIDATE_FIRST gating error referencing m1; got: {errors}",
        )


class DuplicateDecisionsTest(_TripleCase):
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
