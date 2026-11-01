"""Red-first tests for the OneShot provider abstraction.

Covers:

* unified types round-trip (ProviderConfig, UnifiedRequest, UnifiedResponse,
  ProviderCapabilities);
* ProviderRegistry create + unknown provider error;
* EchoAdapter determinism, capability declaration, explicit capability
  refusal on unsupported features;
* lazy vendor stubs (openai / anthropic / openai_compatible) import
  without the SDK installed and raise typed error on `.generate()`;
* OneShotController opt-in provider wiring (`provider_config` kwarg
  installs the client; default stays None; `model_call` without a
  config raises RuntimeError).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.providers import (
    EchoAdapter,
    ProviderAdapter,
    ProviderCapabilities,
    ProviderConfig,
    ProviderRegistry,
    UnifiedRequest,
    UnifiedResponse,
    UnsupportedCapabilityError,
    UnsupportedProviderError,
)
from agent.providers.types import Message, Usage

# ---------------------------------------------------------------------------
# Unified types round-trip
# ---------------------------------------------------------------------------


class TestUnifiedTypes:
    def test_provider_config_requires_provider_and_model(self):
        cfg = ProviderConfig(provider="echo", model="echo-1")
        assert cfg.provider == "echo"
        assert cfg.model == "echo-1"
        assert cfg.endpoint is None
        assert cfg.credential_ref is None

    def test_provider_config_rejects_empty_provider(self):
        with pytest.raises(ValidationError):
            ProviderConfig(provider="", model="x")

    def test_provider_config_three_axes_are_independent(self):
        """Provider != model != endpoint. The spec explicitly notes
        that one model can run through many endpoints."""
        cfg = ProviderConfig(
            provider="openai_compatible",
            model="meta-llama/Meta-Llama-3-70B-Instruct",
            endpoint="https://api.together.xyz/v1",
            credential_ref="TOGETHER_API_KEY",
        )
        assert cfg.provider == "openai_compatible"
        assert cfg.endpoint.endswith("/v1")
        # The three fields are stored separately — not merged into one URL.
        dumped = cfg.model_dump()
        assert set(dumped) == {
            "provider", "model", "endpoint", "credential_ref", "options",
        }

    def test_unified_request_rejects_empty_messages(self):
        with pytest.raises(ValidationError):
            UnifiedRequest(messages=[])

    def test_unified_request_round_trip(self):
        req = UnifiedRequest(
            messages=[Message(role="user", content="hi")],
            temperature=0.5,
            max_tokens=256,
        )
        rebuilt = UnifiedRequest.model_validate(req.model_dump())
        assert rebuilt.messages[0].content == "hi"
        assert rebuilt.temperature == 0.5

    def test_unified_response_defaults(self):
        resp = UnifiedResponse()
        assert resp.content == ""
        assert resp.finish_reason == "stop"
        assert resp.usage.model_dump() == Usage().model_dump()


# ---------------------------------------------------------------------------
# ProviderRegistry
# ---------------------------------------------------------------------------


class TestProviderRegistry:
    def test_defaults_installed_lazily(self):
        known = ProviderRegistry.known_providers()
        assert "echo" in known
        # The three documented vendors register themselves as lazy stubs.
        for key in ("openai", "anthropic", "openai_compatible"):
            assert key in known, f"{key!r} missing from registry"

    def test_create_echo(self):
        cfg = ProviderConfig(provider="echo", model="echo-1")
        adapter = ProviderRegistry.create(cfg)
        assert isinstance(adapter, EchoAdapter)
        assert isinstance(adapter, ProviderAdapter)

    def test_create_unknown_provider_raises(self):
        with pytest.raises(UnsupportedProviderError) as ctx:
            ProviderRegistry.create(
                ProviderConfig(provider="not_a_real_vendor", model="x")
            )
        msg = str(ctx.value)
        assert "not_a_real_vendor" in msg
        # The error should hint at how to add one.
        assert "Known providers" in msg

    def test_register_rejects_different_factory_shadowing(self):
        # Attempt to re-register 'echo' with a different factory.
        class _Fake:
            def __init__(self, cfg):
                pass

            def capabilities(self):
                return ProviderCapabilities()

            def generate(self, req):
                return UnifiedResponse()

        with pytest.raises(ValueError):
            ProviderRegistry.register("echo", _Fake)

    def test_register_same_factory_is_idempotent(self):
        # Re-registering the same class under the same key is a no-op.
        ProviderRegistry.register("echo", EchoAdapter)
        # It still resolves.
        adapter = ProviderRegistry.create(
            ProviderConfig(provider="echo", model="x")
        )
        assert isinstance(adapter, EchoAdapter)


# ---------------------------------------------------------------------------
# EchoAdapter
# ---------------------------------------------------------------------------


class TestEchoAdapter:
    def _adapter(self):
        return ProviderRegistry.create(
            ProviderConfig(provider="echo", model="echo-1")
        )

    def test_capabilities_declared_explicitly(self):
        caps = self._adapter().capabilities()
        assert caps.structured_outputs is True
        assert caps.streaming is False
        assert caps.batch is False
        assert caps.prompt_caching is False
        assert caps.strict_tool_schemas is False

    def test_generate_is_deterministic(self):
        ad = self._adapter()
        req = UnifiedRequest(messages=[Message(role="user", content="hi")])
        a = ad.generate(req)
        b = ad.generate(req)
        assert a.content == b.content
        assert a.content.startswith("[echo:echo-1] ")
        # The content is a sha-256 digest; 64 hex chars.
        digest = a.content.split("] ", 1)[1]
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_generate_streaming_request_refused_explicitly(self):
        ad = self._adapter()
        req = UnifiedRequest(
            messages=[Message(role="user", content="hi")], stream=True
        )
        with pytest.raises(UnsupportedCapabilityError) as ctx:
            ad.generate(req)
        assert ctx.value.capability == "streaming"
        assert ctx.value.provider == "echo"

    def test_optional_capabilities_raise_capability_error(self):
        ad = self._adapter()
        req = UnifiedRequest(messages=[Message(role="user", content="hi")])
        with pytest.raises(UnsupportedCapabilityError):
            ad.stream(req)
        with pytest.raises(UnsupportedCapabilityError):
            ad.batch([req])


# ---------------------------------------------------------------------------
# Lazy vendor stubs — import without SDK, typed error on generate
# ---------------------------------------------------------------------------


class TestLazyVendorStubs:
    def test_openai_stub_imports_without_sdk(self):
        import importlib

        mod = importlib.import_module("agent.providers.openai_adapter")
        assert mod.OpenAIAdapter is not None

    def test_openai_stub_declares_full_capability_matrix(self):
        from agent.providers.openai_adapter import OpenAIAdapter

        caps = OpenAIAdapter(
            ProviderConfig(provider="openai", model="gpt-4o-mini")
        ).capabilities()
        assert caps.structured_outputs is True
        assert caps.streaming is True
        assert caps.batch is True
        assert caps.prompt_caching is True
        assert caps.strict_tool_schemas is True

    def test_openai_stub_generate_raises_install_hint(self):
        from agent.providers.openai_adapter import OpenAIAdapter

        ad = OpenAIAdapter(
            ProviderConfig(provider="openai", model="gpt-4o-mini")
        )
        req = UnifiedRequest(
            messages=[Message(role="user", content="hi")]
        )
        with pytest.raises((UnsupportedProviderError, NotImplementedError)) as ctx:
            ad.generate(req)
        # Either the SDK is missing (install hint) or it is installed but
        # the live translation layer is still a follow-up (NotImplemented).
        text = str(ctx.value)
        assert "openai" in text.lower()

    def test_anthropic_stub_declares_capabilities(self):
        from agent.providers.anthropic_adapter import AnthropicAdapter

        caps = AnthropicAdapter(
            ProviderConfig(provider="anthropic", model="claude-sonnet-4-20250514")
        ).capabilities()
        assert caps.streaming is True
        assert caps.batch is True
        assert caps.prompt_caching is True
        assert caps.strict_tool_schemas is True
        # Anthropic's native API returns free-form content; structured
        # outputs are an opt-in dance, not a declared capability.
        assert caps.structured_outputs is False

    def test_openai_compatible_stub_declares_lcd_capabilities(self):
        from agent.providers.openai_compatible_adapter import (
            OpenAICompatibleAdapter,
        )

        ad = OpenAICompatibleAdapter(
            ProviderConfig(
                provider="openai_compatible",
                model="meta-llama/Meta-Llama-3-70B-Instruct",
                endpoint="https://api.together.xyz/v1",
                credential_ref="TOGETHER_API_KEY",
            )
        )
        caps = ad.capabilities()
        # LCD stub — advertises streaming but NOT structured outputs /
        # batch / prompt caching; a concrete subclass may override.
        assert caps.streaming is True
        assert caps.structured_outputs is False
        assert caps.batch is False


# ---------------------------------------------------------------------------
# OneShotController opt-in provider wiring
# ---------------------------------------------------------------------------


class TestOneShotControllerIntegration:
    def test_default_controller_has_no_client(self):
        from main import OneShotController

        ctrl = OneShotController(storage_path="/tmp/oneshot_provider_test_1.json")
        assert ctrl.client is None
        assert ctrl.provider_config is None

    def test_controller_installs_echo_client_on_demand(self):
        from main import OneShotController

        ctrl = OneShotController(
            storage_path="/tmp/oneshot_provider_test_2.json",
            provider_config=ProviderConfig(provider="echo", model="echo-1"),
        )
        assert ctrl.client is not None
        assert isinstance(ctrl.client, EchoAdapter)
        # And the model_call seam actually routes through it.
        resp = ctrl.model_call(
            UnifiedRequest(messages=[Message(role="user", content="hi")])
        )
        assert resp.content.startswith("[echo:echo-1] ")

    def test_model_call_without_provider_raises(self):
        from main import OneShotController

        ctrl = OneShotController(storage_path="/tmp/oneshot_provider_test_3.json")
        with pytest.raises(RuntimeError) as ctx:
            ctrl.model_call(
                UnifiedRequest(messages=[Message(role="user", content="hi")])
            )
        assert "provider_config" in str(ctx.value)
