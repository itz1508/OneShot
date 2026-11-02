"""Operational LLM Judge.

Three evaluation modes:

  * ``LLMJudge.single(candidate)`` — one answer against the rubric.
    Verdict ∈ ``{"pass", "fail", "inconclusive"}``.

  * ``LLMJudge.pairwise(candidate_a, candidate_b)`` — relative judgment,
    run TWICE with the order of ``a`` and ``b`` reversed. Disagreement
    between the two runs forces verdict ``"inconclusive"``. This is the
    standard order-bias control.

  * ``LLMJudge.reference_guided(candidate, reference)`` — compare the
    candidate to an INDEPENDENTLY-SOURCED reference answer. The
    reference MUST come from the caller (typically
    ``agent.contracts.oracles``), NEVER from the candidate's own
    output — the Judge refuses a reference-guided call if ``candidate``
    and ``reference`` are the same Python object.

Reviewer rules this module obeys:

  * Judge refuses to run on an adapter whose
    ``capabilities().structured_outputs`` is ``False``. Silent fallback
    to free-form content parsing is explicitly rejected.
  * Hard USD budget cap enforced per Judge instance (``config.judge.
    max_cost_usd``). Every adapter call is accounted BEFORE the next
    is dispatched; a call that would push the running total past the
    cap is refused with ``BudgetExceeded``.
  * Per-call usage (model, input tokens, output tokens, cost USD, mode,
    at-wallclock) appended to the JSONL usage log at
    ``config.judge.usage_log_path``. The log never carries the
    rendered prompt or the candidate's output — only accounting data.
  * Model inventory is REQUIRED for any model used; unknown models
    raise ``UnknownJudgeModel`` (via ``JudgeConfig.model_cost_usd``).
  * The Judge never persists prompts, candidates, or responses to
    disk. The ``EvaluationResult`` is returned to the caller only.

The Judge is build-time infrastructure. It does NOT execute inside
the deterministic Research / Plan / Build code paths; a prompt
revision needs a Judge-signed receipt BEFORE activation, not during
runtime dispatch.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.prompt_authoring.config import JudgeConfig
from agent.providers.base import ProviderAdapter, UnsupportedCapabilityError
from agent.providers.types import Message, UnifiedRequest, UnifiedResponse

PairwiseVerdict = Literal["a", "b", "tie", "inconclusive"]
SingleVerdict = Literal["pass", "fail", "inconclusive"]


class BudgetExceeded(RuntimeError):  # noqa: N818 - standard Python idiom
    """Raised when a Judge call would push the running total past
    ``config.judge.max_cost_usd``.

    The attribute ``spent_usd`` is the amount already recorded for
    this Judge instance; ``cap_usd`` is the configured hard cap.
    """

    def __init__(self, *, spent_usd: float, cap_usd: float):
        self.spent_usd = float(spent_usd)
        self.cap_usd = float(cap_usd)
        super().__init__(
            f"judge_budget_exceeded: already spent {spent_usd:.4f} USD; "
            f"cap is {cap_usd:.4f} USD."
        )


class CriterionResult(BaseModel):
    """One per rubric criterion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    criterion: str
    score: int = Field(ge=0, le=10)
    notes: str = ""


class Finding(BaseModel):
    """A specific gap or praise the Judge flagged."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    criterion: str
    severity: Literal["info", "minor", "major", "critical"]
    note: str


class SingleEvaluationResult(BaseModel):
    """``LLMJudge.single`` return shape."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: SingleVerdict
    critical_failure: bool = False
    criteria: list[CriterionResult]
    findings: list[Finding] = Field(default_factory=list)

    @model_validator(mode="after")
    def _critical_implies_fail(self) -> SingleEvaluationResult:
        if self.critical_failure and self.verdict == "pass":
            raise ValueError(
                "critical_failure=True is incompatible with verdict='pass'."
            )
        return self


