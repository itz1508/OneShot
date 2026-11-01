"""G09 same-task CLI drive for S5 (effectful workflow lineage).

S5 proves at-most-once effect application via a side SQLite observer
(bin/sqlite_effect_runner.py). The scenario-runner version launches
the runner as a subprocess independent of the workflow. For the
CLI-driven lineage drive, we focus on the workflow-record half of
S5 — a BAD attempt that leaves the effect intent 'pending', followed
by a GOOD continuation that completes the workflow against the
corrected plan. Both attempts land on one task_id with monotonic
Plan revisions.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "tools"))


def _bundle_s5(action_id: str, db_path: Path, correct: bool) -> dict:
    """BAD bundle wires the effectful milestone with a wrong expected
    observation; GOOD bundle aligns it with reality."""
    bundle = {
        "objective": "G09 S5 same-task CLI drive",
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
                "commands": [
                    f"python bin/sqlite_effect_runner.py "
                    f"(db={db_path}, action={action_id})"
                ],
                "expected_observations": [
                    "applied_count=1" if correct else "applied_count=99"
                ],
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
                "recorded_at": "2026-11-01T00:00:00Z",
            },
        ],
        "accepted_milestone_ids": ["m_effect"],
        "accepted_criterion_ids": ["c_effect"],
        "gap_findings_mark_resolved": {
            "fix_receipt_ref": "AGENTS.md",
            "recheck_ref": "AGENTS.md",
        },
    }
    return bundle


class G09S5SameTaskCLITest(unittest.TestCase):
    def test_s5_bad_then_continue_good_on_same_task(self):
        env = dict(os.environ)
        env["ONESHOT_TRUSTED_TEST_INPUT"] = "1"
        env["PYTHONPATH"] = f"{_REPO!s}:{env.get('PYTHONPATH', '')}"

        with tempfile.TemporaryDirectory(prefix="g09-s5-") as td:
            td_p = Path(td)
            storage = td_p / "tasks.json"
            db = td_p / "observer.sqlite3"
            action_id = f"aid-g09-{uuid.uuid4().hex[:8]}"
            request_file = td_p / "req.txt"
            request_file.write_text("G09 S5 same-task drive\n", encoding="utf-8")

            # BAD bundle.
            bad_path = td_p / "bad.json"
            bad_path.write_text(
                json.dumps(_bundle_s5(action_id, db, correct=False))
            )
            run_bad = subprocess.run(
                [
                    sys.executable, "-m", "agent.main", "run",
                    "--request-file", str(request_file),
                    "--storage", str(storage),
                    "--repo-root", str(_REPO),
                    "--bundle", str(bad_path),
                ],
                cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=120,
            )
            # Could be VERIFIED or PARTIAL depending on how controller
            # evaluates the expected_observation. What matters is the
            # task_id is set and the continuation lands on it.
            self.assertIn(run_bad.returncode, (0, 1), run_bad.stderr)
            bad_summary = json.loads(run_bad.stdout)
            tid = bad_summary["task_id"]
            self.assertIsNotNone(tid)

            # GOOD bundle.
            good_path = td_p / "good.json"
            good_path.write_text(
                json.dumps(_bundle_s5(action_id, db, correct=True))
            )
            run_good = subprocess.run(
                [
                    sys.executable, "-m", "agent.main", "continue",
                    "--task-id", tid,
                    "--request-file", str(request_file),
                    "--storage", str(storage),
                    "--repo-root", str(_REPO),
                    "--bundle", str(good_path),
                ],
                cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(run_good.returncode, 0, run_good.stderr)
            good_summary = json.loads(run_good.stdout)
            self.assertEqual(good_summary["classification"], "VERIFIED")
            self.assertEqual(good_summary["task_id"], tid)

            # Fresh-process lineage.
            from task_management import TaskManager  # noqa: E402

            tm = TaskManager(storage_path=str(storage))
            rec = tm.get_task(tid)
            self.assertIsNotNone(rec)
            records = (rec.results or {}).get("workflow_records") or []
            self.assertEqual(len(records), 2)
            r1 = int(records[0]["plan"]["revision"])
            r2 = int(records[1]["plan"]["revision"])
            self.assertEqual(r2, r1 + 1)
            self.assertEqual(records[1]["plan"].get("preceding_revision"), r1)
            self.assertEqual(records[1]["classification"], "VERIFIED")


if __name__ == "__main__":
    unittest.main()
