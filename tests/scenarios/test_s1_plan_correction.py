"""Scenario S1 — Normal execution with Plan correction.

End-to-end acceptance:

* Research r1 produces a Plan r1 that CARRIES an open critical gap finding
  (scanner-detected drift that is in-scope and material). Build admission
  must refuse to proceed on an open critical gap; classification BLOCKED
  (negative control).
* A corrective bundle creates Plan r2 with the gap finding resolved and
  marked `recheck_receipt_ref`; cross-record validation passes; the real
  build artifact runs; completion is persisted.
* Negative control: Build cannot proceed on Plan r1 (open critical gap);
  only the pinned revision-2 Plan admits the Build.

Independently authored oracle:

* Plan r1: validate_pipeline must surface
    'unresolved critical gaps:' (from GapAnalysis invariant), classification
    BLOCKED (Pydantic rejects the Plan before cross-record).
* Plan r2: classification VERIFIED, zero cross-record errors.
* Build runner output: 'characters: 4', 'bytes: 7', 'words: 2' for the
  same canonical input as S2.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

from tests.scenarios._runner import run_scenario  # noqa: E402


def _base_bundle_r1() -> dict:
    counter = _REPO_ROOT / "bin" / "context_counter.py"
    return {
        "objective": "Scenario S1 — Plan correction (r1 open critical, r2 resolved)",
        "requirements": [
            {
                "id": "R1",
                "statement": "Count characters correctly",
                "scope": "in_scope",
                "authority_ref": "AGENTS.md",
            },
        ],
        "findings": [
            {
                "id": "F1",
                "claim": "bin/context_counter.py counts characters",
                "evidence_refs": ["bin/context_counter.py"],
                "assessment": "supported",
                "limitations": "",
            },
        ],
        "requirement_trace": [
            {
                "requirement_id": "R1",
                "finding_ids": ["F1"],
                "fixture_ids": ["bin/context_counter.py"],
                "criterion_ids": ["agent/contracts/build.yaml"],
                "disposition": "covered",
            },
        ],
        "accepted_requirement_ids": ["R1"],
        "plan_milestones": [
            {
                "id": "m1",
                "goal": "Count characters via the counter",
                "files": ["bin/context_counter.py"],
                "steps": ["invoke", "verify"],
                "commands": [f"python {counter}"],
                "expected_observations": ["characters: 4"],
                "status": "pending",
            },
        ],
        "acceptance_criteria": [
            {
                "id": "c1",
                "requirement_id": "R1",
                "expected_result": "character count matches",
                "oracle_ref": "bin/context_counter.py",
            },
        ],
        "claim_decisions": [
            {
                "id": "d1",
                "source_finding_id": "F1",
                "applicability": "USE",
                "reason": "Direct source inspection of bin/context_counter.py.",
                "evidence_refs": ["bin/context_counter.py"],
                "affected_step_ids": ["m1"],
                "revision": 1,
                "recorded_at": "2026-10-31T00:00:00Z",
            },
        ],
        "accepted_milestone_ids": ["m1"],
        "accepted_criterion_ids": ["c1"],
    }


class S1PlanCorrectionTest(unittest.TestCase):
    """Plan r1 has an open critical gap → Build blocked. Plan r2 resolves it → VERIFIED."""

    def test_r1_blocked_on_open_critical_gap(self):
        """Plan r1 has an open critical gap finding → cross-record validator
        surfaces 'unresolved critical gaps' and classification is PARTIAL
        (controller still produces records; validator blocks completion)."""
        counter = _REPO_ROOT / "bin" / "context_counter.py"
        bundle = _base_bundle_r1()
        bundle["gap_findings"] = [
            {
                "id": "g_missing_recovery",
                "type": "missing",
                "path": "docs/recovery_runbook.md",
                "finding": "runbook referenced by plan but absent from workspace",
                "status": "open",
                "severity": "critical",
                "evidence_ref": "g_missing_recovery",
                "fix_receipt_ref": None,
                "recheck_ref": None,
            },
        ]
        bundle["build_runner"] = {
            "argv": [sys.executable, str(counter), "A\U0001f600\nB"],
            "cwd": str(_REPO_ROOT),
            "timeout": 10,
        }
        bundle["oracle"] = {
            # Pydantic rejects a Plan with an unresolved critical gap at
            # review_research_plan time → classification = BLOCKED.
            "classification": "BLOCKED",
        }

        result = run_scenario("S1.r1", bundle)
        self.assertEqual(
            result.classification,
            "BLOCKED",
            msg=f"S1 r1 negative control failed:\n{result.summary()}",
        )
        joined = " || ".join(result.pydantic_errors)
        # Pydantic's GapAnalysis @model_validator fires first with
        # 'gap analysis must be resolved' when status != resolved.
        # When status is resolved but critical IDs remain, the message is
        # 'unresolved critical gaps: ...'. Either error is a valid r1 refusal.
        self.assertTrue(
            "gap analysis must be resolved" in joined or "unresolved critical gaps" in joined,
            f"expected gap-related pydantic error; got: {joined}",
        )

    def test_r2_resolved_passes(self):
        """Plan r2 resolves the gap with fix_receipt_ref and recheck_receipt_ref
        and bumps revision; cross-record passes; the real counter runs."""
        counter = _REPO_ROOT / "bin" / "context_counter.py"
        bundle = _base_bundle_r1()
        # Preserve lineage: the same claim decision, bumped to revision 2.
        bundle["claim_decisions"][0]["revision"] = 2
        bundle["gap_findings"] = [
            {
                "id": "g_missing_recovery",
                "type": "missing",
                "path": "docs/recovery_runbook.md",
                "finding": "runbook referenced by plan but absent from workspace",
                "status": "resolved",
                "severity": "critical",
                "evidence_ref": "g_missing_recovery",
                "fix_receipt_ref": "AGENTS.md",
                "recheck_receipt_ref": "AGENTS.md",
                "recheck_ref": "AGENTS.md",
            },
        ]
        bundle["gap_findings_mark_resolved"] = {
            "fix_receipt_ref": "AGENTS.md",
            "recheck_ref": "AGENTS.md",
        }
        bundle["build_runner"] = {
            "argv": [sys.executable, str(counter), "A\U0001f600\nB"],
            "cwd": str(_REPO_ROOT),
            "timeout": 10,
        }
        bundle["oracle"] = {
            "classification": "VERIFIED",
            "cross_record_errors_expected": [],
            "cross_record_errors_forbidden": [
                "unresolved critical gaps",
                "unsupported finding",
            ],
            "plan_decisions_applicability": {
                "USE": 1,
                "DO_NOT_USE": 0,
                "VALIDATE_FIRST": 0,
            },
            "build_accepted_milestones": ["m1"],
            "build_runner": {
                "expected_exit": 0,
                "stdout_contains": ["characters: 4", "bytes: 7", "words: 2"],
            },
        }

        result = run_scenario("S1.r2", bundle)
        self.assertTrue(
            result.passed,
            msg=f"S1 r2 corrective path failed:\n{result.summary()}",
        )
        self.assertEqual(result.classification, "VERIFIED")


if __name__ == "__main__":
    unittest.main()
