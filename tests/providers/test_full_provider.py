"""Test full provider probes with mock client."""

from types import SimpleNamespace

from agent.contracts.provider import ProviderConfig, ProviderProtocol
from agent.runtime.providers.openai_compatible import OpenAICompatibleAdapter
from api_fundamentals.models import StructuredProbeResult
from api_fundamentals.probes.all import PROBES


class ChatCompletions:
    def parse(self, **kwargs):
        parsed = StructuredProbeResult(capability="structured_output", supported=True, observation="ok")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])

    def create(self, **kwargs):
        if kwargs.get("stream"):
            return iter(
                [
                    SimpleNamespace(
                        usage=None, choices=[SimpleNamespace(delta=SimpleNamespace(content="three words here"))]
                    ),
                    SimpleNamespace(usage=SimpleNamespace(prompt_tokens=4, completion_tokens=3), choices=[]),
                ]
            )
        if kwargs.get("tools"):
            if any(isinstance(m, dict) and m.get("role") == "tool" for m in kwargs["messages"]):
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="5", tool_calls=None))])
            function = SimpleNamespace(name="add", arguments='{"a":2,"b":3}')
            call = SimpleNamespace(id="call", function=function)
            message = SimpleNamespace(
                content=None,
                tool_calls=[call],
                model_dump=lambda exclude_none=True: {
                    "role": "assistant",
                    "tool_calls": [
                        {"id": "call", "type": "function", "function": {"name": "add", "arguments": '{"a":2,"b":3}'}}
                    ],
                },
            )
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])
        messages = kwargs["messages"]
        content = str(messages[-1]["content"])
        text = "provider-ready"
        if "MARKER" in content:
            text = "ONESHOT-LONG-CONTEXT-MARKER"
        usage = SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=2,
            prompt_tokens_details=SimpleNamespace(cached_tokens=5),
            completion_tokens_details=SimpleNamespace(reasoning_tokens=1),
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text, tool_calls=None))], usage=usage
        )


class Responses:
    def create(self, **kwargs):
        return SimpleNamespace(output=[SimpleNamespace(type="web_search_call")], output_text="official citation")


class Client:
    def __init__(self):
        self.chat = SimpleNamespace(completions=ChatCompletions())
        self.responses = Responses()


def adapter():
    config = ProviderConfig(
        provider_id="test",
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        api_key_env="KEY",
        sdk="openai",
        model="model",
        max_retries=0,
        capabilities={},
        options={"chat": {}, "streaming": {}},
    )
    return OpenAICompatibleAdapter(config, Client())


def test_all_ten_probes_have_implementations():
    expected = {
        "chat",
        "streaming",
        "tool_calling",
        "structured_output",
        "prompt_caching",
        "reasoning",
        "vision",
        "long_context",
        "error_handling",
        "search_grounding",
    }
    assert set(PROBES) == expected


def test_core_remote_probes_with_mock_client():
    a = adapter()
    assert PROBES["chat"](a, {"prompt": "x", "expected_text": "provider-ready"})["observation"]
    assert PROBES["streaming"](a, {"prompt": "x"})["observation"]
    assert (
        PROBES["tool_calling"](
            a, {"prompt": "x", "expected_result": 5, "tool_schema": {"name": "add", "parameters": {}}}
        )["observation"]
        == "5"
    )
    assert "structured_output" in PROBES["structured_output"](a, {"prompt": "x"})["observation"]
    assert (
        PROBES["prompt_caching"](a, {"stable_prefix": "x", "repeat": 2, "first_suffix": "a", "second_suffix": "b"})[
            "cached_tokens"
        ]
        == 5
    )
    assert PROBES["reasoning"](a, {"prompt": "x", "effort": "low"})["reasoning_tokens"] == 1
    assert PROBES["vision"](a, {"prompt": "x", "image_url": "https://example.test/image.jpg"})["observation"]
    assert (
        "MARKER"
        in PROBES["long_context"](a, {"filler": "x", "repeat": 2, "marker": "ONESHOT-LONG-CONTEXT-MARKER"})[
            "observation"
        ]
    )
    assert PROBES["error_handling"](
        a,
        {"expected_sdk_retries": 0, "status_classes": {"400": "deterministic", "429": "transient", "500": "transient"}},
    )["observation"]
    assert PROBES["search_grounding"](a, {"prompt": "x"})["observation"] == "official citation"
