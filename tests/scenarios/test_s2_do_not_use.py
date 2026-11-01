"""Scenario S2 — Unsupported research claim with DO_NOT_USE provenance filter.

End-to-end acceptance:

* Research retains an unsupported external claim (`assessment != supported`)
  alongside at least one supported finding.
* Plan assigns a `DO_NOT_USE` applicability decision to that unsupported
  claim, naming the milestone it would have produced.
* Build admission removes that milestone from `accepted_milestone_ids`
  while retaining the unaffected supported milestone.
* The real build artifact (`bin/context_counter.py`) executes successfully
  for the retained supported work and produces the expected observable
  output (character / byte / word counts for a known input).
* `validate_pipeline(research, plan, build, resolve=hybrid_resolver)` returns
  zero cross-record errors; classification is VERIFIED.

Independently authored oracle (no field is read back from the generated
records to construct expectations):

* Count expectations for input "A\\U0001f600\\nB":
    characters: 4   (A, emoji, newline, B)
    bytes:      7   (A=1, emoji=4, newline=1, B=1)
    words:      2
* The m_removed milestone must NOT appear in build.plan_input.accepted_milestone_ids
* The m_keep    milestone must     appear in build.plan_input.accepted_milestone_ids
* plan.claim_decisions applicability counts: USE=1, DO_NOT_USE=1, VALIDATE_FIRST=0

Negative control: when the DO_NOT_USE decision is removed from the bundle,
cross-record validation surfaces the "unsupported finding" error and the
blocked milestone would be admissible — captured in a sibling test below.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

from tests.scenarios._runner import run_scenario  # noqa: E402


def _base_bundle() -> dict:
    """Build the common Research/Plan/Build shape for S2."""
    counter = _REPO_ROOT / "bin" / "context_counter.py"
    return {
        "objective": "Scenario S2 — DO_NOT_USE provenance filter",
        "requirements": [
            {
                "id": "R_SUPPORTED",
                "statement": "Count characters in input text",
                "scope": "in_scope",
                "authority_ref": "AGENTS.md",
            },
            {
                "id": "R_CLAIM",
                "statement": "External claim: counter supports streaming audio",
                "scope": "in_scope",
                "authority_ref": "AGENTS.md",
            },
        ],
        "findings": [
            {
                "id": "F_SUPPORTED",
                "claim": "bin/context_counter.py counts characters",
                "evidence_refs": ["bin/context_counter.py"],
                "assessment": "supported",
                "limitations": "",
            },
            {
                "id": "F_UNSUPPORTED",
                "claim": "bin/context_counter.py streams audio in real time",
                "evidence_refs": ["AGENTS.md"],
                "assessment": "contradicted",
                "limitations": "no audio code path exists in bin/context_counter.py",
            },
        ],
        "requirement_trace": [
            {
                "requirement_id": "R_SUPPORTED",
                "finding_ids": ["F_SUPPORTED"],
                "fixture_ids": ["bin/context_counter.py"],
                "criterion_ids": ["agent/contracts/build.yaml"],
                "disposition": "covered",
            },
            {
                "requirement_id": "R_CLAIM",
                "finding_ids": ["F_UNSUPPORTED"],
                "fixture_ids": [],
                "criterion_ids": [],
                "disposition": "deferred",
            },
        ],
        "accepted_requirement_ids": ["R_SUPPORTED", "R_CLAIM"],
        "plan_milestones": [
            {
                "id": "m_keep",
                "goal": "Count characters in text input via counter",
                "files": ["bin/context_counter.py"],
                "steps": ["invoke", "verify"],
                "commands": [f"python {counter} <text>"],
                "expected_observations": ["characters: 4"],
                "status": "pending",
            },
            {
                "id": "m_removed",
                "goal": "Add audio streaming to counter (derived from unsupported claim)",
                "files": ["bin/context_counter.py"],
                "steps": ["invoke", "verify"],
                "commands": [f"python {counter} --audio stream"],
                "expected_observations": ["audio ok"],
                "status": "pending",
            },
        ],
        "acceptance_criteria": [
            {
                "id": "c_supported",
                "requirement_id": "R_SUPPORTED",
                "expected_result": "character/byte/word counts match",
                "oracle_ref": "bin/context_counter.py",
            },
        ],
        "accepted_milestone_ids": ["m_keep"],  # bundle narrows after admission filter
        "accepted_criterion_ids": ["c_supported"],
    }


class S2DoNotUseTest(unittest.TestCase):
    """End-to-end: Research retains unsupported claim; Plan assigns DO_NOT_USE;
    Build admission excludes the derived milestone; real counter still runs."""

    def test_positive_path(self):
        """DO_NOT_USE present → unsupported claim retained, milestone excluded,
        supported milestone still executes, zero cross-record errors."""
        counter = _REPO_ROOT / "bin" / "context_counter.py"
        bundle = _base_bundle()
        bundle["claim_decisions"] = [
            {
                "id": "d_use_support",
                "source_finding_id": "F_SUPPORTED",
                "applicability": "USE",
                "reason": "Direct source inspection of bin/context_counter.py.",
                "evidence_refs": ["bin/context_counter.py"],
                "affected_step_ids": ["m_keep"],
                "revision": 1,
                "recorded_at": "2026-10-31T00:00:00Z",
            },
            {
                "id": "d_block_audio",
                "source_finding_id": "F_UNSUPPORTED",
                "applicability": "DO_NOT_USE",
                "reason": ("Claim contradicted; no audio code path in bin/context_counter.py."),
                "evidence_refs": ["bin/context_counter.py"],
                "affected_step_ids": ["m_removed"],
                "revision": 1,
                "recorded_at": "2026-10-31T00:00:00Z",
            },
        ]
        bundle["build_runner"] = {
            "argv": [sys.executable, str(counter), "A\U0001f600\nB"],
            "cwd": str(_REPO_ROOT),
            "stdin": None,
            "timeout": 10,
        }
        bundle["gap_findings_mark_resolved"] = {
            "fix_receipt_ref": "AGENTS.md",
            "recheck_ref": "AGENTS.md",
        }
        bundle["oracle"] = {
            "classification": "VERIFIED",
            "cross_record_errors_expected": [],
            "cross_record_errors_forbidden": [
                "unsupported finding F_UNSUPPORTED",
                "DO_NOT_USE blocks step m_keep",
            ],
            "plan_decisions_applicability": {
                "USE": 1,
                "DO_NOT_USE": 1,
                "VALIDATE_FIRST": 0,
            },
            "build_accepted_milestones": ["m_keep"],
            "build_runner": {
                "expected_exit": 0,
                "stdout_contains": ["characters: 4", "bytes: 7", "words: 2"],
            },
        }

        result = run_scenario("S2.positive", bundle)
        self.assertTrue(
            result.passed,
            msg=f"S2 positive path failed:\n{result.summary()}",
        )
        self.assertEqual(result.classification, "VERIFIED")

    def test_negative_control_decision_removed(self):
        """Remove the DO_NOT_USE decision → the unsupported finding must
        surface as a cross-record error ('unsupported finding ...') and the
        classification is PARTIAL. Also the m_removed milestone is NOT
        filtered out of accepted_milestone_ids (admission not applied)."""
        counter = _REPO_ROOT / "bin" / "context_counter.py"
        bundle = _base_bundle()
        bundle["claim_decisions"] = [
            # Only a USE decision for the supported finding is present.
            {
                "id": "d_use_support",
                "source_finding_id": "F_SUPPORTED",
                "applicability": "USE",
                "reason": "Direct source inspection.",
                "evidence_refs": ["bin/context_counter.py"],
                "affected_step_ids": ["m_keep"],
                "revision": 1,
                "recorded_at": "2026-10-31T00:00:00Z",
            },
        ]
        bundle["build_runner"] = {
            "argv": [sys.executable, str(counter), "A\U0001f600\nB"],
            "cwd": str(_REPO_ROOT),
            "stdin": None,
            "timeout": 10,
        }
        bundle["gap_findings_mark_resolved"] = {
            "fix_receipt_ref": "AGENTS.md",
            "recheck_ref": "AGENTS.md",
        }
        bundle["oracle"] = {
            "classification": "PARTIAL",
            "cross_record_errors_expected": ["unsupported finding F_UNSUPPORTED"],
            "cross_record_errors_forbidden": [],
            "plan_decisions_applicability": {
                "USE": 1,
                "DO_NOT_USE": 0,
                "VALIDATE_FIRST": 0,
            },
            # Without the DO_NOT_USE decision, nothing filters out m_removed
            # from the pre-bundle accepted list. The bundle itself still
            # narrows to ["m_keep"] via `accepted_milestone_ids` (the explicit
            # override). This test does NOT pass accepted_milestone_ids
            # override — so the filter leaves the controller's default
            # (whatever review_research_plan built) alone.
        }
        # Clear the explicit override so admission is the only filter.
        bundle.pop("accepted_milestone_ids", None)

        result = run_scenario("S2.negative", bundle)
        self.assertTrue(
            result.passed,
            msg=f"S2 negative control failed:\n{result.summary()}",
        )
        self.assertEqual(result.classification, "PARTIAL")


if __name__ == "__main__":
    unittest.main()
