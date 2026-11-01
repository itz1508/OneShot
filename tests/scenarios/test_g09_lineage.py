"""G09 reopen (reviewer finding on 9d2ce25): same-task continue must
preserve real Research/Plan revision lineage across a fresh-process
readback.

Before this fix, `continue` regenerated Research/Plan/Build from
scratch and did not reference the previous attempt — classification
was PARTIAL -> VERIFIED on the same task_id, but there was no durable
Research r1 -> Plan r1 -> Plan r2 -> Build revision lineage.

After the fix:

  * run_workflow(existing_task_id=...) loads the previous attempt from
    task.results.workflow_records.
  * The new Plan's revision is bumped to prev_plan.revision + 1 and
    carries plan["preceding_record_id"] / plan["preceding_revision"].
  * Both the previous AND the corrected attempt are persisted on
    task.results.workflow_records.
  * A fresh TaskManager on the same storage sees BOTH plan revisions
    on the SAME task_id.
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

# Re-use the S2 bundle factory from the sibling CLI test — the lineage
# is the behaviour we're pinning, not the specific scenario.
from tests.scenarios.test_g09_same_task_cli import (  # noqa: E402
    _bundle_s2 as _s2_bundle,
)


def _run_cli(cmd, env, cwd):
    """Run the oneshot CLI as a subprocess, parse JSON summary stdout."""
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=120)
    try:
        summary = json.loads(proc.stdout)
    except Exception:
        summary = None
    return proc, summary


class G09LineagePreservedTest(unittest.TestCase):
    def test_fresh_process_sees_both_plan_revisions_on_same_task(self):
        env = dict(os.environ)
        env["ONESHOT_TRUSTED_TEST_INPUT"] = "1"
        env["PYTHONPATH"] = f"{_REPO!s}:{env.get('PYTHONPATH', '')}"

        with tempfile.TemporaryDirectory(prefix="g09-lineage-") as td:
            td_p = Path(td)
            storage = td_p / "tasks.json"
            request_file = td_p / "req.txt"
            request_file.write_text("G09 lineage proof\n", encoding="utf-8")

            # Step 1 — BAD invocation (no DO_NOT_USE).
            bad_bundle_path = td_p / "bad.json"
            bad_bundle_path.write_text(json.dumps(_s2_bundle(include_do_not_use=False)))
            run_bad, bad_summary = _run_cli(
                [
                    sys.executable, "-m", "agent.main", "run",
                    "--request-file", str(request_file),
                    "--storage", str(storage),
                    "--repo-root", str(_REPO),
                    "--bundle", str(bad_bundle_path),
                ],
                env=env, cwd=str(_REPO),
            )
            self.assertEqual(run_bad.returncode, 1, run_bad.stderr)
            self.assertEqual(bad_summary["classification"], "PARTIAL")
            tid = bad_summary["task_id"]

            # Step 2 — GOOD continuation on the SAME task_id.
            good_bundle_path = td_p / "good.json"
            good_bundle_path.write_text(json.dumps(_s2_bundle(include_do_not_use=True)))
            run_good, good_summary = _run_cli(
                [
                    sys.executable, "-m", "agent.main", "continue",
                    "--task-id", tid,
                    "--request-file", str(request_file),
                    "--storage", str(storage),
                    "--repo-root", str(_REPO),
                    "--bundle", str(good_bundle_path),
                ],
                env=env, cwd=str(_REPO),
            )
            self.assertEqual(run_good.returncode, 0, run_good.stderr)
            self.assertEqual(good_summary["classification"], "VERIFIED")
            self.assertEqual(good_summary["task_id"], tid)

            # Step 3 — fresh TaskManager on same storage: both attempts are
            # visible as workflow_records on this exact task.
            from task_management import TaskManager  # noqa: E402

            tm = TaskManager(storage_path=str(storage))
            rec = tm.get_task(tid)
            self.assertIsNotNone(rec, "task vanished across processes")
            records = (rec.results or {}).get("workflow_records")
            self.assertIsNotNone(
                records, "workflow_records not persisted on task.results"
            )
            self.assertEqual(
                len(records),
                2,
                f"expected 2 workflow_records; got {len(records) if records else 0}",
            )

            # The two Plan revisions MUST be strictly monotonic on this task.
            p_rev_1 = int(records[0]["plan"]["revision"])
            p_rev_2 = int(records[1]["plan"]["revision"])
            self.assertEqual(p_rev_1, 1, f"first attempt plan.revision != 1: {p_rev_1}")
            self.assertEqual(
                p_rev_2, p_rev_1 + 1,
                f"second attempt plan.revision must advance; got {p_rev_1} -> {p_rev_2}",
            )

            # The second Plan references the first via back-pointer.
            self.assertEqual(
                records[1]["plan"].get("preceding_revision"), p_rev_1,
                f"preceding_revision missing/mismatched: "
                f"{records[1]['plan'].get('preceding_revision')!r}",
            )
            self.assertEqual(
                records[1]["plan"].get("preceding_record_id"),
                records[0]["plan"].get("record_id"),
                "preceding_record_id does not reference the previous Plan",
            )

            # Both attempts share the SAME task_id (lineage proof).
            self.assertEqual(records[0]["research"]["task_id"], tid)
            self.assertEqual(records[1]["research"]["task_id"], tid)

            # The classification arc: PARTIAL on r1, VERIFIED on r2.
            self.assertEqual(records[0]["classification"], "PARTIAL")
            self.assertEqual(records[1]["classification"], "VERIFIED")

            # The Build on r2 is pinned to plan_revision = r2 (G07 manifest).
            r2_manifest = records[1]["build"]["manifest_binding"]
            self.assertEqual(int(r2_manifest["plan_revision"]), p_rev_2)
            self.assertNotEqual(int(r2_manifest["plan_revision"]), p_rev_1)


if __name__ == "__main__":
    unittest.main()
