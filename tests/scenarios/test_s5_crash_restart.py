"""Scenario S5 — Process interruption with SQLite effect observer.

The scenario executes a durable effectful action through a REAL subprocess
(bin/sqlite_effect_runner.py), terminated at deterministic checkpoints,
restarted, and reconciled against an INDEPENDENT SQLite observer the test
also opens directly to verify at-most-once application.

Three crash windows are exercised:

  1. CHECKPOINT_KILL_AT=pre_effect
     — intent persisted, effect NOT applied. Restart with
       CHECKPOINT_RECONCILE=1 must apply the effect exactly once.
  2. CHECKPOINT_KILL_AT=post_effect
     — intent persisted, effect applied, receipt NOT written.
       Restart must detect 'applied' state and NOT reapply.
  3. Normal baseline (no crash) — effect applied exactly once.

Each crash case is enveloped by:
  * a real OneShotController.run_workflow() invocation whose Plan declares
    the effectful milestone as the only accepted step;
  * Pydantic validation of the generated records at Build boundary;
  * independent SQLite SELECT confirming applied_count == 1.

The Build does NOT run the effect runner (we invoke it ourselves to
precisely control the kill moment); the Plan still carries the milestone
and the admission filter still runs — the record set remains valid.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

from tests.scenarios._runner import run_scenario  # noqa: E402


def _effect_runner_argv(db_path: Path, action_id: str, payload: str = "effect") -> list[str]:
    return [sys.executable, str(_REPO_ROOT / "bin" / "sqlite_effect_runner.py")]


def _spawn_effect_runner(
    db_path: Path,
    action_id: str,
    *,
    kill_at: str | None = None,
    reconcile: bool = False,
    payload: str = "effect",
) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["SQLITE_OBSERVER_DB"] = str(db_path)
    env["ACTION_ID"] = action_id
    env["ACTION_PAYLOAD"] = payload
    if kill_at:
        env["CHECKPOINT_KILL_AT"] = kill_at
    if reconcile:
        env["CHECKPOINT_RECONCILE"] = "1"
    return subprocess.run(
        _effect_runner_argv(db_path, action_id),
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _observer_state(db_path: Path, action_id: str) -> tuple[str, int]:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT state, applied_count FROM actions WHERE action_id=?",
            (action_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return ("none", 0)
    return (row[0], row[1])


def _workflow_bundle(action_id: str, db_path: Path) -> dict:
    """A valid-triple bundle whose Build milestone is 'the effectful action'."""
    return {
        "objective": f"Scenario S5 — crash+restart for action {action_id}",
        "requirements": [
            {
                "id": "R_EFFECT",
                "statement": "Apply the external effect at-most-once.",
                "scope": "in_scope",
                "authority_ref": "AGENTS.md",
            },
        ],
        "findings": [
            {
                "id": "F_EFFECT",
                "claim": "bin/sqlite_effect_runner.py applies one effect per action_id",
                "evidence_refs": ["bin/sqlite_effect_runner.py"],
                "assessment": "supported",
                "limitations": "",
            },
        ],
        "requirement_trace": [
            {
                "requirement_id": "R_EFFECT",
                "finding_ids": ["F_EFFECT"],
                "fixture_ids": ["bin/sqlite_effect_runner.py"],
                "criterion_ids": ["agent/contracts/build.yaml"],
                "disposition": "covered",
            },
        ],
        "accepted_requirement_ids": ["R_EFFECT"],
        "plan_milestones": [
            {
                "id": "m_effect",
                "goal": "Apply external effect at-most-once",
                "files": ["bin/sqlite_effect_runner.py"],
                "steps": ["persist intent", "apply effect", "write receipt"],
                "commands": [f"python bin/sqlite_effect_runner.py (db={db_path})"],
                "expected_observations": ["applied_count=1"],
                "status": "pending",
            },
        ],
        "acceptance_criteria": [
            {
                "id": "c_effect",
                "requirement_id": "R_EFFECT",
                "expected_result": "applied_count=1",
                "oracle_ref": "bin/sqlite_effect_runner.py",
            },
        ],
        "claim_decisions": [
            {
                "id": "d_effect",
                "source_finding_id": "F_EFFECT",
                "applicability": "USE",
                "reason": "Direct source inspection of bin/sqlite_effect_runner.py.",
                "evidence_refs": ["bin/sqlite_effect_runner.py"],
                "affected_step_ids": ["m_effect"],
                "revision": 1,
                "recorded_at": "2026-10-31T00:00:00Z",
            },
        ],
        "gap_findings_mark_resolved": {
            "fix_receipt_ref": "AGENTS.md",
            "recheck_ref": "AGENTS.md",
        },
        "oracle": {
            "classification": "VERIFIED",
            "cross_record_errors_expected": [],
            "plan_decisions_applicability": {
                "USE": 1,
                "DO_NOT_USE": 0,
                "VALIDATE_FIRST": 0,
            },
            "build_accepted_milestones": ["m_effect"],
        },
    }


class S5CrashRestartTest(unittest.TestCase):
    def _run_workflow(self, action_id: str, db_path: Path) -> None:
        """Run the real OneShotController workflow and assert VERIFIED."""
        bundle = _workflow_bundle(action_id, db_path)
        result = run_scenario(f"S5.workflow.{action_id}", bundle)
        self.assertTrue(
            result.passed,
            msg=f"S5 workflow for {action_id} failed:\n{result.summary()}",
        )
        self.assertEqual(result.classification, "VERIFIED")

    def test_normal_baseline_applies_exactly_once(self):
        with tempfile.TemporaryDirectory(prefix="s5-base-") as td:
            db = Path(td) / "observer.sqlite3"
            aid = f"aid-base-{uuid.uuid4().hex[:8]}"
            self._run_workflow(aid, db)
            r = _spawn_effect_runner(db, aid)
            self.assertEqual(r.returncode, 0, r.stderr)
            state, count = _observer_state(db, aid)
            self.assertEqual(state, "reconciled")
            self.assertEqual(count, 1)

    def test_pre_effect_crash_recovers_to_apply_once(self):
        with tempfile.TemporaryDirectory(prefix="s5-pre-") as td:
            db = Path(td) / "observer.sqlite3"
            aid = f"aid-pre-{uuid.uuid4().hex[:8]}"
            self._run_workflow(aid, db)

            r1 = _spawn_effect_runner(db, aid, kill_at="pre_effect")
            # Crash exit code: 137 (SIGKILL-equivalent via os._exit(137))
            # — the parent should see this precise code.
            self.assertEqual(r1.returncode, 137, r1.stderr)
            state, count = _observer_state(db, aid)
            self.assertEqual(state, "pending")
            self.assertEqual(count, 0)

            # Restart & reconcile.
            r2 = _spawn_effect_runner(db, aid, reconcile=True)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            state, count = _observer_state(db, aid)
            self.assertEqual(state, "reconciled")
            self.assertEqual(count, 1)

    def test_post_effect_crash_never_duplicates(self):
        with tempfile.TemporaryDirectory(prefix="s5-post-") as td:
            db = Path(td) / "observer.sqlite3"
            aid = f"aid-post-{uuid.uuid4().hex[:8]}"
            self._run_workflow(aid, db)

            r1 = _spawn_effect_runner(db, aid, kill_at="post_effect")
            self.assertEqual(r1.returncode, 137, r1.stderr)
            state, count = _observer_state(db, aid)
            self.assertEqual(state, "applied")
            self.assertEqual(count, 1)

            # Reconcile must NOT reapply.
            r2 = _spawn_effect_runner(db, aid, reconcile=True)
            self.assertEqual(r2.returncode, 0, r2.stderr)
            state, count = _observer_state(db, aid)
            self.assertEqual(state, "reconciled")
            self.assertEqual(count, 1)  # EXACTLY one application

    def test_blind_retry_after_post_effect_crash_still_at_most_once(self):
        """Negative control for forced blind retry: if the caller tries to
        rerun the effect WITHOUT reconcile, the atomic UPDATE in
        _apply_effect refuses because state is 'applied' (not 'pending').
        applied_count must remain 1."""
        with tempfile.TemporaryDirectory(prefix="s5-blind-") as td:
            db = Path(td) / "observer.sqlite3"
            aid = f"aid-blind-{uuid.uuid4().hex[:8]}"
            self._run_workflow(aid, db)

            # First run → crash after effect, state=applied.
            r1 = _spawn_effect_runner(db, aid, kill_at="post_effect")
            self.assertEqual(r1.returncode, 137)
            self.assertEqual(_observer_state(db, aid), ("applied", 1))

            # Caller forces a blind retry (no reconcile flag). The runner's
            # intent insertion is INSERT OR IGNORE, and the apply UPDATE
            # requires state='pending'. So neither applies again.
            r2 = _spawn_effect_runner(db, aid)
            # The runner proceeds through the normal path, which calls
            # _apply_effect on an 'applied' row — the function returns
            # (idempotent) rather than reapplying, then writes receipt.
            self.assertEqual(r2.returncode, 0, r2.stderr)
            state, count = _observer_state(db, aid)
            self.assertEqual(state, "reconciled")
            self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
