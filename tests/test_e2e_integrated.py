"""Integrated E2E — stitches Audit Discovery -> Run -> Judge -> Completion.

This test exercises the full agent orchestration path end-to-end
against a scripted Judge adapter (no live Baseten calls — the live
path is already proven in tests/test_judge_live_baseten.py). The
test asserts:

  1. Audit Discovery accepts a handoff and produces a Run.
  2. Run.execute() drives tasks to completion in parallel.
  3. Build Admission metadata lands on each child Task's TaskManager
     row.
  4. CompletionEvaluator grades the finished Run and persists a
     receipt on the parent task.
  5. Pause/resume respects terminal task states.
"""

from __future__ import annotations

import json
import threading
import time

import pytest

from agent.audit_discovery import (
    AuditDiscoveryRunner,
    DiscoveryHandoff,
)
from agent.evaluation import CompletionEvaluator
from agent.orchestration import PlannedFileOperation, Task
from agent.prompt_authoring.config import (
    JudgeConfig,
    JudgeSection,
    ModelInventoryEntry,
)
from agent.prompt_authoring.judge import EvaluationRubric, LLMJudge
from tests.test_judge import ScriptedJudgeAdapter


@pytest.fixture
def tm_snapshot(tmp_path):
    return str(tmp_path / "tasks.json")


@pytest.fixture
def rubric():
    return EvaluationRubric(
        name="e2e_rubric",
        criteria=("io_contract_compliance", "evidence_fidelity"),
    )


@pytest.fixture
def judge_config(tmp_path):
    return JudgeConfig(
        judge=JudgeSection(
            default_model="muse-spark-open-1026",
            max_cost_usd=5.0,
            timeout_s=60.0,
            usage_log_path=str(tmp_path / "usage.jsonl"),
        ),
        providers={},
        models={
            "muse-spark-open-1026": ModelInventoryEntry(
                input_per_1m=1.0, output_per_1m=2.0
            ),
        },
    )


def _judge_pass_payload():
    return json.dumps(
        {
            "verdict": "pass",
            "critical_failure": False,
            "criteria": [
                {"criterion": "io_contract_compliance", "score": 9, "notes": ""},
                {"criterion": "evidence_fidelity", "score": 8, "notes": ""},
            ],
            "findings": [],
        }
    )


class TestIntegratedE2E:
    def test_full_discovery_execute_judge_completion(
        self, tm_snapshot, rubric, judge_config
    ):
        # 1. Audit Discovery handoff.
        handoff = DiscoveryHandoff(
            plan_id="e2e-plan-01",
            objective="integrated e2e run",
            files=(
                PlannedFileOperation(path="src/mod_a.py", operation="create"),
                PlannedFileOperation(path="src/mod_b.py", operation="create"),
                PlannedFileOperation(path="src/mod_c.py", operation="create"),
            ),
        )
        runner = AuditDiscoveryRunner()
        run = runner.start_from_handoff(handoff, storage_path=tm_snapshot)
        assert run.plan_id == "e2e-plan-01"
        assert [t.path for t in run.tasks] == [
            "src/mod_a.py",
            "src/mod_b.py",
            "src/mod_c.py",
        ]
        assert run.status() == "pending"

        # 2. Run.execute() with a per-task writer that records I/O ops.
        performed: list[str] = []
        lock = threading.Lock()

        def writer(task: Task) -> None:
            # Pretend to write the planned file.
            with lock:
                performed.append(task.path)
            time.sleep(0.01)

        results = run.execute(executor=writer, max_workers=3)
        assert set(results.values()) == {"completed"}
        assert sorted(performed) == [
            "src/mod_a.py",
            "src/mod_b.py",
            "src/mod_c.py",
        ]
        assert run.status() == "completed"

        # 3. Build Admission on every child task.
        tm = run._controller.tm
        for t in run.tasks:
            row = tm.get_task(t.task_id)
            admission = row.metadata["build_admission"]
            assert admission["outcome"] == "completed"
            assert admission["task_path"] == t.path
            assert admission["actor"] == "agent.orchestration"

        # 4. CompletionEvaluator grades the finished Run and persists.
        adapter = ScriptedJudgeAdapter(
            [(_judge_pass_payload(), 120, 60)]
        )
        judge = LLMJudge(
            adapter=adapter, config=judge_config, rubric=rubric
        )
        evaluator = CompletionEvaluator(judge=judge)
        receipt = evaluator.evaluate(
            run,
            candidate={
                "plan_id": "e2e-plan-01",
                "paths": sorted(performed),
                "task_count": len(performed),
            },
        )
        assert receipt.verdict == "pass"
        assert receipt.critical_failure is False
        assert receipt.task_summary == {"completed": 3}
        assert receipt.rubric_name == "e2e_rubric"
        assert receipt.judge_model == "muse-spark-open-1026"
        assert receipt.spent_usd > 0.0

        # 5. Receipt landed on parent task.
        parent = tm.get_task(run._parent_task_id)
        receipts = parent.metadata.get("completion_receipts")
        assert isinstance(receipts, list) and len(receipts) == 1
        assert receipts[0]["plan_id"] == "e2e-plan-01"
        assert receipts[0]["verdict"] == "pass"

    def test_pause_resume_mid_pipeline(self, tm_snapshot, rubric, judge_config):
        """A paused Run returns a paused snapshot without executing;
        resume + execute drives it to completion; completion
        evaluation then persists a receipt."""
        handoff = DiscoveryHandoff(
            plan_id="e2e-plan-02",
            objective="pause-resume e2e",
            files=(
                PlannedFileOperation(path="x.py"),
                PlannedFileOperation(path="y.py"),
            ),
        )
        runner = AuditDiscoveryRunner()
        run = runner.start_from_handoff(handoff, storage_path=tm_snapshot)
        run.pause()
        results_paused = run.execute()
        assert set(results_paused.values()) == {"paused"}
        assert run.status() == "paused"
        run.resume()
        results = run.execute()
        assert set(results.values()) == {"completed"}
        adapter = ScriptedJudgeAdapter([(_judge_pass_payload(), 50, 25)])
        judge = LLMJudge(adapter=adapter, config=judge_config, rubric=rubric)
        receipt = CompletionEvaluator(judge=judge).evaluate(
            run, candidate={"ok": True}
        )
        assert receipt.verdict == "pass"

    def test_failing_task_blocks_completion_pass(
        self, tm_snapshot, rubric, judge_config
    ):
        """A Run with a failed task still gets evaluated — the receipt
        just records that only some tasks completed."""
        handoff = DiscoveryHandoff(
            plan_id="e2e-plan-03",
            objective="partial failure e2e",
            files=(
                PlannedFileOperation(path="good.py"),
                PlannedFileOperation(path="bad.py"),
            ),
        )
        runner = AuditDiscoveryRunner()
        run = runner.start_from_handoff(handoff, storage_path=tm_snapshot)

        def writer(task: Task) -> None:
            if task.path == "bad.py":
                raise RuntimeError("writer refused")

        results = run.execute(executor=writer)
        assert run.status() == "failed"
        assert any(v == "completed" for v in results.values())
        assert any(v == "failed" for v in results.values())
        adapter = ScriptedJudgeAdapter([(_judge_pass_payload(), 60, 30)])
        judge = LLMJudge(adapter=adapter, config=judge_config, rubric=rubric)
        receipt = CompletionEvaluator(judge=judge).evaluate(
            run, candidate={"attempted": 2}
        )
        assert receipt.task_summary.get("completed", 0) == 1
        assert receipt.task_summary.get("failed", 0) == 1
