"""G06 — bounded retry refuses no-change (same-identity) attempts.

If `CapabilityPreflight` is INVALID and the caller invokes
`run_capability_preflight_with_correction` again without changing the
detector source, the second attempt must stop with
`blocked_resumable=True` and a `no_material_correction` blocker.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_REPO = Path(__file__).resolve().parents[2]
for sub in ("agent", "tools"):
    sp = str(_REPO / sub)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from main import OneShotController  # noqa: E402


class StubPreflight:
    """Fake preflight that always returns INVALID with the same
    scanner_identity, mimicking a stalled retry loop."""

    def run(self):
        from gap_analysis import CapabilityVerdict, PreflightCategoryResult, PreflightResult

        cat = PreflightCategoryResult(
            category="duplication",
            verdict=CapabilityVerdict.INVALID.value,
            positive_control_id="pos",
            negative_control_id="neg",
            positive_found=False,
            negative_preserved=True,
            scanner_identity="SAME_IDENTITY",
        )
        return PreflightResult(
            categories=[cat],
            aggregate_verdict=CapabilityVerdict.INVALID.value,
            scanner_identity="SAME_IDENTITY",
        )


class RetryIdentityTest(unittest.TestCase):
    def test_no_change_retry_blocks_resumable(self):
        with tempfile.TemporaryDirectory(prefix="g06-identity-") as td:
            storage = Path(td) / "tasks.json"
            ctrl = OneShotController(storage_path=str(storage))
            tid = ctrl.start_task("g06")

            # Patch the CapabilityPreflight class the controller uses
            # so every call returns the same INVALID identity.
            with patch("main._CapabilityPreflight", StubPreflight):
                receipt = ctrl.run_capability_preflight_with_correction(tid, max_repair_attempts=3)

            self.assertEqual(len(receipt["attempts"]), 2)
            self.assertTrue(receipt.get("blocked_resumable"))
            self.assertIn("no_material_correction", receipt.get("blocker", ""))
            # Attempt 1 and 2 share the same scanner_identity.
            self.assertEqual(
                receipt["attempts"][0]["scanner_identity"],
                receipt["attempts"][1]["scanner_identity"],
            )


if __name__ == "__main__":
    unittest.main()
