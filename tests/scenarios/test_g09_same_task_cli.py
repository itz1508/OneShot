"""G09 — CLI-driven same-task BAD → correction → GOOD.

Represents a shortcut version of the audit's "S1-S5 through the real
CLI with same task_id" requirement, demonstrated here for the S2
DO_NOT_USE scenario because it has the simplest fault model:

  1. Run `python -m agent.main run --request-file ... --bundle BAD`
     against a fresh `--storage`. The BAD bundle omits the
     DO_NOT_USE decision for the unsupported finding — classification
     is PARTIAL and exit code is 1.
  2. Parse the task_id from the first run's JSON stdout.
  3. Run `python -m agent.main continue --task-id <id> --bundle GOOD`
     against the SAME --storage. The GOOD bundle supplies the
     corrective DO_NOT_USE decision; classification is VERIFIED and
     exit code is 0.
  4. Open a fresh TaskManager on the same storage and assert BOTH runs
     left visible event history on the same task_id (lineage proof).

This is the pattern that must extend to S1, S3, S4, S5 in a follow-up
to prove the audit's "same-task continuation" invariant end-to-end.
This file demonstrates the plumbing works and leaves the extension
as a documented follow-up.
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


def _bundle_s2(include_do_not_use: bool) -> dict:
    counter = _REPO / "bin" / "context_counter.py"
    bundle = {
        "objective": "G09 — S2 same-task CLI drive",
        "requirements": [
            {
                "id": "R_SUPPORTED",
                "statement": "Count characters",
                "scope": "in_scope",
                "authority_ref": "AGENTS.md",
            },
            {
                "id": "R_CLAIM",
                "statement": "External claim: audio streaming",
                "scope": "in_scope",
                "authority_ref": "AGENTS.md",
            },
        ],
        "findings": [
            {
                "id": "F_SUPPORTED",
                "claim": "counts characters",
                "evidence_refs": ["bin/context_counter.py"],
                "assessment": "supported",
                "limitations": "",
            },
            {
                "id": "F_UNSUPPORTED",
                "claim": "streams audio",
                "evidence_refs": ["AGENTS.md"],
                "assessment": "contradicted",
                "limitations": "no audio code path exists",
            },
        ],
        "requirement_trace": [
            {
                "requirement_id": "R_SUPPORTED",
                "finding_ids": ["F_SUPPORTED"],
                "fixture_ids": ["bin/context_counter.py"],
                "criterion_ids": ["agent/contracts/build.yaml"],
                "disposition": "covered",
            },
            {
                "requirement_id": "R_CLAIM",
                "finding_ids": ["F_UNSUPPORTED"],
                "fixture_ids": [],
                "criterion_ids": [],
                "disposition": "deferred",
            },
        ],
        "accepted_requirement_ids": ["R_SUPPORTED", "R_CLAIM"],
        "plan_milestones": [
            {
                "id": "m_keep",
                "goal": "Count characters",
                "files": ["bin/context_counter.py"],
                "steps": ["invoke"],
                "commands": [f"python {counter}"],
                "expected_observations": ["characters: 4"],
                "status": "pending",
            },
            {
                "id": "m_removed",
                "goal": "Audio stream (derived from unsupported claim)",
                "files": ["bin/context_counter.py"],
                "steps": ["invoke"],
                "commands": [f"python {counter} --audio"],
                "expected_observations": ["audio ok"],
                "status": "pending",
            },
        ],
        "acceptance_criteria": [
            {
                "id": "c_supported",
                "requirement_id": "R_SUPPORTED",
                "expected_result": "character count matches",
                "oracle_ref": "bin/context_counter.py",
            },
        ],
        "claim_decisions": [
            {
                "id": "d_use",
                "source_finding_id": "F_SUPPORTED",
                "applicability": "USE",
                "reason": "Direct source inspection.",
                "evidence_refs": ["bin/context_counter.py"],
                "affected_step_ids": ["m_keep"],
                "revision": 1,
                "recorded_at": "2026-11-01T00:00:00Z",
            }
        ],
        "accepted_milestone_ids": ["m_keep"],
        "accepted_criterion_ids": ["c_supported"],
        "gap_findings_mark_resolved": {
            "fix_receipt_ref": "AGENTS.md",
            "recheck_ref": "AGENTS.md",
        },
    }
    if include_do_not_use:
        bundle["claim_decisions"].append(
            {
                "id": "d_block",
                "source_finding_id": "F_UNSUPPORTED",
                "applicability": "DO_NOT_USE",
                "reason": "Claim contradicted.",
                "evidence_refs": ["bin/context_counter.py"],
                "affected_step_ids": ["m_removed"],
                "revision": 1,
                "recorded_at": "2026-11-01T00:00:00Z",
            }
        )
    return bundle


class G09SameTaskCLITest(unittest.TestCase):
    def test_s2_bad_then_continue_good_on_same_task(self):
        env = dict(os.environ)
        env["ONESHOT_TRUSTED_TEST_INPUT"] = "1"
        env["PYTHONPATH"] = f"{_REPO!s}:{env.get('PYTHONPATH', '')}"

        with tempfile.TemporaryDirectory(prefix="g09-s2-") as td:
            td_p = Path(td)
            storage = td_p / "tasks.json"
            request_file = td_p / "req.txt"
            request_file.write_text("G09 S2 same-task drive\n", encoding="utf-8")

            bad_bundle_path = td_p / "bad.json"
            bad_bundle_path.write_text(json.dumps(_bundle_s2(include_do_not_use=False)))

            # Step 1 — BAD invocation. Expect classification PARTIAL, exit 1.
            run_bad = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent.main",
                    "run",
                    "--request-file",
                    str(request_file),
                    "--storage",
                    str(storage),
                    "--repo-root",
                    str(_REPO),
                    "--bundle",
                    str(bad_bundle_path),
                ],
                cwd=str(_REPO),
                env=env,
                capture_output=True,
                text=True,
                timeout=90,
            )
            self.assertEqual(run_bad.returncode, 1, run_bad.stderr)
            bad_summary = json.loads(run_bad.stdout)
            self.assertEqual(bad_summary["classification"], "PARTIAL")
            tid = bad_summary["task_id"]
            self.assertIsNotNone(tid)

            # Step 2 — GOOD continuation on the SAME task_id.
            good_bundle_path = td_p / "good.json"
            good_bundle_path.write_text(json.dumps(_bundle_s2(include_do_not_use=True)))
            run_good = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "agent.main",
                    "continue",
                    "--task-id",
                    tid,
                    "--request-file",
                    str(request_file),
                    "--storage",
                    str(storage),
                    "--repo-root",
                    str(_REPO),
                    "--bundle",
                    str(good_bundle_path),
                ],
                cwd=str(_REPO),
                env=env,
                capture_output=True,
                text=True,
                timeout=90,
            )
            self.assertEqual(run_good.returncode, 0, run_good.stderr)
            good_summary = json.loads(run_good.stdout)
            self.assertEqual(good_summary["classification"], "VERIFIED")
            self.assertEqual(good_summary["task_id"], tid)

            # Step 3 — fresh reader sees BOTH runs' events on the SAME task.
            from task_management import TaskManager  # noqa: E402

            tm = TaskManager(storage_path=str(storage))
            rec = tm.get_task(tid)
            self.assertIsNotNone(rec, "task vanished across runs")
            # Each stage run appends events (research/plan/build transitions
            # + resume/complete). A same-task run with two full cycles has
            # at least ~6 events; be conservative and require >= 4.
            self.assertGreaterEqual(
                len(rec.events),
                4,
                f"only {len(rec.events)} events — same-task continuation did not append",
            )
            # The LAST event's to_state must be 'completed' (good_run ended VERIFIED).
            self.assertEqual(rec.events[-1]["to_state"], "completed")


if __name__ == "__main__":
    unittest.main()