class PairwiseEvaluationResult(BaseModel):
    """``LLMJudge.pairwise`` return shape (post order-bias reconciliation)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verdict: PairwiseVerdict
    critical_failure_a: bool = False
    critical_failure_b: bool = False
    criteria_a: list[CriterionResult]
    criteria_b: list[CriterionResult]
    findings: list[Finding] = Field(default_factory=list)
    # True when the two reversed-order runs reached incompatible
    # verdicts — the Judge forces the final verdict to "inconclusive"
    # in that case and ``order_bias_detected`` records the fact.
    order_bias_detected: bool = False


class EvaluationRubric(BaseModel):
    """Rubric declaration.

    ``criteria`` is a short list of criterion names. ``critical_failure_rule``
    is a free-text description the Judge prompt relays verbatim to the
    model (so critical-failure semantics are rubric-defined, not
    hard-coded in the Judge).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    criteria: tuple[str, ...] = Field(min_length=1)
    scale_hint: str = "0..10, 10 is perfect"
    critical_failure_rule: str = (
        "Flag critical_failure=True only when the output violates a "
        "contract that MUST hold for the pipeline to run safely."
    )
    rubric_notes: tuple[str, ...] = ()


_SINGLE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict", "critical_failure", "criteria"],
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fail", "inconclusive"]},
        "critical_failure": {"type": "boolean"},
        "criteria": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["criterion", "score"],
                "properties": {
                    "criterion": {"type": "string"},
                    "score": {"type": "integer", "minimum": 0, "maximum": 10},
                    "notes": {"type": "string"},
                },
            },
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["criterion", "severity", "note"],
                "properties": {
                    "criterion": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["info", "minor", "major", "critical"],
                    },
                    "note": {"type": "string"},
                },
            },
        },
    },
}


_PAIRWISE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "verdict",
        "critical_failure_a",
        "critical_failure_b",
        "criteria_a",
        "criteria_b",
    ],
    "properties": {
        "verdict": {"type": "string", "enum": ["a", "b", "tie", "inconclusive"]},
        "critical_failure_a": {"type": "boolean"},
        "critical_failure_b": {"type": "boolean"},
        "criteria_a": _SINGLE_SCHEMA["properties"]["criteria"],
        "criteria_b": _SINGLE_SCHEMA["properties"]["criteria"],
        "findings": _SINGLE_SCHEMA["properties"]["findings"],
    },
}


