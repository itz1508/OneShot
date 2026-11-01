"""G11 — Durable, revision-safe TaskManager persistence (red → green).

Red-first expectations against the baseline source at 8729a01 BEFORE the
fix lands:

  1. A concurrent writer that reads then writes WITHOUT reconciling can
     clobber another process's committed state (last-writer-wins).
  2. A truncated or partial write while reading leads to a crash on
     reload (no explicit recovery policy).
  3. There is NO public API for persisting a `UserDecisionWait`; the
     controller uses `tm._save()` (private seam).

These tests express the behaviour we need. They will fail on the current
code and pass after the §2 §G11 implementation lands.

NOTE: a cross-platform file-lock implementation covers Windows and
Linux; we only exercise the POSIX path here because the CI matrix is
ubuntu-latest. The code path for Windows (`msvcrt.locking`) is unit-
tested indirectly by invoking the lock helper under a mock environment.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "tools"))

from task_management import TaskManager  # noqa: E402


class AtomicSaveTest(unittest.TestCase):
    def test_concurrent_writer_cannot_clobber_committed_history(self):
        """Two processes creating different tasks must each survive.

        Baseline (no fix) will fail because both processes read an empty
        store, each adds its task, each writes a full snapshot — second
        writer overwrites first.
        """
        with tempfile.TemporaryDirectory(prefix="g11-concurrent-") as td:
            storage = Path(td) / "tasks.json"

            # Launch two writer processes in parallel.
            def spawn(tid: str) -> subprocess.Popen:
                code = f"""
import sys, time
sys.path.insert(0, {str(_REPO / "tools")!r})
from task_management import TaskManager
tm = TaskManager(storage_path={str(storage)!r})
# tiny stagger so both are inside the critical section
time.sleep(0.05)
tm.create_task(task_id={tid!r}, metadata={{"producer": {tid!r}}})
"""
                return subprocess.Popen([sys.executable, "-c", code])

            p1 = spawn("concurrent-a")
            p2 = spawn("concurrent-b")
            p1.wait(timeout=15)
            p2.wait(timeout=15)
            self.assertEqual(p1.returncode, 0, "writer A failed")
            self.assertEqual(p2.returncode, 0, "writer B failed")

            # A fresh reader must see BOTH tasks.
            tm = TaskManager(storage_path=str(storage))
            ids = {t.task_id for t in tm._tasks.values()}
            self.assertIn("concurrent-a", ids, "task A lost — concurrent clobber")
            self.assertIn("concurrent-b", ids, "task B lost — concurrent clobber")


class RevisionGuardedUpdateTest(unittest.TestCase):
    def test_stale_in_memory_task_cannot_overwrite_newer_committed_state(self):
        """A long-running controller must not overwrite a newer snapshot.

        Baseline fails because `_save()` writes everything in-memory and
        never checks whether the on-disk revision has advanced.
        """
        with tempfile.TemporaryDirectory(prefix="g11-stale-") as td:
            storage = Path(td) / "tasks.json"

            # Writer A creates the task and holds a stale reference.
            tm_a = TaskManager(storage_path=str(storage))
            tm_a.create_task(task_id="t1", metadata={"owner": "A", "revision": 1})

            # Writer B (fresh process on same storage) advances the task.
            code_b = f"""
