"""Provider capability tests — PROV01-PROV16."""

import pytest

from agent.runtime.providers.base import (
    CapabilityDescriptor,
    ProviderError,
    ProviderRequest,
    ProviderResult,
    UnsupportedProviderError,
)
from agent.runtime.providers.echo import EchoProvider
from agent.runtime.providers.meta import MetaProvider
from agent.runtime.providers.registry import ProviderRegistry


class TestEchoProvider:
    def test_echo_generates_response(self):
        """PROV01: Echo provider generates deterministic response."""
        provider = EchoProvider()
        request = ProviderRequest(run_id="run-001", prompt="hello")
        result = provider.generate(request)
        assert result.content.startswith("echo:")
        assert result.provider == "echo"

    def test_echo_deterministic(self):
        """PROV02: Same request produces same response."""
        provider = EchoProvider()
        request = ProviderRequest(run_id="run-001", prompt="hello")
        r1 = provider.generate(request)
        r2 = provider.generate(request)
        assert r1.content == r2.content

    def test_echo_capabilities(self):
        """PROV03: Echo capabilities are all false."""
        provider = EchoProvider()
        caps = provider.declared_capabilities()
        assert caps.structured_outputs is False
        assert caps.streaming is False


class TestProviderRegistry:
    def test_echo_registered_by_default(self):
        """PROV04: Echo registered by default."""
        registry = ProviderRegistry()
        assert "echo" in registry.registered_providers

    def test_unknown_provider_rejected(self):
        """PROV05: Unknown provider raises UnsupportedProviderError."""
        registry = ProviderRegistry()
        with pytest.raises(UnsupportedProviderError):
            registry.create("nonexistent")

    def test_shadowing_prevented(self):
        """PROV06: Cannot shadow existing provider."""
        registry = ProviderRegistry()
        with pytest.raises(ProviderError):
            registry.register("echo", EchoProvider)

    def test_generate_via_registry(self):
        """PROV07: Generate through registry."""
        registry = ProviderRegistry()
        request = ProviderRequest(run_id="run-001", prompt="test")
        result = registry.generate("echo", request)
        assert result.content.startswith("echo:")

    def test_default_provider_is_meta(self):
        """PROV08: Echo is a test double; Meta is the runtime default."""
        registry = ProviderRegistry()
        assert registry.default_provider == "meta"


class TestMetaProvider:
    def test_meta_default_config(self):
        """PROV09: Meta provider has correct default config."""
        provider = MetaProvider()
        assert provider.DEFAULT_BASE_URL == "https://api.meta.ai/v1"
        assert provider.DEFAULT_MODEL == "muse-spark-1.3"

    def test_meta_model_can_be_selected_from_profile_environment(self, monkeypatch):
        monkeypatch.setenv("META_MODEL_ID", "another-model")
        monkeypatch.setenv("META_MODEL_BASE_URL", "http://127.0.0.1:9000/v1")
        provider = MetaProvider()
        assert provider._model == "another-model"
        assert provider._base_url == "http://127.0.0.1:9000/v1"

    def test_meta_credential_ref(self):
        """PROV10: Meta provider uses credential_ref, not embedded key."""
        provider = MetaProvider(credential_ref="MY_KEY")
        assert provider._credential_ref == "MY_KEY"

    def test_meta_capabilities(self):
        """PROV11: Meta provider declares capabilities."""
        provider = MetaProvider()
        caps = provider.declared_capabilities()
        assert caps.structured_outputs is True
        assert caps.streaming is True

    def test_meta_without_key_raises(self):
        """PROV12: Meta provider without API key raises."""
        import os

        old = os.environ.pop("MODEL_API_KEY", None)
        try:
            provider = MetaProvider()
            with pytest.raises(ProviderError):
                provider.generate(ProviderRequest(run_id="run-001", prompt="test"))
        finally:
            if old:
                os.environ["MODEL_API_KEY"] = old

    def test_meta_without_sdk_raises(self, monkeypatch):
        """PROV13: Meta provider without openai SDK raises."""
        import sys

        # Simulate missing openai
        monkeypatch.setitem(sys.modules, "openai", None)
        provider = MetaProvider()
        monkeypatch.setenv("MODEL_API_KEY", "test-key")
        with pytest.raises(ProviderError):
            provider.generate(ProviderRequest(run_id="run-001", prompt="test"))


class TestProviderRequestResult:
    def test_request_validation(self):
        """PROV14: Request validation rejects bad input."""
        with pytest.raises(Exception):
            ProviderRequest(run_id="", prompt="test")

    def test_result_defaults(self):
        """PROV15: Result has sensible defaults."""
        result = ProviderResult()
        assert result.finish_reason == "stop"
        assert result.tool_calls == ()

    def test_capability_descriptor_defaults(self):
        """PROV16: Capability descriptor defaults all false."""
        caps = CapabilityDescriptor()
        assert caps.structured_outputs is False
        assert caps.streaming is False
        assert caps.batch is False
