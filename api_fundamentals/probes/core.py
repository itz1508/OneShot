"""Core probe functions for basic capability testing."""

from __future__ import annotations

from agent.runtime.streaming import StreamEventType
from api_fundamentals.models import StructuredProbeResult

TOOL = {
    "name": "add",
    "description": "Add integers",
    "parameters": {
        "type": "object",
        "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
        "required": ["a", "b"],
        "additionalProperties": False,
    },
}


def chat(a: object) -> str:
    """Probe basic chat completion."""
    x = a.chat("Return exactly: provider-ready")
    if "provider-ready" not in str(x).lower():
        raise AssertionError(x)
    return str(x)


def streaming(a: object) -> str:
    """Probe streaming with text deltas and completion."""
    es = list(a.stream("Return three words"))
    x = "".join(e.content or "" for e in es if e.event_type is StreamEventType.TEXT_DELTA)
    if not x or es[-1].event_type is not StreamEventType.COMPLETED:
        raise AssertionError("bad stream")
    return x


def structured_output(a: object) -> object:
    """Probe structured output parsing."""
    return a.structured_output("Return supported structured_output JSON", StructuredProbeResult)


def tool_calling(a: object) -> str:
    """Probe tool calling roundtrip."""
    return a.tool_roundtrip("Use add for 2+3", TOOL, lambda n, v: {"result": v["a"] + v["b"]})
