"""CompletionEvaluator tests (scripted adapter, no live calls)."""

from __future__ import annotations

import json

import pytest

import agent
from agent.evaluation import (
    CompletionEvaluator,
    CompletionReceipt,
    CompletionReceiptError,
)
from agent.orchestration import PlannedFileOperation, RunPlan
from agent.prompt_authoring.config import (
    JudgeConfig,
    JudgeSection,
    ModelInventoryEntry,
)
from agent.prompt_authoring.judge import EvaluationRubric, LLMJudge
from tests.test_judge import ScriptedJudgeAdapter  # reuse adapter

# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

@pytest.fixture
def tm_snapshot(tmp_path):
    return str(tmp_path / "tasks.json")


@pytest.fixture
def plan():
    return RunPlan(
        plan_id="eval-plan-01",
        objective="completion eval",
        files=(PlannedFileOperation(path="a.py"), PlannedFileOperation(path="b.py")),
    )


@pytest.fixture
def rubric():
    return EvaluationRubric(
        name="completion_rubric",
        criteria=("io_contract_compliance",),
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


def _pass_payload():
    return json.dumps(
        {
            "verdict": "pass",
            "critical_failure": False,
            "criteria": [
                {"criterion": "io_contract_compliance", "score": 9, "notes": ""},
            ],
            "findings": [],
        }
    )


def _fail_payload():
    return json.dumps(
        {
            "verdict": "fail",
            "critical_failure": True,
            "criteria": [
                {"criterion": "io_contract_compliance", "score": 1, "notes": ""},
            ],
        }
    )


class TestEvaluateFinishedRun:
    def test_evaluate_completed_run_single_mode(
        self, plan, tm_snapshot, rubric, judge_config
    ):
        run = agent.start(plan, storage_path=tm_snapshot)
        run.execute()
        adapter = ScriptedJudgeAdapter([(_pass_payload(), 100, 50)])
        judge = LLMJudge(adapter=adapter, config=judge_config, rubric=rubric)
        evaluator = CompletionEvaluator(judge=judge)
        receipt = evaluator.evaluate(
            run, candidate={"summary": "two files edited"}
        )
        assert isinstance(receipt, CompletionReceipt)
        assert receipt.plan_id == "eval-plan-01"
        assert receipt.mode == "single"
        assert receipt.verdict == "pass"
        assert receipt.critical_failure is False
        assert receipt.task_summary.get("completed") == 2
        assert receipt.spent_usd > 0.0

    def test_evaluate_persists_receipt_on_parent_task(
        self, plan, tm_snapshot, rubric, judge_config
    ):
        run = agent.start(plan, storage_path=tm_snapshot)
        run.execute()
        adapter = ScriptedJudgeAdapter([(_pass_payload(), 100, 50)])
        judge = LLMJudge(adapter=adapter, config=judge_config, rubric=rubric)
        evaluator = CompletionEvaluator(judge=judge)
        evaluator.evaluate(run, candidate={"summary": "..."})
        tm = run._controller.tm
        parent = tm.get_task(run._parent_task_id)
        receipts = parent.metadata.get("completion_receipts")
        assert isinstance(receipts, list) and len(receipts) == 1
        rec = receipts[0]
        assert rec["plan_id"] == "eval-plan-01"
        assert rec["verdict"] == "pass"

    def test_evaluate_reference_guided_mode(
        self, plan, tm_snapshot, rubric, judge_config
    ):
        run = agent.start(plan, storage_path=tm_snapshot)
        run.execute()
        adapter = ScriptedJudgeAdapter([(_pass_payload(), 100, 50)])
        judge = LLMJudge(adapter=adapter, config=judge_config, rubric=rubric)
        evaluator = CompletionEvaluator(judge=judge)
        receipt = evaluator.evaluate(
            run,
            candidate={"summary": "candidate"},
            reference={"summary": "reference-from-oracle"},
        )
        assert receipt.mode == "reference_guided"
        assert receipt.verdict == "pass"

    def test_evaluate_failing_candidate_marks_fail(
        self, plan, tm_snapshot, rubric, judge_config
    ):
        run = agent.start(plan, storage_path=tm_snapshot)
        run.execute()
        adapter = ScriptedJudgeAdapter([(_fail_payload(), 100, 50)])
        judge = LLMJudge(adapter=adapter, config=judge_config, rubric=rubric)
        evaluator = CompletionEvaluator(judge=judge)
        receipt = evaluator.evaluate(run, candidate={"summary": "..."})
        assert receipt.verdict == "fail"
        assert receipt.critical_failure is True


class TestEvaluateRefusals:
    def test_refuses_unfinished_run(
        self, plan, tm_snapshot, rubric, judge_config
    ):
        run = agent.start(plan, storage_path=tm_snapshot)
        # Did NOT call execute(); tasks still pending.
        adapter = ScriptedJudgeAdapter([])
        judge = LLMJudge(adapter=adapter, config=judge_config, rubric=rubric)
        evaluator = CompletionEvaluator(judge=judge)
        with pytest.raises(CompletionReceiptError, match="run_not_finished"):
            evaluator.evaluate(run, candidate={"summary": "..."})

    def test_reference_same_object_refused_by_judge(
        self, plan, tm_snapshot, rubric, judge_config
    ):
        run = agent.start(plan, storage_path=tm_snapshot)
        run.execute()
        adapter = ScriptedJudgeAdapter([(_pass_payload(), 100, 50)])
        judge = LLMJudge(adapter=adapter, config=judge_config, rubric=rubric)
        evaluator = CompletionEvaluator(judge=judge)
        shared = {"summary": "x"}
        with pytest.raises(CompletionReceiptError, match="judge_dispatch_failed"):
            evaluator.evaluate(run, candidate=shared, reference=shared)
