"""Live-provider Judge test — Baseten (OpenAI-compat).

This test is skipped unless ``ONESHOT_LIVE_BASETEN=1`` is set in the
environment, so CI does NOT make live calls (the Baseten key is not
checked into the repo and MUST stay out of CI). The test is run
locally by the agent against the per-thread sandbox before each
commit.

What this test proves
---------------------
1. The ``BasetenAdapter`` can be constructed from a filesystem-path
   ``credential_ref`` and advertise ``structured_outputs=True``.
2. ``LLMJudge`` admits a tiny single-mode call via
   ``would_admit(estimated_output_tokens=...)``.
3. ``LLMJudge.single(...)`` performs ONE real Baseten dispatch,
   returns a well-formed ``SingleEvaluationResult``, and the usage
   log at ``/work/openai-usage.jsonl`` carries exactly one new
   accounting record for this call.
4. The hard $5 USD cap is NOT exceeded — the test runs well under
   a cent even on the most pessimistic published Baseten rate.

Credential handling
-------------------
The key file ``/files/ppf.01a198ef-...`` is passed by path to the
adapter; the adapter reads it inline at ``.generate()`` time and
never persists it. The test asserts the config object does NOT
hold the raw key string.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agent.prompt_authoring.config import (
    JudgeConfig,
    JudgeSection,
    ModelInventoryEntry,
    ProviderConfigEntry,
)
from agent.prompt_authoring.judge import (
    EvaluationRubric,
    LLMJudge,
    SingleEvaluationResult,
)
from agent.providers.baseten_adapter import BasetenAdapter
from agent.providers.types import ProviderConfig

LIVE_ENABLED = os.environ.get("ONESHOT_LIVE_BASETEN") == "1"
BASETEN_KEY_FILE = "/files/ppf.01a198ef-d53a-762c-bd6a-1321789909df"
BASETEN_MODEL = "meta-models/muse-spark-open-1026"


pytestmark = pytest.mark.skipif(
    not LIVE_ENABLED,
    reason=(
        "live-provider test disabled by default — set "
        "ONESHOT_LIVE_BASETEN=1 to opt in; the Baseten key is not "
        "in CI."
    ),
)


@pytest.fixture
def live_judge_config(tmp_path):
    """A JudgeConfig whose [models] inventory covers the live model."""
    return JudgeConfig(
        judge=JudgeSection(
            default_model=BASETEN_MODEL,
            max_cost_usd=5.0,
            timeout_s=120.0,
            usage_log_path=str(tmp_path / "openai-usage.jsonl"),
        ),
        providers={
            "baseten": ProviderConfigEntry(
                base_url="https://inference.baseten.co/v1",
                api_key_file=BASETEN_KEY_FILE,
            ),
        },
        models={
            BASETEN_MODEL: ModelInventoryEntry(
                # Pessimistic published-rate upper bound; actual Baseten
                # price is lower. The admission check uses THIS rate.
                input_per_1m=1.0,
                output_per_1m=2.0,
            ),
        },
    )


def _rubric() -> EvaluationRubric:
    return EvaluationRubric(
        name="live_sanity_rubric",
        criteria=("io_contract_compliance",),
    )


def _adapter() -> BasetenAdapter:
    cfg = ProviderConfig(
        provider="baseten",
        model=BASETEN_MODEL,
        credential_ref=BASETEN_KEY_FILE,
    )
    assert Path(BASETEN_KEY_FILE).exists(), (
        f"Baseten key file missing at {BASETEN_KEY_FILE}"
    )
    adapter = BasetenAdapter(cfg)
    assert adapter.capabilities().structured_outputs is True
    return adapter


class TestLiveBaseten:
    def test_adapter_does_not_cache_key_as_attribute(self):
        """Credential hygiene: the Baseten adapter must NOT store the
        raw key as an instance attribute. Any dir() entry whose string
        value starts with b10_ would be a key leak."""
        adapter = _adapter()
        for name in dir(adapter):
            if name.startswith("_"):
                # Allow private hooks except the config bag; check it
                # does not contain the key either.
                if name == "_config":
                    val = getattr(adapter, name)
                    for attr in ("credential_ref",):
                        v = getattr(val, attr, "")
                        if isinstance(v, str):
                            assert not v.startswith("b10_"), (
                                "credential_ref must be the PATH, not "
                                "the raw key"
                            )
                continue
            value = getattr(adapter, name, "")
            if isinstance(value, str):
                assert not value.startswith("b10_"), (
                    f"attribute {name} leaks a Baseten key"
                )

    def test_live_single_call_returns_wellformed_result(
        self, live_judge_config
    ):
        adapter = _adapter()
        judge = LLMJudge(
            adapter=adapter,
            config=live_judge_config,
            rubric=_rubric(),
        )
        # Pre-call admission MUST hold for a modest-size call.
        assert judge.would_admit(
            estimated_output_tokens=600, estimated_input_tokens=400
        ), "live single call must fit under the $5 cap"
        candidate = {
            "io_contract_compliance": (
                "The output conforms to the schema with every required "
                "field present and values within the declared vocabulary."
            ),
        }
        result = judge.single(candidate)
        assert isinstance(result, SingleEvaluationResult)
        assert result.verdict in ("pass", "fail", "inconclusive")
        assert len(result.criteria) >= 1
        assert judge.spent_usd > 0.0
        assert judge.spent_usd < live_judge_config.judge.max_cost_usd

    def test_live_single_call_writes_usage_log_entry(
        self, live_judge_config
    ):
        adapter = _adapter()
        judge = LLMJudge(
            adapter=adapter,
            config=live_judge_config,
            rubric=_rubric(),
        )
        judge.single(
            {"io_contract_compliance": "schema compliance OK"}
        )
        log_path = Path(live_judge_config.judge.usage_log_path)
        assert log_path.exists(), "usage log file must be created"
        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 1, (
            f"expected one usage line, got {len(lines)}"
        )
        record = json.loads(lines[0])
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
            assert key in record, f"missing key {key!r}"
        assert record["mode"] == "single"
        assert record["model"] == BASETEN_MODEL
        assert record["rubric"] == "live_sanity_rubric"
        assert record["input_tokens"] > 0
        assert record["output_tokens"] > 0
        assert record["cost_usd"] > 0.0
        # No candidate text / rubric prompt in the log.
        serialised = json.dumps(record).lower()
        assert "schema compliance ok" not in serialised
        assert "critical" not in serialised
