"""G08 — input_bundle trusted-test-input fields are gated by env flag.

Production invocations (no env flag) must silently DROP the trusted
fields (`gap_findings`, `gap_findings_mark_resolved`,
`accepted_milestone_ids`, `accepted_criterion_ids`) rather than let
callers short-circuit Plan admission from a bundle.

Test harness invocations (env `ONESHOT_TRUSTED_TEST_INPUT=1`) are
allowed to pass those fields.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for sub in ("agent", "tools"):
    sp = str(_REPO / sub)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from main import OneShotController, _sanitise_input_bundle  # noqa: E402


class ProductionGateTest(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop("ONESHOT_TRUSTED_TEST_INPUT", None)

    def tearDown(self):
        if self._saved is not None:
            os.environ["ONESHOT_TRUSTED_TEST_INPUT"] = self._saved
        else:
            os.environ.pop("ONESHOT_TRUSTED_TEST_INPUT", None)

    def test_production_mode_drops_trusted_fields(self):
        bundle = {
            "objective": "x",
            "gap_findings_mark_resolved": {"fix_receipt_ref": "AGENTS.md"},
            "gap_findings": [{"id": "g1", "status": "open"}],
            "accepted_milestone_ids": ["m1"],
            "accepted_criterion_ids": ["c1"],
            # non-trusted field survives
            "requirements": [],
        }
        clean, dropped = _sanitise_input_bundle(bundle)
        self.assertIn("gap_findings_mark_resolved", dropped)
        self.assertIn("gap_findings", dropped)
        self.assertIn("accepted_milestone_ids", dropped)
        self.assertIn("accepted_criterion_ids", dropped)
        self.assertNotIn("gap_findings_mark_resolved", clean)
        self.assertIn("requirements", clean)

    def test_production_controller_records_dropped_fields(self):
        with tempfile.TemporaryDirectory(prefix="g08-prod-") as td:
            storage = Path(td) / "tasks.json"
            ctrl = OneShotController(storage_path=str(storage))
            tid = ctrl.start_task("g08")
            # No env flag — the bundle below carries trusted fields
            # that must be dropped.
            r = ctrl.research_plan(
                tid,
                "g08",
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
                    "gap_findings_mark_resolved": {
                        "fix_receipt_ref": "AGENTS.md",
                        "recheck_ref": "AGENTS.md",
                    },
                },
            )
            # research_plan recorded the drop.
            self.assertEqual(r["errors"], [])
            self.assertIn("gap_findings_mark_resolved", ctrl._last_dropped_bundle_fields)


class TrustedTestInputGateTest(unittest.TestCase):
    def setUp(self):
        os.environ["ONESHOT_TRUSTED_TEST_INPUT"] = "1"

    def tearDown(self):
        os.environ.pop("ONESHOT_TRUSTED_TEST_INPUT", None)

    def test_trusted_mode_keeps_fields(self):
        bundle = {
            "gap_findings_mark_resolved": {"fix_receipt_ref": "AGENTS.md"},
        }
        clean, dropped = _sanitise_input_bundle(bundle)
        self.assertEqual(dropped, [])
        self.assertEqual(clean, bundle)


if __name__ == "__main__":
    unittest.main()
