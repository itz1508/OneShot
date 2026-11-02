"""BasetenAdapter unit tests (no live calls).

Exercises the pure plumbing: ProviderConfig acceptance, capability
matrix, credential resolution (file vs env), request translation,
response normalisation, and refusal paths.

The ``openai`` SDK is monkeypatched so these tests run offline. The
live-provider tests live in ``test_judge_live_baseten.py`` and are
gated by ``ONESHOT_LIVE_BASETEN=1``.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.providers.base import (
    UnsupportedCapabilityError,
    UnsupportedProviderError,
)
from agent.providers.baseten_adapter import (
    BASETEN_BASE_URL,
    BasetenAdapter,
)
from agent.providers.types import (
    Message,
    ProviderConfig,
    UnifiedRequest,
)

# ---------------------------------------------------------------------
# Fake openai.OpenAI client — captures the call args and returns a
# minimal object matching the shape the adapter reads.
# ---------------------------------------------------------------------

class _FakeOpenAI:
    last_init: dict = {}
    last_create: dict = {}

    def __init__(self, *, base_url, api_key):
        _FakeOpenAI.last_init = {"base_url": base_url, "api_key": api_key}
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        _FakeOpenAI.last_create = kwargs
        return SimpleNamespace(
            model=kwargs["model"],
            id="live-id-00001",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"verdict":"pass"}'),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=42, completion_tokens=7),
        )


@pytest.fixture
def monkey_openai(monkeypatch):
    """Monkeypatch ``openai.OpenAI`` with the fake client."""
    import importlib
    openai_mod = importlib.import_module("openai")
    monkeypatch.setattr(openai_mod, "OpenAI", _FakeOpenAI, raising=True)
    yield _FakeOpenAI


@pytest.fixture
def key_file(tmp_path):
    p = tmp_path / "baseten.key"
    p.write_text("\n   b10_test-key-xyz   \n", encoding="utf-8")
    return str(p)


class TestConstruction:
    def test_rejects_non_provider_config(self):
        with pytest.raises(TypeError):
            BasetenAdapter({"provider": "baseten"})  # type: ignore[arg-type]

    def test_rejects_wrong_provider_name(self):
        cfg = ProviderConfig(
            provider="openai", model="m", credential_ref="/x"
        )
        with pytest.raises(ValueError, match="must be 'baseten'"):
            BasetenAdapter(cfg)

    def test_default_base_url(self):
        cfg = ProviderConfig(
            provider="baseten", model="m", credential_ref="/x"
        )
        adapter = BasetenAdapter(cfg)
        assert adapter._base_url == BASETEN_BASE_URL

    def test_endpoint_override(self):
        cfg = ProviderConfig(
            provider="baseten",
            model="m",
            credential_ref="/x",
            endpoint="https://custom.example/v1",
        )
        adapter = BasetenAdapter(cfg)
        assert adapter._base_url == "https://custom.example/v1"

    def test_capabilities_declare_structured_outputs(self):
        cfg = ProviderConfig(
            provider="baseten", model="m", credential_ref="/x"
        )
        adapter = BasetenAdapter(cfg)
        caps = adapter.capabilities()
        assert caps.structured_outputs is True
        assert caps.streaming is False
        assert caps.batch is False


class TestCredentialResolution:
    def test_file_path_first_nonblank_line(self, key_file):
        cfg = ProviderConfig(
            provider="baseten", model="m", credential_ref=key_file
        )
        adapter = BasetenAdapter(cfg)
        assert adapter._read_api_key_at_call_time() == "b10_test-key-xyz"

    def test_env_name_fallback(self, monkeypatch):
        monkeypatch.setenv("BASETEN_API_KEY", "env-key-abc")
        cfg = ProviderConfig(
            provider="baseten",
            model="m",
            credential_ref="BASETEN_API_KEY",
        )
        adapter = BasetenAdapter(cfg)
        assert adapter._read_api_key_at_call_time() == "env-key-abc"

    def test_missing_file_returns_empty(self, tmp_path):
        cfg = ProviderConfig(
            provider="baseten",
            model="m",
            credential_ref=str(tmp_path / "nope.key"),
        )
        adapter = BasetenAdapter(cfg)
        assert adapter._read_api_key_at_call_time() == ""

    def test_empty_credential_returns_empty(self):
        cfg = ProviderConfig(
            provider="baseten", model="m", credential_ref=""
        )
        adapter = BasetenAdapter(cfg)
        assert adapter._read_api_key_at_call_time() == ""


class TestGenerate:
    def test_generate_translates_unified_request(
        self, key_file, monkey_openai
    ):
        cfg = ProviderConfig(
            provider="baseten", model="model-a", credential_ref=key_file
        )
        adapter = BasetenAdapter(cfg)
        req = UnifiedRequest(
            messages=[
                Message(role="system", content="Be concise."),
                Message(role="user", content="Hello"),
            ],
            temperature=0.5,
            max_tokens=50,
        )
        resp = adapter.generate(req)
        assert resp.content == '{"verdict":"pass"}'
        assert resp.finish_reason == "stop"
        assert resp.usage.input_tokens == 42
        assert resp.usage.output_tokens == 7
        # Fake OpenAI client saw the right init + call.
        assert monkey_openai.last_init["base_url"] == BASETEN_BASE_URL
        assert monkey_openai.last_init["api_key"] == "b10_test-key-xyz"
        call = monkey_openai.last_create
        assert call["model"] == "model-a"
        assert call["temperature"] == 0.5
        assert call["max_tokens"] == 50
        assert call["messages"] == [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Hello"},
        ]
        assert "response_format" not in call

    def test_generate_honours_output_schema_via_json_object(
        self, key_file, monkey_openai
    ):
        cfg = ProviderConfig(
            provider="baseten", model="model-a", credential_ref=key_file
        )
        adapter = BasetenAdapter(cfg)
        schema = {"type": "object", "required": ["x"]}
        req = UnifiedRequest(
            messages=[Message(role="user", content="hi")],
            output_schema=schema,
        )
        adapter.generate(req)
        call = monkey_openai.last_create
        assert call["response_format"] == {"type": "json_object"}
        # Schema must be mentioned in the final system message.
        schema_sys = call["messages"][-1]
        assert schema_sys["role"] == "system"
        assert '"required":["x"]' in schema_sys["content"]

    def test_generate_uses_metadata_judge_model_over_config(
        self, key_file, monkey_openai
    ):
        cfg = ProviderConfig(
            provider="baseten",
            model="cfg-default",
            credential_ref=key_file,
        )
        adapter = BasetenAdapter(cfg)
        req = UnifiedRequest(
            messages=[Message(role="user", content="hi")],
            metadata={"judge_model": "override-model"},
        )
        adapter.generate(req)
        assert monkey_openai.last_create["model"] == "override-model"

    def test_generate_refuses_stream(self, key_file):
        cfg = ProviderConfig(
            provider="baseten", model="m", credential_ref=key_file
        )
        adapter = BasetenAdapter(cfg)
        req = UnifiedRequest(
            messages=[Message(role="user", content="hi")], stream=True
        )
        with pytest.raises(UnsupportedCapabilityError):
            adapter.generate(req)

    def test_generate_refuses_empty_key(self, tmp_path, monkey_openai):
        # Point at a missing file -> empty key -> UnsupportedProviderError.
        cfg = ProviderConfig(
            provider="baseten",
            model="m",
            credential_ref=str(tmp_path / "nope"),
        )
        adapter = BasetenAdapter(cfg)
        req = UnifiedRequest(messages=[Message(role="user", content="hi")])
        with pytest.raises(UnsupportedProviderError):
            adapter.generate(req)


class TestRegistry:
    def test_adapter_registered_under_key_baseten(self):
        from agent.providers.registry import ProviderRegistry
        cfg = ProviderConfig(
            provider="baseten", model="m", credential_ref="/x"
        )
        inst = ProviderRegistry.create(cfg)
        assert isinstance(inst, BasetenAdapter)
