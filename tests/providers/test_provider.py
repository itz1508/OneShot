"""Test provider config loading and capability resolution."""

from pathlib import Path

import pytest

from agent.contracts.provider import ProviderConfig, ProviderProtocol
from agent.runtime.provider_config import (
    ProviderConfigurationError,
    load_provider_config,
    resolve_api_key,
    resolve_base_url,
    resolve_model,
)


def test_load_provider_config():
    config = load_provider_config(Path(".agents/providers/meta.yaml"))
    assert config.provider_id == "meta"
    assert config.protocol is ProviderProtocol.OPENAI_COMPATIBLE


def test_resolve_api_key_missing():
    config = ProviderConfig(
        provider_id="test",
        api_key_env="NONEXISTENT_KEY_12345",
        sdk="openai",
        model="test-model",
        capabilities={},
    )
    with pytest.raises(ProviderConfigurationError):
        resolve_api_key(config)


def test_resolve_model_from_config():
    config = ProviderConfig(
        provider_id="test",
        api_key_env="KEY",
        sdk="openai",
        model="direct-model",
        capabilities={},
    )
    assert resolve_model(config) == "direct-model"


def test_resolve_base_url_none():
    config = ProviderConfig(
        provider_id="test",
        api_key_env="KEY",
        sdk="openai",
        model="m",
        capabilities={},
    )
    assert resolve_base_url(config) is None