import sys
sys.path.insert(0, {str(_REPO / "tools")!r})
from task_management import TaskManager
tm = TaskManager(storage_path={str(storage)!r})
rec = tm.get_task("t1")
rec.metadata["revision"] = 2
rec.metadata["owner"] = "B"
# Public API for revision-guarded metadata update (G11 contract).
tm.set_task_metadata("t1", rec.metadata, if_revision=1)
"""
            p = subprocess.run([sys.executable, "-c", code_b], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)

            # Writer A tries to persist its STALE revision=1 copy.
            # G11 contract: raises a typed `StaleRevisionError` so callers
            # know to reconcile rather than catch everything.
            from task_management import StaleRevisionError

            with self.assertRaises(StaleRevisionError):
                tm_a.set_task_metadata("t1", {"owner": "A-stale", "revision": 1}, if_revision=1)

            # On disk, the writer-B update must survive.
            with open(storage) as f:
                data = json.load(f)
            self.assertEqual(data["t1"]["metadata"]["owner"], "B")
            self.assertEqual(data["t1"]["metadata"]["revision"], 2)


class CorruptSnapshotRecoveryTest(unittest.TestCase):
    def test_truncated_json_raises_corrupt_store_error_by_default(self):
        """G11 reopen (second concern): a corrupt snapshot must FAIL
        CLOSED by default rather than silently continue with an empty
        store (which was equivalent to losing durable history)."""
        from task_management import CorruptStoreError

        with tempfile.TemporaryDirectory(prefix="g11-corrupt-") as td:
            storage = Path(td) / "tasks.json"
            storage.write_text('{"t": {"task_id": "t", "state": "pending"')
            with self.assertRaises(CorruptStoreError):
                TaskManager(storage_path=str(storage))
            quarantined = list(Path(td).glob("tasks.json.corrupt-*"))
            self.assertEqual(len(quarantined), 1)
            self.assertFalse(storage.exists())

    def test_allow_corrupt_opt_in_still_recovers_safely(self):
        """Callers that genuinely need to continue (fresh install,
        tooling that treats corrupt as empty) MUST explicitly opt in."""
        with tempfile.TemporaryDirectory(prefix="g11-corrupt-ok-") as td:
            storage = Path(td) / "tasks.json"
            storage.write_text('{"t": {"task_id": "t", "state": "pending"')
            tm = TaskManager(storage_path=str(storage), allow_corrupt=True)
            self.assertEqual(tm._tasks, {})
            quarantined = list(Path(td).glob("tasks.json.corrupt-*"))
            self.assertEqual(len(quarantined), 1)


class DecisionWaitPublicApiTest(unittest.TestCase):
    def test_task_manager_has_public_set_decision_wait(self):
        """§2 requires a *public* TaskManager method for decision-wait
        updates. Baseline reaches through `tm._save()` from the
        controller, which is a private seam."""
        tm = TaskManager(storage_path=str(Path(tempfile.gettempdir()) / "g11-dw.json"))
        self.assertTrue(
            hasattr(tm, "set_decision_wait"),
            "TaskManager must expose set_decision_wait as a public API",
        )
        self.assertTrue(
            hasattr(tm, "clear_decision_wait"),
            "TaskManager must expose clear_decision_wait as a public API",
        )


if __name__ == "__main__":
    unittest.main()


class MetadataMergePolicyTest(unittest.TestCase):
    """G11 reopen (first concern): transition() must not merge stale
    in-memory metadata OVER a newer committed value. Only keys that are
    new to the in-memory record may be added; existing keys stay with
    the on-disk value."""

    def test_stale_in_memory_metadata_does_not_overwrite_committed(self):
        with tempfile.TemporaryDirectory(prefix="g11-merge-") as td:
            storage = Path(td) / "tasks.json"
            # Writer A creates the task with v=1 and holds a reference.
            tm_a = TaskManager(storage_path=str(storage))
            tm_a.create_task(task_id="t1", metadata={"owner": "A", "revision": 1})

            # Writer B (new process on same storage) advances the task.
            import subprocess

            code_b = f"""
import sys
sys.path.insert(0, {str(_REPO / "tools")!r})
from task_management import TaskManager
tm = TaskManager(storage_path={str(storage)!r})
tm.set_task_metadata('t1', {{'owner':'B','revision':2}}, if_revision=1)
"""
            proc = subprocess.run([sys.executable, "-c", code_b], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)

            # Now writer A performs a transition. Baseline (before fix)
            # would merge its stale metadata ({'owner':'A','revision':1})
            # OVER the newer committed state. The new policy keeps the
            # committed values and only adds brand-new keys.
            tm_a.transition("t1", "running", detail="A transition after stale read")

            # Open a fresh reader to see what was actually persisted.
            tm_fresh = TaskManager(storage_path=str(storage))
            rec = tm_fresh.get_task("t1")
            self.assertEqual(rec.metadata["owner"], "B")
            self.assertEqual(rec.metadata["revision"], 2)

    def test_new_in_memory_metadata_keys_are_preserved_across_reload(self):
        """The merge still ADDS keys that are new in the in-memory
        record (controller's 'stage' write pattern)."""
        with tempfile.TemporaryDirectory(prefix="g11-merge-new-") as td:
            storage = Path(td) / "tasks.json"
            tm = TaskManager(storage_path=str(storage))
            tm.create_task(task_id="t1", metadata={"owner": "A"})
            rec = tm.get_task("t1")
            # Simulate the controller's "mutate task.metadata then call
            # transition" pattern: add a new key in memory.
            rec.metadata["stage"] = "plan"
            tm.transition("t1", "running", detail="plan stage")

            # The new key must still be present after the write.
            tm_fresh = TaskManager(storage_path=str(storage))
            self.assertEqual(tm_fresh.get_task("t1").metadata.get("stage"), "plan")
            # And the pre-existing key is unchanged.
            self.assertEqual(tm_fresh.get_task("t1").metadata.get("owner"), "A")