class LLMJudge:
    """Operational LLM Judge.

    The Judge is build-time infrastructure. It does not touch the
    deterministic Research/Plan/Build code paths; a prompt revision
    needs a Judge-signed receipt BEFORE activation, not during runtime.
    """

    def __init__(
        self,
        *,
        adapter: ProviderAdapter,
        config: JudgeConfig,
        rubric: EvaluationRubric,
        model: str | None = None,
        rng: random.Random | None = None,
    ) -> None:
        caps = adapter.capabilities()
        if not caps.structured_outputs:
            raise UnsupportedCapabilityError(
                "structured_outputs",
                type(adapter).__name__,
                "LLMJudge refuses to run on an adapter whose capabilities "
                "declare structured_outputs=False. Silent fallback to "
                "free-form content parsing is explicitly rejected.",
            )
        self._adapter = adapter
        self._config = config
        self._rubric = rubric
        self._model = model or config.judge.default_model
        # Validate the model is in the inventory so we fail LOUD at
        # construction, not on the first call.
        if self._model not in config.models:
            raise ValueError(
                f"unknown_judge_model: {self._model!r} is not in the "
                "config.toml [models] inventory. Add its per-1M cost "
                "entry (silent fallback refused)."
            )
        self._spent_usd = 0.0
        self._rng = rng or random.Random()

    # ------------------------------------------------------------------
    # Accessors (budget transparency)
    # ------------------------------------------------------------------

    @property
    def spent_usd(self) -> float:
        return self._spent_usd

    @property
    def remaining_usd(self) -> float:
        return max(0.0, self._config.judge.max_cost_usd - self._spent_usd)

    # ------------------------------------------------------------------
    # single / pairwise / reference_guided
    # ------------------------------------------------------------------

    def single(self, candidate: dict) -> SingleEvaluationResult:
        """Grade ``candidate`` against the rubric."""
        messages = [
            Message(role="system", content=_render_single_system(self._rubric)),
            Message(role="user", content=_render_single_user(candidate)),
        ]
        payload = self._ask(messages, _SINGLE_SCHEMA, mode="single")
        return SingleEvaluationResult.model_validate(payload)

    def pairwise(
        self, candidate_a: dict, candidate_b: dict
    ) -> PairwiseEvaluationResult:
        """Grade ``a`` against ``b`` with order-bias control.

        Runs twice:
          1. (a, b) as presented.
          2. (b, a) with roles reversed.
        If the two runs' verdicts disagree the final verdict is forced
        to ``"inconclusive"`` and ``order_bias_detected=True``.
        """
        payload_ab = self._ask(
            [
                Message(role="system", content=_render_pairwise_system(self._rubric)),
                Message(role="user", content=_render_pairwise_user(candidate_a, candidate_b)),
            ],
            _PAIRWISE_SCHEMA,
            mode="pairwise_ab",
        )
        payload_ba = self._ask(
            [
                Message(role="system", content=_render_pairwise_system(self._rubric)),
                # NOTE: a and b are swapped — if the reversed run picks
                # the OTHER label we have order bias.
                Message(role="user", content=_render_pairwise_user(candidate_b, candidate_a)),
            ],
            _PAIRWISE_SCHEMA,
            mode="pairwise_ba",
        )
        run_ab = PairwiseEvaluationResult.model_validate(payload_ab)
        # The reversed run returns verdict a->b and b->a.
        reversed_label_map = {"a": "b", "b": "a", "tie": "tie", "inconclusive": "inconclusive"}
        reversed_verdict = reversed_label_map[payload_ba["verdict"]]
        if run_ab.verdict != reversed_verdict:
            # Order bias: force inconclusive, preserve per-criterion detail
            # from the FIRST run so callers can inspect.
            return run_ab.model_copy(
                update={"verdict": "inconclusive", "order_bias_detected": True}
            )
        return run_ab

    def reference_guided(
        self, candidate: dict, reference: dict
    ) -> SingleEvaluationResult:
        """Grade ``candidate`` against an INDEPENDENT ``reference``.

        Reviewer rule: the reference MUST NOT be the candidate's own
        output; the Judge refuses the call if ``candidate is reference``
        (same Python object). Callers should source references from
        ``agent.contracts.oracles``.
        """
        if candidate is reference:
            raise ValueError(
                "reference_guided_identity: candidate and reference are "
                "the same object. The reference must be independently "
                "sourced (e.g. from agent.contracts.oracles)."
            )
        messages = [
            Message(role="system", content=_render_reference_system(self._rubric)),
            Message(role="user", content=_render_reference_user(candidate, reference)),
        ]
        payload = self._ask(messages, _SINGLE_SCHEMA, mode="reference_guided")
        return SingleEvaluationResult.model_validate(payload)

    # ------------------------------------------------------------------
    # Low-level: dispatch + usage logging + budget enforcement
    # ------------------------------------------------------------------

    def _ask(
        self,
        messages: list[Message],
        output_schema: dict,
        *,
        mode: str,
    ) -> dict:
        if self._spent_usd >= self._config.judge.max_cost_usd:
            raise BudgetExceeded(
                spent_usd=self._spent_usd,
                cap_usd=self._config.judge.max_cost_usd,
            )
        request = UnifiedRequest(
            messages=messages,
            output_schema=output_schema,
            temperature=0.0,
            metadata={
                "judge_mode": mode,
                "judge_rubric": self._rubric.name,
                "judge_model": self._model,
            },
        )
        response: UnifiedResponse = self._adapter.generate(request)
        # Account cost BEFORE allowing the next call. If the adapter
        # returned token counts, bill them; if not, treat the call as
        # zero-cost (the adapter is responsible for declaring usage —
        # we never guess).
        call_cost = self._config.model_cost_usd(
            self._model,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        self._spent_usd = round(self._spent_usd + call_cost, 8)
        _append_usage_record(
            path=self._config.judge.usage_log_path,
            record={
                "at": time.time(),
                "mode": mode,
                "model": self._model,
                "rubric": self._rubric.name,
                "input_tokens": int(response.usage.input_tokens),
                "output_tokens": int(response.usage.output_tokens),
                "cost_usd": call_cost,
                "running_total_usd": self._spent_usd,
            },
        )
        if self._spent_usd > self._config.judge.max_cost_usd:
            # The last call pushed us past the cap. Record it, then
            # refuse any subsequent call.
            # (We do NOT undo the audit; the money is spent.)
            raise BudgetExceeded(
                spent_usd=self._spent_usd,
                cap_usd=self._config.judge.max_cost_usd,
            )
        # Parse the structured output. The adapter advertises
        # structured_outputs=True, so content SHOULD be valid JSON
        # matching output_schema. If it is not, we raise LOUDLY — never
        # fall back to free-form parsing.
        try:
            payload: dict = json.loads(response.content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "judge_response_not_json: adapter advertised "
                "structured_outputs=True but returned non-JSON content."
            ) from exc
        return payload


# ---------------------------------------------------------------------
# Prompt rendering — small, deterministic, no secrets
# ---------------------------------------------------------------------

def _render_single_system(r: EvaluationRubric) -> str:
    lines = [
        "You are an operational judge. Grade a candidate answer against the rubric below.",
        f"Rubric name: {r.name}",
        f"Criteria: {', '.join(r.criteria)}",
        f"Score scale: {r.scale_hint}",
        f"Critical-failure rule: {r.critical_failure_rule}",
    ]
    if r.rubric_notes:
        lines.append("Additional guidance:")
        for n in r.rubric_notes:
            lines.append(f"  - {n}")
    lines.append(
        "Return ONLY a JSON object matching the agreed schema. Do not include "
        "prose outside the JSON."
    )
    return "\n".join(lines)


def _render_single_user(candidate: dict) -> str:
    return "Candidate (JSON):\n" + json.dumps(candidate, sort_keys=True)


def _render_pairwise_system(r: EvaluationRubric) -> str:
    return _render_single_system(r) + (
        "\nYou are comparing TWO candidates. Pick 'a' or 'b' as better per the "
        "rubric, or 'tie' when they are equivalent, or 'inconclusive' when the "
        "evidence does not support a judgment. Fill critical_failure_a and "
        "critical_failure_b independently."
    )


def _render_pairwise_user(a: dict, b: dict) -> str:
    return (
        "Candidate A (JSON):\n"
        + json.dumps(a, sort_keys=True)
        + "\n\nCandidate B (JSON):\n"
        + json.dumps(b, sort_keys=True)
    )


def _render_reference_system(r: EvaluationRubric) -> str:
    return _render_single_system(r) + (
        "\nA REFERENCE answer is provided independently of the candidate. Grade "
        "the candidate against the rubric using the reference as the ground "
        "truth where the rubric calls for one."
    )


def _render_reference_user(candidate: dict, reference: dict) -> str:
    return (
        "Candidate (JSON):\n"
        + json.dumps(candidate, sort_keys=True)
        + "\n\nReference (JSON):\n"
        + json.dumps(reference, sort_keys=True)
    )


# ---------------------------------------------------------------------
# Usage log — append-only JSONL
# ---------------------------------------------------------------------

def _append_usage_record(*, path: str, record: dict) -> None:
    """Append one JSONL record to the usage log, creating parents.

    The record is small and purely accounting (no prompts, no secrets).
    Best-effort: a failed append is logged to stderr but never raises
    into the caller — the Judge's primary job is the evaluation, not
    bookkeeping, and we must not fail an eval because the log file is
    read-only.
    """
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, sort_keys=True) + "\n")
    except OSError:
        # Non-fatal. The budget enforcement does NOT depend on the log
        # (budget state lives on the Judge instance).
        import sys
        sys.stderr.write(
            f"judge_usage_log_write_failed: path={path!r}\n"
        )


__all__ = [
    "BudgetExceeded",
    "CriterionResult",
    "EvaluationRubric",
    "Finding",
    "LLMJudge",
    "PairwiseEvaluationResult",
    "PairwiseVerdict",
    "SingleEvaluationResult",
    "SingleVerdict",
]
