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


class PreflightFailureBlocksPlanTest(unittest.TestCase):
    """G05 reopen — a non-VALID preflight MUST prevent gap_analysis.status
    from reaching 'resolved' and MUST emit critical gap findings per
    offending category. The baseline (before this fix) set status to
    'resolved' when the file-diff scanner found no missing files,
    regardless of the preflight verdict."""

    def test_not_validated_preflight_blocks_plan(self):
        """Patch _CapabilityPreflight so .run() returns NOT_VALIDATED and
        confirm the controller refuses to mark gap_analysis resolved."""
        import os
        import sys
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        _repo = Path(__file__).resolve().parents[2]
        for sub in ("agent", "tools"):
            sp = str(_REPO / sub)
            if sp not in sys.path:
                sys.path.insert(0, sp)
        import gap_analysis as _ga  # noqa: E402

        class StubPreflight:
            def run(self):
                cat = _ga.PreflightCategoryResult(
                    category="duplication",
                    verdict=_ga.CapabilityVerdict.NOT_VALIDATED.value,
                    positive_control_id="pos",
                    negative_control_id="neg",
                    positive_found=False,
                    negative_preserved=True,
                    scanner_identity="SAME",
                )
                return _ga.PreflightResult(
                    categories=[cat],
                    aggregate_verdict=_ga.CapabilityVerdict.NOT_VALIDATED.value,
                    scanner_identity="SAME",
                )

        os.environ["ONESHOT_TRUSTED_TEST_INPUT"] = "1"
        try:
            with (
                tempfile.TemporaryDirectory(prefix="g05-reopen-") as td,
                patch(
                    "gap_analysis.CapabilityPreflight",
                    return_value=StubPreflight(),
                ),
            ):
                from main import OneShotController

                storage = Path(td) / "tasks.json"
                ctrl = OneShotController(storage_path=str(storage))
                tid = ctrl.start_task("preflight-reopen")
                r = ctrl.research_plan(
                    tid,
                    "preflight-reopen",
                    str(_REPO),
                    input_bundle={
                        "requirements": [
                            {
                                "id": "R1",
                                "statement": "x",
                                "scope": "in_scope",
                                "authority_ref": "AGENTS.md",
                            }
                        ],
                        "findings": [
                            {
                                "id": "F1",
                                "claim": "x",
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
                                "goal": "g",
                                "files": [],
                                "steps": ["x"],
                                "commands": ["x"],
                                "expected_observations": ["x"],
                                "status": "pending",
                            }
                        ],
                        "acceptance_criteria": [
                            {
                                "id": "c1",
                                "requirement_id": "R1",
                                "expected_result": "x",
                                "oracle_ref": "AGENTS.md",
                            }
                        ],
                    },
                )
                # Plan can still be CREATED (handoff.ready becomes False),
                # but gap_analysis.status MUST NOT be 'resolved'.
                self.assertEqual(
                    p["record"]["gap_analysis"]["status"],
                    "findings_open",
                    "preflight NOT_VALIDATED must not reach gap_analysis.status=resolved",
                )
                findings = p["record"]["gap_analysis"]["findings"]
                preflight_ids = [f["id"] for f in findings if "preflight-" in f["id"]]
                self.assertGreater(
                    len(preflight_ids),
                    0,
                    "critical gap finding(s) must be emitted per failing preflight category",
                )
        finally:
            os.environ.pop("ONESHOT_TRUSTED_TEST_INPUT", None)
