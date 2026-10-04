"""Load an RSM config file from a TOML path (stdlib `tomllib`)."""

from __future__ import annotations

import tomllib
from pathlib import Path

from .schema import RSMConfig, ConfigValidationError


def load_config(path: str | Path) -> RSMConfig:
    """Read a TOML config, fail closed on any unknown key or type error."""
    p = Path(path)
    if not p.exists():
        raise ConfigValidationError(f"Config file not found: {p}")
    with p.open("rb") as f:
        raw = tomllib.load(f)
    return RSMConfig.validate_dict(raw)
