"""Provider configuration loading and environment resolution."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from agent.contracts.provider import ProviderConfig


class ProviderConfigurationError(RuntimeError):
    """Raised when provider configuration is incomplete or invalid."""


def load_provider_config(path: Path) -> ProviderConfig:
    """Load a provider configuration YAML file."""
    return ProviderConfig.model_validate(yaml.safe_load(path.read_text()))


def _env(name: str | None) -> str | None:
    return os.getenv(name) if name else None


def resolve_api_key(c: ProviderConfig) -> str:
    """Resolve the API key from the environment."""
    v = _env(c.api_key_env)
    if not v:
        raise ProviderConfigurationError(f"Missing {c.api_key_env}")
    return v


def resolve_model(c: ProviderConfig) -> str:
    """Resolve the model identifier from config or environment."""
    v = _env(c.model_env) or c.model
    if not v:
        raise ProviderConfigurationError(f"Missing {c.model_env}")
    return v


def resolve_base_url(c: ProviderConfig) -> str | None:
    """Resolve the base URL from config or environment."""
    return _env(c.base_url_env) or c.base_url
