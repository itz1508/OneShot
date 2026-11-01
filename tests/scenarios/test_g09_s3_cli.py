"""G09 same-task CLI drive for S3 (VALIDATE_FIRST gate).

Mirrors the S1/S2 drives: a BAD bundle has a VALIDATE_FIRST decision
blocking a milestone but then "pretends" (via accepted_milestone_ids
override) that the milestone was admitted anyway → cross-record
validator surfaces "VALIDATE_FIRST blocks step m_gated" and
classification is PARTIAL. The GOOD continuation removes the stale
admission → classification VERIFIED. A fresh TaskManager sees two
workflow_records on the SAME task_id with monotonic Plan revisions.
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


def _bundle_s3(stale_admission: bool) -> dict:
    counter = _REPO / "bin" / "context_counter.py"
    bundle = {
        "objective": "G09 S3 same-task CLI drive",
        "requirements": [
            {
                "id": "R_INDEP",
                "statement": "Count characters (independent of gated claim)",
                "scope": "in_scope",
                "authority_ref": "AGENTS.md",
            },
            {
                "id": "R_GATED",
                "statement": "Byte histogram (requires missing evidence)",
                "scope": "in_scope",
                "authority_ref": "AGENTS.md",
            },
        ],
        "findings": [
            {
                "id": "F_INDEP",
                "claim": "bin/context_counter.py counts characters",
                "evidence_refs": ["bin/context_counter.py"],
                "assessment": "supported",
                "limitations": "",
            },
            {
                "id": "F_GATED",
                "claim": "bin/context_counter.py returns a byte histogram",
                "evidence_refs": ["AGENTS.md"],
                "assessment": "uncertain",
                "limitations": "no byte-histogram code path",
            },
        ],
        "requirement_trace": [
            {
                "requirement_id": "R_INDEP",
                "finding_ids": ["F_INDEP"],
                "fixture_ids": ["bin/context_counter.py"],
                "criterion_ids": ["agent/contracts/build.yaml"],
                "disposition": "covered",
            },
            {
                "requirement_id": "R_GATED",
                "finding_ids": ["F_GATED"],
                "fixture_ids": [],
                "criterion_ids": [],
                "disposition": "deferred",
            },
        ],
        "accepted_requirement_ids": ["R_INDEP", "R_GATED"],
        "plan_milestones": [
            {
                "id": "m_independent",
                "goal": "Count characters",
                "files": ["bin/context_counter.py"],
                "steps": ["invoke"],
                "commands": [f"python {counter}"],
                "expected_observations": ["characters: 4"],
                "status": "pending",
            },
            {
                "id": "m_gated",
                "goal": "Byte histogram (gated)",
                "files": ["bin/context_counter.py"],
                "steps": ["invoke"],
                "commands": [f"python {counter} --histogram"],
                "expected_observations": ["histogram ok"],
                "status": "pending",
            },
        ],
        "acceptance_criteria": [
            {
                "id": "c_indep",
                "requirement_id": "R_INDEP",
                "expected_result": "character count matches",
                "oracle_ref": "bin/context_counter.py",
            },
            {
                "id": "c_gated",
                "requirement_id": "R_GATED",
                "expected_result": "deferred",
                "oracle_ref": "AGENTS.md",
            },
        ],
        "accepted_criterion_ids": ["c_indep", "c_gated"],
        "claim_decisions": [
            {
                "id": "d_use_indep",
                "source_finding_id": "F_INDEP",
                "applicability": "USE",
                "reason": "Direct source inspection.",
                "evidence_refs": ["bin/context_counter.py"],
                "affected_step_ids": ["m_independent"],
                "revision": 1,
                "recorded_at": "2026-11-01T00:00:00Z",
            },
            {
                "id": "d_gate_hist",
                "source_finding_id": "F_GATED",
                "applicability": "VALIDATE_FIRST",
                "reason": "Evidence inconclusive.",
                "evidence_refs": ["AGENTS.md"],
                "affected_step_ids": ["m_gated"],
                "revision": 1,
                "recorded_at": "2026-11-01T00:00:00Z",
            },
        ],
        "gap_findings_mark_resolved": {
            "fix_receipt_ref": "AGENTS.md",
            "recheck_ref": "AGENTS.md",
        },
    }
    if stale_admission:
        # BAD: force m_gated into accepted_milestone_ids anyway.
        bundle["accepted_milestone_ids"] = ["m_independent", "m_gated"]
    else:
        # GOOD: honor the gate.
        bundle["accepted_milestone_ids"] = ["m_independent"]
    bundle["accepted_criterion_ids"] = ["c_indep"]
    return bundle


class G09S3SameTaskCLITest(unittest.TestCase):
    def test_s3_bad_then_continue_good_on_same_task(self):
        env = dict(os.environ)
        env["ONESHOT_TRUSTED_TEST_INPUT"] = "1"
        env["PYTHONPATH"] = f"{_REPO!s}:{env.get('PYTHONPATH', '')}"

        with tempfile.TemporaryDirectory(prefix="g09-s3-") as td:
            td_p = Path(td)
            storage = td_p / "tasks.json"
            request_file = td_p / "req.txt"
            request_file.write_text("G09 S3 same-task drive\n", encoding="utf-8")

            bad_path = td_p / "bad.json"
            bad_path.write_text(json.dumps(_bundle_s3(stale_admission=True)))
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
            self.assertEqual(run_bad.returncode, 1, run_bad.stderr)
            bad_summary = json.loads(run_bad.stdout)
            self.assertEqual(bad_summary["classification"], "PARTIAL")
            # Diagnostic: cross-record must flag the gate.
            self.assertTrue(
                any(
                    "VALIDATE_FIRST blocks step m_gated" in e
                    for e in (bad_summary.get("cross_record_errors") or [])
                ),
                f"expected VALIDATE_FIRST error; got: "
                f"{bad_summary.get('cross_record_errors')}",
            )
            tid = bad_summary["task_id"]

            good_path = td_p / "good.json"
            good_path.write_text(json.dumps(_bundle_s3(stale_admission=False)))
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
            self.assertEqual(records[0]["classification"], "PARTIAL")
            self.assertEqual(records[1]["classification"], "VERIFIED")
            r1 = int(records[0]["plan"]["revision"])
            r2 = int(records[1]["plan"]["revision"])
            self.assertEqual(r2, r1 + 1)
            self.assertEqual(records[1]["plan"].get("preceding_revision"), r1)


if __name__ == "__main__":
    unittest.main()
