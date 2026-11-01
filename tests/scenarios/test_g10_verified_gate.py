"""G10 — VERIFIED is awarded only when all_pass AND cross_record is clean.

Baseline (before this fix) would set classification = VERIFIED based on
cross_record_errors alone, even if the Build artifact itself failed
(all_pass = False). This test confirms the new gate: a Build whose real
output does not match the counter.py expectations must not be VERIFIED.

We simulate the all_pass=False path by stubbing build_plan to return a
BuildRecord that validates clean but reports all_pass=False.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_REPO = Path(__file__).resolve().parents[2]
for sub in ("agent", "tools", "agent/contracts"):
    sp = str(_REPO / sub)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from main import OneShotController  # noqa: E402


class VerifiedGateTest(unittest.TestCase):
    def setUp(self):
        os.environ["ONESHOT_TRUSTED_TEST_INPUT"] = "1"

    def tearDown(self):
        os.environ.pop("ONESHOT_TRUSTED_TEST_INPUT", None)

    def test_all_pass_false_cannot_be_verified(self):
        """Stub build_plan to return all_pass=False with a clean record.
        Classification MUST be PARTIAL."""
        with tempfile.TemporaryDirectory(prefix="g10-") as td:
            storage = Path(td) / "tasks.json"
            ctrl = OneShotController(storage_path=str(storage))

            real_build_plan = OneShotController.build_plan

            def _stub_build_plan(self, *args, **kwargs):
                result = real_build_plan(self, *args, **kwargs)
                result["all_pass"] = False
                return result

            with patch.object(OneShotController, "build_plan", _stub_build_plan):
                result = ctrl.run_workflow(
                    "verified-gate",
                    str(_REPO),
                    storage_path=str(storage),
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

            # cross_record may be clean (schema is fine); but all_pass=False
            # must demote the classification.
            self.assertFalse(result.get("all_pass"))
            self.assertEqual(result.get("classification"), "PARTIAL")


if __name__ == "__main__":
    unittest.main()
