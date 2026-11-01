"""G09 same-task CLI drive for S4 (Build output contradicts Plan).

S4 is subtle: Plan r1 claims expected_observations=["characters: 99"]
for the counter; the real counter outputs "characters: 4". The Build
record itself still validates and classifies VERIFIED at
cross-record level because validate_pipeline does not inspect the
runtime stdout. The scenario's oracle layer is what catches the
mismatch via the scenario runner's build_runner_stdout assertions.

For the CLI-driven lineage drive, we focus on the DURABLE claim
revision bump: Plan r1 pins the wrong claim (revision=1), Plan r2
corrects it (revision=2) with the matching expected observation.
Both attempts land on the same task_id; the second attempt's Plan
revision strictly dominates the first.
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


def _bundle_s4(expected_text: str) -> dict:
    counter = _REPO / "bin" / "context_counter.py"
    return {
        "objective": "G09 S4 same-task CLI drive",
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
                "goal": "Count characters",
                "files": ["bin/context_counter.py"],
                "steps": ["invoke"],
                "commands": [f"python {counter}"],
                "expected_observations": [expected_text],
                "status": "pending",
            },
        ],
        "acceptance_criteria": [
            {
                "id": "c1",
                "requirement_id": "R1",
                "expected_result": expected_text,
                "oracle_ref": "bin/context_counter.py",
            },
        ],
        "claim_decisions": [
            {
                "id": "d1",
                "source_finding_id": "F1",
                "applicability": "USE",
                "reason": "Direct source inspection.",
                "evidence_refs": ["bin/context_counter.py"],
                "affected_step_ids": ["m1"],
                "revision": 1,
                "recorded_at": "2026-11-01T00:00:00Z",
            },
        ],
        "accepted_milestone_ids": ["m1"],
        "accepted_criterion_ids": ["c1"],
        "gap_findings_mark_resolved": {
            "fix_receipt_ref": "AGENTS.md",
            "recheck_ref": "AGENTS.md",
        },
    }


class G09S4SameTaskCLITest(unittest.TestCase):
    def test_s4_wrong_then_continue_right_on_same_task(self):
        env = dict(os.environ)
        env["ONESHOT_TRUSTED_TEST_INPUT"] = "1"
        env["PYTHONPATH"] = f"{_REPO!s}:{env.get('PYTHONPATH', '')}"

        with tempfile.TemporaryDirectory(prefix="g09-s4-") as td:
            td_p = Path(td)
            storage = td_p / "tasks.json"
            request_file = td_p / "req.txt"
            request_file.write_text("G09 S4 same-task drive\n", encoding="utf-8")

            # r1: wrong expected_observations (characters: 99).
            r1_path = td_p / "r1.json"
            r1_path.write_text(json.dumps(_bundle_s4("characters: 99")))
            run_r1 = subprocess.run(
                [
                    sys.executable, "-m", "agent.main", "run",
                    "--request-file", str(request_file),
                    "--storage", str(storage),
                    "--repo-root", str(_REPO),
                    "--bundle", str(r1_path),
                ],
                cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=120,
            )
            # Both VERIFIED and PARTIAL are legitimate here — the agent's
            # Build-plan evaluates observed stdout against the Plan's
            # expected_observations and marks all_pass accordingly. We
            # accept whichever classification run_workflow produces,
            # since what matters is the LINEAGE: both attempts land on
            # one task with distinct Plan revisions.
            self.assertIn(run_r1.returncode, (0, 1), run_r1.stderr)
            r1_summary = json.loads(run_r1.stdout)
            tid = r1_summary["task_id"]
            self.assertIsNotNone(tid)

            # r2: aligned expected_observations.
            r2_path = td_p / "r2.json"
            r2_path.write_text(json.dumps(_bundle_s4("characters: 4")))
            run_r2 = subprocess.run(
                [
                    sys.executable, "-m", "agent.main", "continue",
                    "--task-id", tid,
                    "--request-file", str(request_file),
                    "--storage", str(storage),
                    "--repo-root", str(_REPO),
                    "--bundle", str(r2_path),
                ],
                cwd=str(_REPO), env=env, capture_output=True, text=True, timeout=120,
            )
            self.assertEqual(run_r2.returncode, 0, run_r2.stderr)
            r2_summary = json.loads(run_r2.stdout)
            self.assertEqual(r2_summary["classification"], "VERIFIED")
            self.assertEqual(r2_summary["task_id"], tid)

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
            # Build on r2 is pinned to plan_revision=r2.
            self.assertEqual(
                int(records[1]["build"]["manifest_binding"]["plan_revision"]),
                r2,
            )


if __name__ == "__main__":
    unittest.main()
