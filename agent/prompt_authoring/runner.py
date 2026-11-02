"""Executable fixture runner — run a candidate prompt against a fixture via a provider.

M3 contract:
  * `run_candidate(prompt, fixture, adapter) -> ObservedOutput` executes the
    candidate prompt against the fixture's input using the supplied adapter
    (any `ProviderAdapter` — real or scripted). The runner synthesises a
    minimal UnifiedRequest, binds the fixture's `input` dict as the user
    message payload, enforces the prompt's `required_capabilities` BEFORE
    the call (fail-closed: `UnsupportedCapabilityError` surfaces to the
    caller), and returns an `ObservedOutput` capturing the generated content,
    tool-call list, usage, and the adapter's provider/model identity.
  * `ObservedOutput` is a Pydantic model with `extra='forbid'`, so downstream
    callers (the behavior-based axes in `evaluator.py`) see a stable shape.
  * The runner itself is deterministic — it does not read the clock,
    randomise, or hit the network beyond what the adapter does. Two
    identical (prompt, fixture, adapter) invocations yield identical
    `UnifiedRequest.model_dump()` payloads, which is what `ScriptedAdapter`
    uses as its lookup key.
"""
from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from agent.prompt_authoring.fixtures import PromptFixture
from agent.prompt_authoring.types import PromptDefinition
from agent.providers.base import (
    ProviderAdapter,
    UnsupportedCapabilityError,
)
from agent.providers.types import Message, UnifiedRequest, UnifiedResponse, Usage


class ObservedOutput(BaseModel):
    """Captured result of running a prompt+fixture through a ProviderAdapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str = Field(default="")
    tool_calls: list[dict] = Field(default_factory=list)
    finish_reason: str = Field(default="stop")
    usage: Usage | None = None
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    # The canonical request_sha256 — the scripted adapter uses this as its lookup key,
    # and the behavior-based axes use it to assert reproducibility.
    request_sha256: str = Field(min_length=1)


def build_request(prompt: PromptDefinition, fixture: PromptFixture) -> UnifiedRequest:
    """Synthesise the UnifiedRequest for a given (prompt, fixture) pair.

    Deterministic: no clock, no random. The adapter sees a stable payload.
    """
    system_text = "\n\n".join(prompt.stable_instructions)
    # The fixture input is a free-form dict declared by the fixture author.
    # We serialise it canonically so the request hash is stable even if dict
    # key order differs across Python versions.
    user_payload = json.dumps(fixture.input, sort_keys=True, separators=(",", ":"))
    return UnifiedRequest(
        messages=[
            Message(role="system", content=system_text),
            Message(role="user", content=user_payload),
        ],
        output_schema=dict(prompt.output_contract),
        strict_tool_schemas=prompt.required_capabilities.strict_tool_schemas,
        prompt_caching=prompt.required_capabilities.prompt_caching,
    )


def _assert_adapter_caps(prompt: PromptDefinition, adapter: ProviderAdapter) -> None:
    """Fail-closed if the adapter does not advertise what the prompt requires."""
    caps = adapter.capabilities()
    required = prompt.required_capabilities
    # Only cross-check the boolean matrix fields the prompt declared True.
    for name in (
        "structured_outputs",
        "streaming",
        "batch",
        "prompt_caching",
        "strict_tool_schemas",
    ):
        if getattr(required, name) and not getattr(caps, name):
            # Importing provider name defensively — adapters set it on their config.
            provider = getattr(getattr(adapter, "_config", None), "provider", "?")
            raise UnsupportedCapabilityError(name, provider)


def run_candidate(
    prompt: PromptDefinition,
    fixture: PromptFixture,
    adapter: ProviderAdapter,
) -> ObservedOutput:
    """Execute a prompt+fixture through an adapter and return the ObservedOutput.

    Pre-flight: `required_capabilities` is checked against `adapter.capabilities()`
    BEFORE issuing the generate() call so a structurally-invalid prompt-adapter
    pair never costs a request.
    """
    _assert_adapter_caps(prompt, adapter)
    request = build_request(prompt, fixture)
    response: UnifiedResponse = adapter.generate(request)
    # Pull provider / model identity from the adapter's config; adapters
    # that stash these differently are responsible for exposing a `raw`
    # dict with keys `provider` and `model`.
    cfg = getattr(adapter, "_config", None)
    provider = getattr(cfg, "provider", "unknown")
    model = getattr(cfg, "model", response.raw.get("model") if response.raw else "unknown")
    request_sha = ""
    if response.raw is not None:
        request_sha = response.raw.get("request_sha256") or ""
    if not request_sha:
        # Compute it ourselves so the field is always populated.
        import hashlib
        canonical = json.dumps(
            request.model_dump(exclude_none=True), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        request_sha = hashlib.sha256(canonical).hexdigest()
    return ObservedOutput(
        content=response.content,
        tool_calls=[tc.model_dump() for tc in (response.tool_calls or [])],
        finish_reason=response.finish_reason or "stop",
        usage=response.usage,
        provider=provider,
        model=str(model),
        request_sha256=request_sha,
    )


__all__ = [
    "ObservedOutput",
    "build_request",
    "run_candidate",
]
