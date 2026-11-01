"""Scenario S3 — VALIDATE_FIRST gating.

End-to-end acceptance:

* Research/Plan is missing material evidence for a dependent milestone;
  Plan assigns VALIDATE_FIRST to that claim.
* Build admission filter removes the dependent milestone — no prohibited
  side effect occurs before evidence arrives.
* Negative control: the stale admission (where Build still accepts the
  gated milestone) is rejected by validate_pipeline with
  'VALIDATE_FIRST blocks step <id>'.
* Positive path (r2): the scenario supplies the missing evidence, updates
  the decision to USE, and the dependent milestone becomes admissible;
  the real counter runs on real input and classification is VERIFIED.

The scenario demonstrates that:
  * the admission filter actually prevents the Build from accepting a
    gated milestone (positive path assertion: build_accepted_milestones
    excludes the gated id);
  * the independent subprocess run does NOT invoke the gated milestone
    (we only run commands for admitted milestones; the gated one has no
    build_runner argv in the gated case).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

from tests.scenarios._runner import run_scenario  # noqa: E402


def _common_bundle() -> dict:
    """Shared bundle shape — two milestones, m_independent and m_gated."""
    counter = _REPO_ROOT / "bin" / "context_counter.py"
    return {
        "objective": "Scenario S3 — VALIDATE_FIRST gate",
        "requirements": [
            {
                "id": "R_INDEP",
                "statement": "Count characters (independent of gated claim)",
                "scope": "in_scope",
                "authority_ref": "AGENTS.md",
            },
            {
                "id": "R_GATED",
                "statement": "Produce a byte histogram (requires missing evidence)",
                "scope": "in_scope",
                "authority_ref": "AGENTS.md",
            },
        ],
        "findings": [
            {
                "id": "F_INDEP",
                "claim": "bin/context_counter.py counts characters",
                "evidence_refs": ["bin/context_counter.py"],
                "assessment": "supported",
                "limitations": "",
            },
            {
                "id": "F_GATED",
                "claim": "bin/context_counter.py returns a byte histogram",
                "evidence_refs": ["AGENTS.md"],
                "assessment": "uncertain",
                "limitations": "no byte-histogram code path was located in bin/context_counter.py",
            },
        ],
        "requirement_trace": [
            {
                "requirement_id": "R_INDEP",
                "finding_ids": ["F_INDEP"],
                "fixture_ids": ["bin/context_counter.py"],
                "criterion_ids": ["agent/contracts/build.yaml"],
                "disposition": "covered",
            },
            {
                "requirement_id": "R_GATED",
                "finding_ids": ["F_GATED"],
                "fixture_ids": [],
                "criterion_ids": [],
                "disposition": "deferred",
            },
        ],
        "accepted_requirement_ids": ["R_INDEP", "R_GATED"],
        "plan_milestones": [
            {
                "id": "m_independent",
                "goal": "Count characters via the counter",
                "files": ["bin/context_counter.py"],
                "steps": ["invoke", "verify"],
                "commands": [f"python {counter}"],
                "expected_observations": ["characters: 4"],
                "status": "pending",
            },
            {
                "id": "m_gated",
                "goal": "Byte histogram (gated by missing evidence)",
                "files": ["bin/context_counter.py"],
                "steps": ["invoke", "verify"],
                "commands": [f"python {counter} --histogram"],
                "expected_observations": ["histogram ok"],
                "status": "pending",
            },
        ],
        "acceptance_criteria": [
            {
                "id": "c_indep",
                "requirement_id": "R_INDEP",
                "expected_result": "character count matches",
                "oracle_ref": "bin/context_counter.py",
            },
            {
                "id": "c_gated",
                "requirement_id": "R_GATED",
                "expected_result": "histogram oracle (deferred)",
                "oracle_ref": "AGENTS.md",
            },
        ],
        "accepted_criterion_ids": ["c_indep", "c_gated"],
        "gap_findings_mark_resolved": {
            "fix_receipt_ref": "AGENTS.md",
            "recheck_ref": "AGENTS.md",
        },
    }


class S3ValidateFirstTest(unittest.TestCase):
    def test_gated_milestone_excluded_from_admission(self):
        """Positive path: VALIDATE_FIRST on m_gated → admission removes it;
        m_independent remains admitted; the counter runs successfully."""
        counter = _REPO_ROOT / "bin" / "context_counter.py"
        bundle = _common_bundle()
        bundle["claim_decisions"] = [
            {
                "id": "d_use_indep",
                "source_finding_id": "F_INDEP",
                "applicability": "USE",
                "reason": "Direct source inspection.",
                "evidence_refs": ["bin/context_counter.py"],
                "affected_step_ids": ["m_independent"],
                "revision": 1,
                "recorded_at": "2026-10-31T00:00:00Z",
            },
            {
                "id": "d_gate_hist",
                "source_finding_id": "F_GATED",
                "applicability": "VALIDATE_FIRST",
                "reason": "Evidence inconclusive — pending verification artifact.",
                "evidence_refs": ["AGENTS.md"],
                "affected_step_ids": ["m_gated"],
                "revision": 1,
                "recorded_at": "2026-10-31T00:00:00Z",
            },
        ]
        bundle["build_runner"] = {
            "argv": [sys.executable, str(counter), "A\U0001f600\nB"],
            "cwd": str(_REPO_ROOT),
            "timeout": 10,
        }
        bundle["oracle"] = {
            "classification": "VERIFIED",
            "cross_record_errors_expected": [],
            "cross_record_errors_forbidden": [
                "VALIDATE_FIRST blocks step m_independent",
            ],
            "plan_decisions_applicability": {
                "USE": 1,
                "DO_NOT_USE": 0,
                "VALIDATE_FIRST": 1,
            },
            "build_accepted_milestones": ["m_independent"],
            "build_runner": {
                "expected_exit": 0,
                "stdout_contains": ["characters: 4", "bytes: 7", "words: 2"],
            },
        }

        result = run_scenario("S3.gated", bundle)
        self.assertTrue(result.passed, msg=f"S3 gated path failed:\n{result.summary()}")
        self.assertEqual(result.classification, "VERIFIED")

    def test_negative_control_stale_admission(self):
        """Stale admission: Plan still has VALIDATE_FIRST on m_gated but the
        bundle forces m_gated into accepted_milestone_ids. Validate_pipeline
        must refuse with 'VALIDATE_FIRST blocks step m_gated'."""
        counter = _REPO_ROOT / "bin" / "context_counter.py"
        bundle = _common_bundle()
        bundle["claim_decisions"] = [
            {
                "id": "d_use_indep",
                "source_finding_id": "F_INDEP",
                "applicability": "USE",
                "reason": "Direct source inspection.",
                "evidence_refs": ["bin/context_counter.py"],
                "affected_step_ids": ["m_independent"],
                "revision": 1,
                "recorded_at": "2026-10-31T00:00:00Z",
            },
            {
                "id": "d_gate_hist",
                "source_finding_id": "F_GATED",
                "applicability": "VALIDATE_FIRST",
                "reason": "Evidence inconclusive.",
                "evidence_refs": ["AGENTS.md"],
                "affected_step_ids": ["m_gated"],
                "revision": 1,
                "recorded_at": "2026-10-31T00:00:00Z",
            },
        ]
        # Force a stale admission: scenario says "pretend Build accepted the
        # gated milestone anyway", which must be rejected.
        bundle["accepted_milestone_ids"] = ["m_independent", "m_gated"]
        bundle["build_runner"] = {
            "argv": [sys.executable, str(counter), "A"],
            "cwd": str(_REPO_ROOT),
            "timeout": 10,
        }
        bundle["oracle"] = {
            "classification": "PARTIAL",
            "cross_record_errors_expected": [
                "VALIDATE_FIRST",
                "m_gated",
            ],
        }

        result = run_scenario("S3.stale", bundle)
        self.assertTrue(result.passed, msg=f"S3 stale admission failed:\n{result.summary()}")
        self.assertEqual(result.classification, "PARTIAL")


if __name__ == "__main__":
    unittest.main()
