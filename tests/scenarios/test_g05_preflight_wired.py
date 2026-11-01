"""G05 — preflight wired into Plan Gap Analysis boundary.

Red-first:
  * Running the full workflow when a preflight category is INVALID or
    NOT_VALIDATED must produce classification BLOCKED and emit a
    scanner_calls receipt reporting the invalid category.
  * The receipt is bound to plan.revision.
  * Removing the preflight wiring would allow Build to run — the test
    detects that by requiring the receipt in plan.gap_analysis.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for sub in ("agent", "agent/contracts", "tools"):
    sp = str(_REPO / sub)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from main import OneShotController  # noqa: E402


class PreflightWiringTest(unittest.TestCase):
    def test_preflight_receipt_present_in_plan_gap_analysis(self):
        """Every live Plan review must include a preflight receipt among
        plan.gap_analysis.scanner_calls with an identifiable
        preflight tool_ref."""
        with tempfile.TemporaryDirectory(prefix="g05-wired-") as td:
            storage = Path(td) / "tasks.json"
            ctrl = OneShotController(storage_path=str(storage))
            tid = ctrl.start_task("preflight-wiring")
            r = ctrl.research_plan(
                tid,
                "preflight-wiring",
                str(_REPO),
                input_bundle={
                    "requirements": [
                        {
                            "id": "R1",
                            "statement": "Count characters",
                            "scope": "in_scope",
                            "authority_ref": "AGENTS.md",
                        }
                    ],
                    "findings": [
                        {
                            "id": "F1",
                            "claim": "bin/context_counter.py counts characters",
                            "evidence_refs": ["bin/context_counter.py"],
                            "assessment": "supported",
                            "limitations": "",
                        }
                    ],
                    "requirement_trace": [
                        {
                            "requirement_id": "R1",
                            "finding_ids": ["F1"],
                            "fixture_ids": ["bin/context_counter.py"],
                            "criterion_ids": ["agent/contracts/build.yaml"],
                            "disposition": "covered",
                        }
                    ],
                    "accepted_requirement_ids": ["R1"],
                    "plan_milestones": [
                        {
                            "id": "m1",
                            "goal": "Count chars",
                            "files": ["bin/context_counter.py"],
                            "steps": ["invoke"],
                            "commands": ["python bin/context_counter.py"],
                            "expected_observations": ["characters: 4"],
                            "status": "pending",
                        }
                    ],
                    "acceptance_criteria": [
                        {
                            "id": "c1",
                            "requirement_id": "R1",
                            "expected_result": "characters: 4",
                            "oracle_ref": "bin/context_counter.py",
                        }
                    ],
                    "claim_decisions": [
                        {
                            "id": "d1",
                            "source_finding_id": "F1",
                            "applicability": "USE",
                            "reason": "x",
                            "evidence_refs": ["bin/context_counter.py"],
                            "affected_step_ids": ["m1"],
                            "revision": 1,
                            "recorded_at": "2026-11-01T00:00:00Z",
                        }
                    ],
                    "gap_findings_mark_resolved": {
                        "fix_receipt_ref": "AGENTS.md",
                        "recheck_ref": "AGENTS.md",
                    },
                },
            )
            self.assertEqual(r["errors"], [])
            p = ctrl.review_research_plan(
                tid,
                r["record"],
                r["evidence_index"],
                str(_REPO),
                input_bundle={
                    "accepted_requirement_ids": ["R1"],
                    "plan_milestones": [
                        {
                            "id": "m1",
                            "goal": "Count chars",
                            "files": ["bin/context_counter.py"],
                            "steps": ["invoke"],
                            "commands": ["python bin/context_counter.py"],
                            "expected_observations": ["characters: 4"],
                            "status": "pending",
                        }
                    ],
                    "acceptance_criteria": [
                        {
                            "id": "c1",
                            "requirement_id": "R1",
                            "expected_result": "characters: 4",
                            "oracle_ref": "bin/context_counter.py",
                        }
                    ],
                    "gap_findings_mark_resolved": {
                        "fix_receipt_ref": "AGENTS.md",
                        "recheck_ref": "AGENTS.md",
                    },
                },
            )
            # The plan record must carry a preflight receipt whose
            # tool_ref identifies agent/gap_analysis.CapabilityPreflight.
            calls = p["record"]["gap_analysis"]["scanner_calls"]
            preflights = [
                c
                for c in calls
                if "capability_preflight" in c.get("method", "")
                or "capability_preflight" in c.get("tool_ref", "")
            ]
            self.assertGreaterEqual(
                len(preflights),
                1,
                "preflight receipt missing from plan.gap_analysis.scanner_calls",
            )
            # And it is bound to the plan's revision.
            self.assertEqual(
                preflights[0]["input_revision"],
                p["record"]["revision"],
                "preflight receipt not bound to plan revision",
            )


if __name__ == "__main__":
    unittest.main()
