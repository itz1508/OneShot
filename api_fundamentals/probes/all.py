"""All capability probes with token accounting."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.runtime.streaming import StreamEventType
from api_fundamentals.models import StructuredProbeResult

Probe = Callable[[Any, dict[str, Any]], dict[str, Any]]


def _usage(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage", None)
    prompt_details = getattr(usage, "prompt_tokens_details", None) if usage else None
    completion_details = getattr(usage, "completion_tokens_details", None) if usage else None
    input_details = getattr(usage, "input_tokens_details", None) if usage else None
    output_details = getattr(usage, "output_tokens_details", None) if usage else None
    return {
        "input_tokens": getattr(usage, "prompt_tokens", getattr(usage, "input_tokens", None)) if usage else None,
        "output_tokens": (
            getattr(usage, "completion_tokens", getattr(usage, "output_tokens", None)) if usage else None
        ),
        "cached_tokens": getattr(
            prompt_details,
            "cached_tokens",
            getattr(input_details, "cached_tokens", None),
        ),
        "reasoning_tokens": getattr(
            completion_details,
            "reasoning_tokens",
            getattr(output_details, "reasoning_tokens", None),
        ),
    }


def chat(adapter: Any, options: dict[str, Any]) -> dict[str, Any]:
    expected = options["expected_text"]
    response = adapter.chat([{"role": "user", "content": options["prompt"]}])
    text = response.choices[0].message.content or ""
    if expected.lower() not in text.lower():
        raise AssertionError(f"Expected {expected!r}, got {text!r}")
    return {"observation": text, **_usage(response)}


def streaming(adapter: Any, options: dict[str, Any]) -> dict[str, Any]:
    events = list(adapter.stream([{"role": "user", "content": options["prompt"]}]))
    text = "".join(event.content or "" for event in events if event.event_type is StreamEventType.TEXT_DELTA)
    if not text.strip() or events[-1].event_type is not StreamEventType.COMPLETED:
        raise AssertionError("Streaming did not yield text and complete")
    usage = next((event for event in events if event.event_type is StreamEventType.USAGE), None)
    return {
        "observation": text,
        "input_tokens": usage.input_tokens if usage else None,
        "output_tokens": usage.output_tokens if usage else None,
    }


def tool_calling(adapter: Any, options: dict[str, Any]) -> dict[str, Any]:
    schema = options["tool_schema"]

    def execute(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name != schema["name"]:
            raise ValueError(name)
        return {"result": arguments["a"] + arguments["b"]}

    text = adapter.tool_roundtrip(options["prompt"], schema, execute)
    if str(options["expected_result"]) not in text:
        raise AssertionError(f"Tool result absent from {text!r}")
    return {"observation": text}


def structured_output(adapter: Any, options: dict[str, Any]) -> dict[str, Any]:
    result = adapter.structured_output(options["prompt"], StructuredProbeResult)
    if not result.supported:
        raise AssertionError(result)
    return {"observation": result.model_dump_json()}


def prompt_caching(adapter: Any, options: dict[str, Any]) -> dict[str, Any]:
    stable = options["stable_prefix"] * options["repeat"]
    adapter.chat([{"role": "system", "content": stable}, {"role": "user", "content": options["first_suffix"]}])
    second = adapter.chat(
        [{"role": "system", "content": stable}, {"role": "user", "content": options["second_suffix"]}],
    )
    usage = _usage(second)
    if usage["cached_tokens"] is None:
        raise RuntimeError("Provider did not report cached token usage")
    return {"observation": f"cached_tokens={usage['cached_tokens']}", **usage}


def reasoning(adapter: Any, options: dict[str, Any]) -> dict[str, Any]:
    original = dict(adapter.config.options.get("chat", {}))
    adapter.config.options["chat"] = {**original, "reasoning_effort": options["effort"]}
    try:
        response = adapter.chat([{"role": "user", "content": options["prompt"]}])
    finally:
        adapter.config.options["chat"] = original
    usage = _usage(response)
    text = response.choices[0].message.content or ""
    return {"observation": text, **usage}


def vision(adapter: Any, options: dict[str, Any]) -> dict[str, Any]:
    text = adapter.vision(options["prompt"], options["image_url"])
    return {"observation": text}


def long_context(adapter: Any, options: dict[str, Any]) -> dict[str, Any]:
    marker = options["marker"]
    context = (options["filler"] * options["repeat"]) + marker
    response = adapter.chat([{"role": "user", "content": f"{context}\n\nReturn only the marker."}])
    text = response.choices[0].message.content or ""
    if marker not in text:
        raise AssertionError("Long-context marker not recovered")
    return {"observation": text, **_usage(response)}


def error_handling(adapter: Any, options: dict[str, Any]) -> dict[str, Any]:
    status_classes = options["status_classes"]
    for raw_status, expected in status_classes.items():
        status = int(raw_status)
        actual = "transient" if status in {408, 409, 429} or status >= 500 else "deterministic"
        if actual != expected:
            raise AssertionError(f"{status}: expected {expected}, got {actual}")
    if adapter.config.max_retries != options["expected_sdk_retries"]:
        raise AssertionError("Retry ownership mismatch")
    return {"observation": "error classification and retry ownership verified"}


def search_grounding(adapter: Any, options: dict[str, Any]) -> dict[str, Any]:
    response = adapter.response(options["prompt"], tools=[{"type": "web_search"}])
    output = getattr(response, "output", [])
    searched = any(getattr(item, "type", None) == "web_search_call" for item in output)
    if not searched:
        raise AssertionError("No web_search_call in response")
    return {"observation": getattr(response, "output_text", str(response))}


PROBES: dict[str, Probe] = {
    "chat": chat,
    "streaming": streaming,
    "tool_calling": tool_calling,
    "structured_output": structured_output,
    "prompt_caching": prompt_caching,
    "reasoning": reasoning,
    "vision": vision,
    "long_context": long_context,
    "error_handling": error_handling,
    "search_grounding": search_grounding,
}
