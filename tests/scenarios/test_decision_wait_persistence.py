"""Audit item 01.6: pending user decisions must survive a controller restart.

Before: _decision_waits was an in-memory dict. A fresh OneShotController could
not see or answer a wait raised in a prior process.

After: UserDecisionWait is persisted on TaskRecord.metadata['decision_waits'];
has_pending_decision() and provide_user_decision() hydrate from TaskManager
so a restarted controller can observe and resolve the wait.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from main import OneShotController  # type: ignore[import-not-found]


class DecisionWaitPersistenceTest(unittest.TestCase):
    def test_pending_decision_visible_after_restart(self):
        with tempfile.TemporaryDirectory(prefix="oneshot-dw-") as td:
            storage = Path(td) / "tasks.json"
            ctrl = OneShotController(storage_path=str(storage))
            tid = ctrl.start_task("decision-persistence")
            rid = ctrl.request_user_decision(
                tid, "Pick an option?", permissible_answers=["yes", "no"]
            )

            # Fresh controller — simulates restart.
            ctrl2 = OneShotController(storage_path=str(storage))
            w = ctrl2.has_pending_decision(tid)
            self.assertIsNotNone(w, "pending decision not visible after restart")
            self.assertEqual(w.input_request_id, rid)
            self.assertEqual(w.question, "Pick an option?")
            self.assertEqual(w.permissible_answers, ["yes", "no"])
            self.assertFalse(w.answered)

            # Answer via the fresh controller.
            self.assertTrue(ctrl2.provide_user_decision(tid, rid, "yes"))
            # Yet another restart — the answer must persist too.
            ctrl3 = OneShotController(storage_path=str(storage))
            self.assertIsNone(
                ctrl3.has_pending_decision(tid),
                "answered decision should no longer be pending",
            )

    def test_invalid_answer_rejected_after_restart(self):
        with tempfile.TemporaryDirectory(prefix="oneshot-dw2-") as td:
            storage = Path(td) / "tasks.json"
            ctrl = OneShotController(storage_path=str(storage))
            tid = ctrl.start_task("decision-persistence-reject")
            rid = ctrl.request_user_decision(tid, "A?", permissible_answers=["yes", "no"])
            ctrl2 = OneShotController(storage_path=str(storage))
            self.assertFalse(ctrl2.provide_user_decision(tid, rid, "maybe"))
            # Still pending because the invalid answer was refused.
            self.assertIsNotNone(ctrl2.has_pending_decision(tid))


if __name__ == "__main__":
    unittest.main()
