"""Actual V18 trace reader, with scope isolation and no invented E2E success."""
from __future__ import annotations

import unittest

from agent.adapters.trace_projection import TraceProjection

try:
    from systems.scan_trace import summarize
except ImportError:
    summarize = None


@unittest.skipUnless(summarize is not None, "Real V18 trace reader unavailable")
class TraceProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reader = TraceProjection(summarize)

    def test_completed_job_is_not_verified_execplan(self) -> None:
        events = [
            {"job_id": "j1", "kind": "source_inspected", "payload": {"coverage": "complete"}},
            {"job_id": "j1", "kind": "job_completed"},
        ]
        view = self.reader.project("j1", events, task_id="task", action_id="act")
        self.assertEqual(view.execution_outcome, "pass")
        self.assertEqual(view.inspection_coverage, "complete")
        self.assertTrue(view.scope_consistent)
        self.assertFalse(view.completion_verified)
        self.assertEqual((view.task_id, view.action_id), ("task", "act"))

    def test_blocked_and_incomplete_remain_distinct(self) -> None:
        blocked = self.reader.project("j2", [{"job_id": "j2", "kind": "job_blocked"}])
        missing = self.reader.project("j3", [])
        self.assertEqual(blocked.execution_outcome, "blocked")
        self.assertEqual(missing.execution_outcome, "incomplete")
        self.assertFalse(missing.scope_consistent)
        self.assertFalse(blocked.completion_verified)

    def test_mixed_job_events_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.reader.project("j", [{"job_id": "another", "kind": "job_completed"}])

    def test_unscoped_events_do_not_claim_scope_verification(self) -> None:
        events = [{"kind": "job_completed"}]
        view = self.reader.project("j", events)
        self.assertFalse(view.scope_consistent)
        owned = self.reader.project("j", events, scoped_by_owner=True)
        self.assertFalse(owned.scope_consistent)
        self.assertEqual(owned.scope_basis, "owner_asserted_unverified")
        self.assertFalse(owned.completion_verified)

    def test_wrong_job_artifact_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            self.reader.project("j", [{"job_id": "j", "kind": "job_completed"}], artifact={"job_id": "other"})

    def test_reader_inconsistent_count_rejected(self) -> None:
        class WrongTrace:
            execution_outcome = "pass"
            inspection_coverage = "complete"
            generation_mode = "deterministic"
            terminal_event = "job_completed"
            event_count = 99
        with self.assertRaises(ValueError):
            TraceProjection(lambda *_args, **_kw: WrongTrace()).project("j", [{"kind": "job_completed"}])


if __name__ == "__main__":
    unittest.main()
