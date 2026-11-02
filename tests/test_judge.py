"""LLMJudge unit tests — exercises the three evaluation modes against a
scripted adapter (no live calls, no network).

Reuses the existing provider adapter protocol and the EvaluationRubric
/ EvaluationResult contract. Deliberately no new fixture files — the
scripted adapter is a trivial class defined inline, matching the
reviewer's "reuse fixtures and acceptance criteria" directive.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

import pytest

from agent.prompt_authoring.config import (
    JudgeConfig,
    JudgeSection,
    ModelInventoryEntry,
)
from agent.prompt_authoring.judge import (
    BudgetExceeded,
    EvaluationRubric,
    LLMJudge,
    PairwiseEvaluationResult,
    SingleEvaluationResult,
)
from agent.providers.base import UnsupportedCapabilityError
from agent.providers.types import (
    ProviderCapabilities,
    UnifiedRequest,
    UnifiedResponse,
    Usage,
)

# ---------------------------------------------------------------------
# Scripted adapter — returns a canned JSON response per call.
# ---------------------------------------------------------------------

class ScriptedJudgeAdapter:
    """Minimal ProviderAdapter satisfying the Protocol runtime check.

    The adapter advertises ``structured_outputs=True`` and replays a
    pre-recorded list of (content, input_tokens, output_tokens)
    tuples. The Judge's test harness drives it one call at a time.
    """

    def __init__(
        self,
        scripted: Iterable[tuple[str, int, int]],
        *,
        structured_outputs: bool = True,
    ):
        self._scripted = list(scripted)
        self._i = 0
        self._structured = bool(structured_outputs)
        self.requests: list[UnifiedRequest] = []

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(structured_outputs=self._structured)

    def generate(self, request: UnifiedRequest) -> UnifiedResponse:
        self.requests.append(request)
        if self._i >= len(self._scripted):
            raise RuntimeError("script exhausted")
        content, inp, out = self._scripted[self._i]
        self._i += 1
        return UnifiedResponse(
            content=content,
            usage=Usage(input_tokens=inp, output_tokens=out),
        )


# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------

@pytest.fixture
def rubric():
    return EvaluationRubric(
        name="audit_discovery_quality",
        criteria=("io_contract_compliance", "evidence_fidelity"),
    )


@pytest.fixture
def tmp_usage_log(tmp_path):
    return tmp_path / "usage.jsonl"


@pytest.fixture
def config_small_budget(tmp_usage_log):
    return JudgeConfig(
        judge=JudgeSection(
            default_model="muse-spark-open-1026",
            max_cost_usd=5.0,
            timeout_s=60.0,
            usage_log_path=str(tmp_usage_log),
        ),
        providers={},
        models={
            "muse-spark-open-1026": ModelInventoryEntry(
                input_per_1m=1.0, output_per_1m=2.0
            ),
        },
    )


# ---------------------------------------------------------------------
# single()
# ---------------------------------------------------------------------

class TestLLMJudgeSingle:
    def test_single_returns_structured_result(self, config_small_budget, rubric):
        payload = {
            "verdict": "pass",
            "critical_failure": False,
            "criteria": [
                {"criterion": "io_contract_compliance", "score": 9, "notes": ""},
                {"criterion": "evidence_fidelity", "score": 8, "notes": ""},
            ],
            "findings": [],
        }
        adapter = ScriptedJudgeAdapter(
            [(json.dumps(payload), 100, 50)]
        )
        judge = LLMJudge(
            adapter=adapter, config=config_small_budget, rubric=rubric
        )
        result = judge.single({"any": "candidate"})
        assert isinstance(result, SingleEvaluationResult)
        assert result.verdict == "pass"
        assert result.critical_failure is False
        assert [c.score for c in result.criteria] == [9, 8]
        # Cost: 100 input @ $1/1M + 50 output @ $2/1M = 0.0001 + 0.0001 = $0.0002
        assert abs(judge.spent_usd - 0.0002) < 1e-9

    def test_single_refuses_adapter_without_structured_outputs(
        self, config_small_budget, rubric
    ):
        adapter = ScriptedJudgeAdapter([], structured_outputs=False)
        with pytest.raises(UnsupportedCapabilityError):
            LLMJudge(adapter=adapter, config=config_small_budget, rubric=rubric)

    def test_single_refuses_non_json_content(self, config_small_budget, rubric):
        adapter = ScriptedJudgeAdapter(
            [("not-a-json-string", 10, 10)]
        )
        judge = LLMJudge(
            adapter=adapter, config=config_small_budget, rubric=rubric
        )
        with pytest.raises(ValueError, match="judge_response_not_json"):
            judge.single({"any": "candidate"})

    def test_single_refuses_schema_violation(self, config_small_budget, rubric):
        # Missing 'criteria' key — Pydantic strict validation refuses.
        payload = {"verdict": "pass", "critical_failure": False}
        adapter = ScriptedJudgeAdapter([(json.dumps(payload), 10, 10)])
        judge = LLMJudge(
            adapter=adapter, config=config_small_budget, rubric=rubric
        )
        with pytest.raises(Exception):  # noqa: B017 - pydantic/jsonschema combo
            judge.single({"c": 1})

    def test_critical_failure_true_forbids_pass_verdict(
        self, config_small_budget, rubric
    ):
        payload = {
            "verdict": "pass",
            "critical_failure": True,
            "criteria": [
                {"criterion": "io_contract_compliance", "score": 9, "notes": ""},
                {"criterion": "evidence_fidelity", "score": 9, "notes": ""},
            ],
        }
        adapter = ScriptedJudgeAdapter([(json.dumps(payload), 10, 10)])
        judge = LLMJudge(
            adapter=adapter, config=config_small_budget, rubric=rubric
        )
        with pytest.raises(Exception):  # noqa: B017 - pydantic/jsonschema combo
            judge.single({"c": 1})


# ---------------------------------------------------------------------
# pairwise()
# ---------------------------------------------------------------------

class TestLLMJudgePairwise:
    def _payload(self, verdict):
        return {
            "verdict": verdict,
            "critical_failure_a": False,
            "critical_failure_b": False,
            "criteria_a": [
                {"criterion": "io_contract_compliance", "score": 8, "notes": ""},
                {"criterion": "evidence_fidelity", "score": 8, "notes": ""},
            ],
            "criteria_b": [
                {"criterion": "io_contract_compliance", "score": 7, "notes": ""},
                {"criterion": "evidence_fidelity", "score": 7, "notes": ""},
            ],
        }

    def test_pairwise_runs_adapter_twice_with_reversed_order(
        self, config_small_budget, rubric
    ):
        # First call: a wins. Second call (reversed order a<->b):
        # should return 'b' (because the model's "a" is now the
        # original candidate_b, so winning candidate_a appears as "b").
        adapter = ScriptedJudgeAdapter(
            [
                (json.dumps(self._payload("a")), 100, 50),
                (json.dumps(self._payload("b")), 100, 50),
            ]
        )
        judge = LLMJudge(
            adapter=adapter, config=config_small_budget, rubric=rubric
        )
        result = judge.pairwise({"id": "A"}, {"id": "B"})
        assert isinstance(result, PairwiseEvaluationResult)
        assert result.verdict == "a"
        assert result.order_bias_detected is False
        # Adapter saw exactly two requests.
        assert len(adapter.requests) == 2

    def test_pairwise_disagreement_forces_inconclusive(
        self, config_small_budget, rubric
    ):
        # First call: a wins; reversed call also says "a" — which maps
        # to the original "b" winning. Disagreement.
        adapter = ScriptedJudgeAdapter(
            [
                (json.dumps(self._payload("a")), 100, 50),
                (json.dumps(self._payload("a")), 100, 50),
            ]
        )
        judge = LLMJudge(
            adapter=adapter, config=config_small_budget, rubric=rubric
        )
        result = judge.pairwise({"id": "A"}, {"id": "B"})
        assert result.verdict == "inconclusive"
        assert result.order_bias_detected is True

    def test_pairwise_tie_or_inconclusive_preserved(
        self, config_small_budget, rubric
    ):
        adapter = ScriptedJudgeAdapter(
            [
                (json.dumps(self._payload("tie")), 100, 50),
                (json.dumps(self._payload("tie")), 100, 50),
            ]
        )
        judge = LLMJudge(
            adapter=adapter, config=config_small_budget, rubric=rubric
        )
        result = judge.pairwise({"id": "A"}, {"id": "B"})
        assert result.verdict == "tie"
        assert result.order_bias_detected is False


# ---------------------------------------------------------------------
# reference_guided()
# ---------------------------------------------------------------------

class TestLLMJudgeReferenceGuided:
    def test_reference_guided_runs_adapter_once(
        self, config_small_budget, rubric
    ):
        payload = {
            "verdict": "fail",
            "critical_failure": False,
            "criteria": [
                {"criterion": "io_contract_compliance", "score": 3, "notes": ""},
                {"criterion": "evidence_fidelity", "score": 5, "notes": ""},
            ],
        }
        adapter = ScriptedJudgeAdapter(
            [(json.dumps(payload), 100, 50)]
        )
        judge = LLMJudge(
            adapter=adapter, config=config_small_budget, rubric=rubric
        )
        candidate = {"answer": "cand"}
        reference = {"answer": "ref"}
        result = judge.reference_guided(candidate, reference)
        assert result.verdict == "fail"
        assert len(adapter.requests) == 1

    def test_reference_guided_refuses_candidate_is_reference(
        self, config_small_budget, rubric
    ):
        adapter = ScriptedJudgeAdapter([])
        judge = LLMJudge(
            adapter=adapter, config=config_small_budget, rubric=rubric
        )
        shared = {"answer": "x"}
        with pytest.raises(ValueError, match="reference_guided_identity"):
            judge.reference_guided(shared, shared)


# ---------------------------------------------------------------------
# Budget enforcement
# ---------------------------------------------------------------------

class TestBudgetAndUsageLog:
    def test_running_total_tracked_across_calls(self, config_small_budget, rubric):
        payload = {
            "verdict": "pass",
            "critical_failure": False,
            "criteria": [
                {"criterion": "io_contract_compliance", "score": 9, "notes": ""},
                {"criterion": "evidence_fidelity", "score": 9, "notes": ""},
            ],
        }
        adapter = ScriptedJudgeAdapter(
            [
                (json.dumps(payload), 1000, 500),
                (json.dumps(payload), 2000, 1000),
            ]
        )
        judge = LLMJudge(
            adapter=adapter, config=config_small_budget, rubric=rubric
        )
        judge.single({"c": 1})
        # 1000 @ $1/1M + 500 @ $2/1M = 0.001 + 0.001 = $0.002
        assert abs(judge.spent_usd - 0.002) < 1e-9
        judge.single({"c": 2})
        # +2000@$1 + 1000@$2 = +0.002 + 0.002 = +0.004 -> total 0.006
        assert abs(judge.spent_usd - 0.006) < 1e-9

    def test_budget_exceeded_refuses_further_calls(self, tmp_path, rubric):
        config = JudgeConfig(
            judge=JudgeSection(
                default_model="muse-spark-open-1026",
                max_cost_usd=0.001,  # very tight
                timeout_s=60.0,
                usage_log_path=str(tmp_path / "u.jsonl"),
            ),
            providers={},
            models={
                "muse-spark-open-1026": ModelInventoryEntry(
                    input_per_1m=1.0, output_per_1m=2.0
                ),
            },
        )
        payload = {
            "verdict": "pass",
            "critical_failure": False,
            "criteria": [
                {"criterion": "io_contract_compliance", "score": 9, "notes": ""},
                {"criterion": "evidence_fidelity", "score": 9, "notes": ""},
            ],
        }
        # First call: 2000 input + 1000 output = $0.002 + $0.002 = $0.004 (way over)
        adapter = ScriptedJudgeAdapter(
            [
                (json.dumps(payload), 2000, 1000),
                (json.dumps(payload), 10, 10),  # must never be made
            ]
        )
        judge = LLMJudge(adapter=adapter, config=config, rubric=rubric)
        with pytest.raises(BudgetExceeded):
            judge.single({"c": 1})
        # Second call refused up-front — adapter is not touched again.
        with pytest.raises(BudgetExceeded):
            judge.single({"c": 2})
        assert len(adapter.requests) == 1

    def test_usage_log_lines_appended(self, config_small_budget, rubric, tmp_usage_log):
        payload = {
            "verdict": "pass",
            "critical_failure": False,
            "criteria": [
                {"criterion": "io_contract_compliance", "score": 9, "notes": ""},
                {"criterion": "evidence_fidelity", "score": 9, "notes": ""},
            ],
        }
        adapter = ScriptedJudgeAdapter(
            [
                (json.dumps(payload), 1000, 500),
                (json.dumps(payload), 1000, 500),
            ]
        )
        judge = LLMJudge(
            adapter=adapter, config=config_small_budget, rubric=rubric
        )
        judge.single({"c": 1})
        judge.single({"c": 2})
        lines = tmp_usage_log.read_text().strip().splitlines()
        assert len(lines) == 2
        rec = json.loads(lines[0])
        # Prompt / candidate content MUST NOT appear in the usage log.
        assert "candidate" not in json.dumps(rec).lower()
        # Required accounting keys.
        for key in (
            "at",
            "mode",
            "model",
            "rubric",
            "input_tokens",
            "output_tokens",
            "cost_usd",
            "running_total_usd",
        ):
            assert key in rec, f"missing {key!r}"
        # Running totals ascend.
        rec2 = json.loads(lines[1])
        assert rec2["running_total_usd"] > rec["running_total_usd"]


# ---------------------------------------------------------------------
# Unknown-model refusal (loud, not a silent fallback)
# ---------------------------------------------------------------------

class TestUnknownModelRefusal:
    def test_unknown_model_at_construction(self, config_small_budget, rubric):
        adapter = ScriptedJudgeAdapter([])
        with pytest.raises(ValueError, match="unknown_judge_model"):
            LLMJudge(
                adapter=adapter,
                config=config_small_budget,
                rubric=rubric,
                model="made-up-model-xyz",
            )



class TestBudgetAdmission:
    """R3 reviewer round-5: pre-call budget admission.

    ``would_admit`` is advisory — the enforcement path still raises
    BudgetExceeded on refusal — but it lets callers decide whether to
    even dispatch a call when they know approximately how expensive
    it will be. Prevents a 50 000-token response from blowing a tight
    cap in a single shot.
    """

    def _make(self, max_cost_usd, rubric):
        cfg = JudgeConfig(
            judge=JudgeSection(
                default_model="muse-spark-open-1026",
                max_cost_usd=max_cost_usd,
                timeout_s=60.0,
                usage_log_path="/tmp/u.jsonl",
            ),
            providers={},
            models={
                "muse-spark-open-1026": ModelInventoryEntry(
                    input_per_1m=1.0, output_per_1m=2.0
                ),
            },
        )
        adapter = ScriptedJudgeAdapter([])
        judge = LLMJudge(adapter=adapter, config=cfg, rubric=rubric)
        return judge

    def test_would_admit_true_when_projection_fits(self, rubric):
        judge = self._make(max_cost_usd=1.0, rubric=rubric)
        # 1000 output tokens @ $2/1M = $0.002 << $1 cap
        assert judge.would_admit(estimated_output_tokens=1000) is True

    def test_would_admit_false_when_projection_exceeds(self, rubric):
        judge = self._make(max_cost_usd=0.001, rubric=rubric)
        # 1_000_000 output tokens @ $2/1M = $2 >> $0.001 cap
        assert judge.would_admit(estimated_output_tokens=1_000_000) is False

    def test_would_admit_accounts_input_tokens(self, rubric):
        judge = self._make(max_cost_usd=0.0025, rubric=rubric)
        # 500 input @ $1/1M + 1000 output @ $2/1M = $0.0005 + $0.002 = $0.0025 (equal)
        assert judge.would_admit(
            estimated_output_tokens=1000, estimated_input_tokens=500
        ) is True
        # One extra token tips it over.
        assert judge.would_admit(
            estimated_output_tokens=1000, estimated_input_tokens=501
        ) is False

    def test_would_admit_rejects_when_already_overspent(self, rubric):
        judge = self._make(max_cost_usd=0.001, rubric=rubric)
        # Simulate prior overspend.
        judge._spent_usd = 0.001
        assert judge.would_admit(estimated_output_tokens=1) is False
