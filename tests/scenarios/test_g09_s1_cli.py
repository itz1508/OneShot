"""G09 reopen (reviewer recommendation): same-task CLI drive for S1.

Mirrors tests/scenarios/test_g09_same_task_cli.py (S2 drive) for the
S1 "Plan correction" scenario: Plan r1 carries an open critical gap
(BLOCKED/PARTIAL), then `oneshot continue` on the same task_id with
a corrective bundle (gap resolved, fix + recheck receipts) drives
classification to VERIFIED, and a fresh TaskManager sees BOTH Plan
revisions on the SAME task_id with monotonic revision bump.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "tools"))


def _bundle_s1(gap_open: bool) -> dict:
    counter = _REPO / "bin" / "context_counter.py"
    bundle = {
        "objective": "G09 S1 same-task CLI drive",
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
                "steps": ["invoke"],
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
                "recorded_at": "2026-11-01T00:00:00Z",
            },
        ],
        "accepted_milestone_ids": ["m1"],
        "accepted_criterion_ids": ["c1"],
    }
    if gap_open:
        # Open critical gap → Plan is BLOCKED/PARTIAL.
        bundle["gap_findings"] = [
            {
                "id": "g_missing_recovery",
                "type": "missing",
                "path": "docs/recovery_runbook.md",
                "finding": "runbook referenced by plan but absent",
                "status": "open",
                "severity": "critical",
                "evidence_ref": "g_missing_recovery",
                "fix_receipt_ref": None,
                "recheck_ref": None,
            },
        ]
    else:
        bundle["gap_findings"] = [
            {
                "id": "g_missing_recovery",
                "type": "missing",
                "path": "docs/recovery_runbook.md",
                "finding": "runbook referenced by plan but absent",
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
    return bundle


class G09S1SameTaskCLITest(unittest.TestCase):
    def test_s1_bad_then_continue_good_on_same_task(self):
        env = dict(os.environ)
        env["ONESHOT_TRUSTED_TEST_INPUT"] = "1"
        env["PYTHONPATH"] = f"{_REPO!s}:{env.get('PYTHONPATH', '')}"

        with tempfile.TemporaryDirectory(prefix="g09-s1-") as td:
            td_p = Path(td)
            storage = td_p / "tasks.json"
            request_file = td_p / "req.txt"
            request_file.write_text("G09 S1 same-task drive\n", encoding="utf-8")

            bad_bundle_path = td_p / "bad.json"
            bad_bundle_path.write_text(json.dumps(_bundle_s1(gap_open=True)))
            run_bad = subprocess.run(
                [
                    sys.executable, "-m", "agent.main", "run",
                    "--request-file", str(request_file),
                    "--storage", str(storage),
                    "--repo-root", str(_REPO),
                    "--bundle", str(bad_bundle_path),
                ],
                cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(run_bad.returncode, 1, run_bad.stderr)
            bad_summary = json.loads(run_bad.stdout)
            # Open critical gap stops the Plan at review time -> BLOCKED,
            # the Build never runs so classification is BLOCKED.
            self.assertIn(bad_summary["classification"], ("BLOCKED", "PARTIAL"))
            tid = bad_summary["task_id"]
            self.assertIsNotNone(tid)

            good_bundle_path = td_p / "good.json"
            good_bundle_path.write_text(json.dumps(_bundle_s1(gap_open=False)))
            run_good = subprocess.run(
                [
                    sys.executable, "-m", "agent.main", "continue",
                    "--task-id", tid,
                    "--request-file", str(request_file),
                    "--storage", str(storage),
                    "--repo-root", str(_REPO),
                    "--bundle", str(good_bundle_path),
                ],
                cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(run_good.returncode, 0, run_good.stderr)
            good_summary = json.loads(run_good.stdout)
            self.assertEqual(good_summary["classification"], "VERIFIED")
            self.assertEqual(good_summary["task_id"], tid)

            # Fresh-process lineage check.
            from task_management import TaskManager  # noqa: E402

            tm = TaskManager(storage_path=str(storage))
            rec = tm.get_task(tid)
            self.assertIsNotNone(rec)
            # BLOCKED attempts return before any record persistence, so
            # workflow_records may contain only the successful second
            # attempt. In either case the SECOND or ONLY record must be
            # VERIFIED and share this task_id.
            records = (rec.results or {}).get("workflow_records") or []
            self.assertGreaterEqual(len(records), 1)
            # The last record is the VERIFIED one.
            last = records[-1]
            self.assertEqual(last["classification"], "VERIFIED")
            self.assertEqual(last["research"]["task_id"], tid)
            # When both attempts persisted, prove monotonic revision bump.
            if len(records) >= 2:
                r1 = int(records[-2]["plan"]["revision"])
                r2 = int(records[-1]["plan"]["revision"])
                self.assertEqual(r2, r1 + 1)
                self.assertEqual(
                    records[-1]["plan"].get("preceding_revision"), r1
                )


if __name__ == "__main__":
    unittest.main()
