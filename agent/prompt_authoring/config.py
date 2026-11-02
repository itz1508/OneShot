"""Operational Judge configuration loader.

Loads a TOML file describing:

  * ``[judge]`` — default model, hard budget cap, timeout, usage log path.
  * ``[providers.*]`` — provider-adapter credentials-ref (never the raw
    secret; always a path or env name).
  * ``[models.<name>]`` — per-model cost inventory
    (input/output USD per 1,000,000 tokens).

Reviewer rules this loader obeys:

  * TOML, not JSON (reviewer directive).
  * ``max_cost_usd`` is a HARD cap enforced by the Judge; the loader
    refuses non-positive values.
  * The provider section may name an ``api_key_file`` path, but the
    loader does NOT read the key here. The adapter reads the key at
    call time, dereferences it, and never persists it (reviewer rule
    on Baseten key handling).
  * Model inventory is REQUIRED for any model the Judge may be asked
    to use. ``LLMJudge`` consults this table to compute per-call cost
    and record it to the usage log; a model missing from the inventory
    is a loader error, NOT a silent fallback.
  * The loader is pure. Reading the file multiple times returns
    semantically-equal immutable models.

The loader is used only by the Operational Judge. The deterministic
Research / Plan / Build code paths do NOT depend on it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PositiveFloat, model_validator

try:  # Python 3.11+
    import tomllib as _tomllib  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised only on 3.10
    import tomli as _tomllib  # type: ignore[no-redef]


DEFAULT_USAGE_LOG_PATH = "/work/openai-usage.jsonl"
DEFAULT_CONFIG_FILENAME = "config.toml"


class JudgeConfigError(ValueError):
    """Raised when the Judge config file is missing, malformed, or
    semantically invalid.

    Error messages are intended for operators and do NOT include caller
    secrets — ``api_key_file`` paths are redacted to their basename
    before quoting.
    """


class ModelInventoryEntry(BaseModel):
    """Per-model cost — USD per 1,000,000 tokens, input / output split."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_per_1m: PositiveFloat
    output_per_1m: PositiveFloat


class ProviderConfigEntry(BaseModel):
    """Provider-adapter configuration.

    ``api_key_file`` is a filesystem path that the adapter reads at
    call time. The loader never opens it; it only validates that the
    path is a string. Setting ``api_key_file=None`` is permitted so an
    adapter can obtain its credential from the environment instead.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: str
    api_key_file: str | None = None
    api_key_env: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> ProviderConfigEntry:
        if self.api_key_file is None and self.api_key_env is None:
            raise ValueError(
                "a provider entry must declare EITHER api_key_file (a "
                "filesystem path the adapter reads at call time) OR "
                "api_key_env (an environment variable name). "
                "Declaring neither is refused."
            )
        return self


class JudgeSection(BaseModel):
    """``[judge]`` subsection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    default_model: str
    # Hard upper-bound on the total USD cost of a single judge run
    # (sum of per-call input + output across every retry). The Judge
    # enforces this; exceeding it raises ``BudgetExceeded``.
    max_cost_usd: PositiveFloat = 5.0
    # Wall-clock timeout per adapter call, in seconds.
    timeout_s: PositiveFloat = 60.0
    # Where the Judge appends per-call usage records (JSONL).
    usage_log_path: str = DEFAULT_USAGE_LOG_PATH


class JudgeConfig(BaseModel):
    """Fully-validated, immutable Judge configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    judge: JudgeSection
    providers: dict[str, ProviderConfigEntry] = Field(default_factory=dict)
    # Keyed by model name as the Judge would pass it to the adapter.
    models: dict[str, ModelInventoryEntry] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _default_model_in_inventory(self) -> JudgeConfig:
        if self.judge.default_model not in self.models:
            raise ValueError(
                f"judge.default_model={self.judge.default_model!r} is not "
                f"listed under [models]. Add a per-1M cost entry so the "
                f"Judge can compute per-call cost (silent fallback refused)."
            )
        return self

    def model_cost_usd(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Return the USD cost of a call that consumed the given tokens.

        Raises ``KeyError`` if ``model`` is not in the inventory. The
        caller is expected to catch and surface a loud failure — the
        Judge is forbidden from guessing an unknown model's price.
        """
        entry = self.models[model]  # KeyError propagates
        inp_usd = (input_tokens / 1_000_000.0) * float(entry.input_per_1m)
        out_usd = (output_tokens / 1_000_000.0) * float(entry.output_per_1m)
        return round(inp_usd + out_usd, 8)


def load_judge_config(path: str | Path | None = None) -> JudgeConfig:
    """Load and validate a Judge config file.

    Resolution:
      * explicit ``path`` argument wins;
      * else the ``ONESHOT_JUDGE_CONFIG`` environment variable;
      * else ``./config.toml`` relative to the current working
        directory.

    The loader raises ``JudgeConfigError`` for any failure mode — the
    file missing, malformed TOML, failing Pydantic validation, or
    containing an unknown top-level key. There is NO silent default
    for a missing file; the caller must know where its config lives.
    """
    resolved = _resolve_path(path)
    try:
        raw_bytes = resolved.read_bytes()
    except FileNotFoundError as exc:
        raise JudgeConfigError(
            f"judge_config_missing: no config file at {resolved!s}. "
            "Set ONESHOT_JUDGE_CONFIG or place a config.toml at the "
            "working directory."
        ) from exc
    try:
        raw: dict[str, Any] = _tomllib.loads(raw_bytes.decode("utf-8"))
    except Exception as exc:  # pragma: no cover - rare TOML parse errors
        raise JudgeConfigError(
            f"judge_config_parse_error: {resolved!s} is not valid TOML "
            f"({type(exc).__name__})."
        ) from exc
    try:
        return JudgeConfig.model_validate(raw)
    except Exception as exc:
        raise JudgeConfigError(
            f"judge_config_invalid: {resolved!s} failed schema validation: "
            f"{exc}"
        ) from exc


def _resolve_path(path: str | Path | None) -> Path:
    if path is not None:
        return Path(path)
    env = os.environ.get("ONESHOT_JUDGE_CONFIG")
    if env:
        return Path(env)
    return Path.cwd() / DEFAULT_CONFIG_FILENAME


__all__ = [
    "DEFAULT_USAGE_LOG_PATH",
    "JudgeConfig",
    "JudgeConfigError",
    "JudgeSection",
    "ModelInventoryEntry",
    "ProviderConfigEntry",
    "load_judge_config",
]
