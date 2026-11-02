"""Judge config loader tests.

Reuses the existing Pydantic-strict pattern — no new fixture files.
Tests cover: missing file, malformed TOML, happy path, each validation
rule, env-var resolution, and the per-model cost helper.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.prompt_authoring.config import (
    DEFAULT_USAGE_LOG_PATH,
    JudgeConfig,
    JudgeConfigError,
    JudgeSection,
    ModelInventoryEntry,
    load_judge_config,
)

HAPPY_CONFIG = """\
[judge]
default_model = "muse-spark-open-1026"
max_cost_usd = 5.0
timeout_s = 60.0
usage_log_path = "/work/openai-usage.jsonl"

[providers.baseten]
base_url = "https://inference.baseten.co"
api_key_file = "/files/ppf.XYZ"

[models.muse-spark-open-1026]
input_per_1m = 1.0
output_per_1m = 2.0
"""


def _write_config(tmp_path: Path, text: str = HAPPY_CONFIG) -> Path:
    p = tmp_path / "config.toml"
    p.write_text(text, encoding="utf-8")
    return p


class TestLoader:
    def test_happy_path(self, tmp_path):
        path = _write_config(tmp_path)
        cfg = load_judge_config(path)
        assert isinstance(cfg, JudgeConfig)
        assert cfg.judge.default_model == "muse-spark-open-1026"
        assert cfg.judge.max_cost_usd == 5.0
        assert cfg.providers["baseten"].base_url == "https://inference.baseten.co"
        assert cfg.providers["baseten"].api_key_file == "/files/ppf.XYZ"
        assert cfg.models["muse-spark-open-1026"].input_per_1m == 1.0

    def test_env_var_resolution(self, tmp_path, monkeypatch):
        path = _write_config(tmp_path)
        monkeypatch.setenv("ONESHOT_JUDGE_CONFIG", str(path))
        cfg = load_judge_config()  # no explicit path
        assert cfg.judge.default_model == "muse-spark-open-1026"

    def test_missing_file(self, tmp_path):
        with pytest.raises(JudgeConfigError, match="judge_config_missing"):
            load_judge_config(tmp_path / "does-not-exist.toml")

    def test_malformed_toml(self, tmp_path):
        p = tmp_path / "bad.toml"
        p.write_text("this is = not = valid [[[", encoding="utf-8")
        with pytest.raises(JudgeConfigError):
            load_judge_config(p)

    def test_unknown_top_level_key_refused(self, tmp_path):
        bad = HAPPY_CONFIG + "\n[extraneous]\nvalue = 1\n"
        p = _write_config(tmp_path, bad)
        with pytest.raises(JudgeConfigError):
            load_judge_config(p)


class TestValidation:
    def test_default_model_must_be_in_inventory(self, tmp_path):
        bad = HAPPY_CONFIG.replace(
            'default_model = "muse-spark-open-1026"',
            'default_model = "no-such-model"',
        )
        p = _write_config(tmp_path, bad)
        with pytest.raises(JudgeConfigError):
            load_judge_config(p)

    def test_max_cost_usd_must_be_positive(self, tmp_path):
        bad = HAPPY_CONFIG.replace("max_cost_usd = 5.0", "max_cost_usd = 0.0")
        p = _write_config(tmp_path, bad)
        with pytest.raises(JudgeConfigError):
            load_judge_config(p)

    def test_input_per_1m_must_be_positive(self, tmp_path):
        bad = HAPPY_CONFIG.replace("input_per_1m = 1.0", "input_per_1m = 0.0")
        p = _write_config(tmp_path, bad)
        with pytest.raises(JudgeConfigError):
            load_judge_config(p)

    def test_provider_entry_requires_a_credential_source(self, tmp_path):
        bad = HAPPY_CONFIG.replace(
            'api_key_file = "/files/ppf.XYZ"',
            "",
        )
        p = _write_config(tmp_path, bad)
        with pytest.raises(JudgeConfigError):
            load_judge_config(p)

    def test_provider_entry_accepts_env_source(self, tmp_path):
        swapped = HAPPY_CONFIG.replace(
            'api_key_file = "/files/ppf.XYZ"',
            'api_key_env = "BASETEN_API_KEY"',
        )
        p = _write_config(tmp_path, swapped)
        cfg = load_judge_config(p)
        assert cfg.providers["baseten"].api_key_env == "BASETEN_API_KEY"
        assert cfg.providers["baseten"].api_key_file is None


class TestCostHelper:
    def test_model_cost_usd_matches_per_1m_rate(self):
        cfg = JudgeConfig(
            judge=JudgeSection(
                default_model="muse-spark-open-1026",
                max_cost_usd=5.0,
                timeout_s=60.0,
                usage_log_path=DEFAULT_USAGE_LOG_PATH,
            ),
            providers={},
            models={
                "muse-spark-open-1026": ModelInventoryEntry(
                    input_per_1m=1.0, output_per_1m=2.0
                ),
            },
        )
        # 1_000_000 input @ $1 + 500_000 output @ $2 = $1 + $1 = $2
        assert cfg.model_cost_usd(
            "muse-spark-open-1026", 1_000_000, 500_000
        ) == pytest.approx(2.0, rel=1e-9)

    def test_unknown_model_raises_key_error(self):
        cfg = JudgeConfig(
            judge=JudgeSection(
                default_model="muse-spark-open-1026",
                max_cost_usd=5.0,
                timeout_s=60.0,
                usage_log_path=DEFAULT_USAGE_LOG_PATH,
            ),
            providers={},
            models={
                "muse-spark-open-1026": ModelInventoryEntry(
                    input_per_1m=1.0, output_per_1m=2.0
                ),
            },
        )
        with pytest.raises(KeyError):
            cfg.model_cost_usd("made-up", 10, 10)
