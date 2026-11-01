"""Unified provider contract types.

The types in this module are OneShot's view of a model call. They are
intentionally generic: nothing in the shape here commits to OpenAI,
Anthropic, Llama, or any other vendor. Each `ProviderAdapter`
translates between THESE types and its own vendor SDK.

Design pins:

* `ProviderConfig.provider`, `.model`, and `.endpoint` are SEPARATE
  configuration axes. The spec explicitly notes that one model (e.g.
  Meta Llama) can run through several inference services, each with
  different capabilities. Keeping the three axes separate lets a
  caller swap endpoints without rewriting the adapter.
* `ProviderCapabilities` is a boolean matrix returned by every adapter.
  A caller that needs a capability the adapter does not declare MUST
  receive `UnsupportedCapabilityError`, not a silent downgrade.
* The `credential_ref` field names an environment variable the adapter
  reads at `.generate()` time. We never embed secrets in the config
  object; the config can be serialised, logged, and persisted safely.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ProviderConfig(BaseModel):
    """Where / what / how to invoke a provider.

    Three independent axes:

    * `provider` — the adapter key registered with `ProviderRegistry`
      (e.g. `openai`, `anthropic`, `openai_compatible`, `echo`).
    * `model` — the model identifier the adapter will pass through.
    * `endpoint` — optional base URL for `*_compatible` or custom
      hosting; providers with a fixed base URL (`openai`, `anthropic`)
      may ignore this.

    `credential_ref` names an environment variable (e.g.
    `OPENAI_API_KEY`). The adapter reads it at `.generate()` time;
    this object is safe to serialise.
    """

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    endpoint: str | None = None
    credential_ref: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    """One message in the chat log the adapter forwards."""

    model_config = ConfigDict(extra="allow")

    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None


class ToolDefinition(BaseModel):
    """A tool / function the adapter is asked to expose to the model."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1)
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    """One tool call the model emitted in the unified response."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class UnifiedRequest(BaseModel):
    """OneShot's provider-agnostic request shape."""

    model_config = ConfigDict(extra="forbid")

    messages: list[Message] = Field(default_factory=list, min_length=1)
    tools: list[ToolDefinition] = Field(default_factory=list)
    # The caller MAY pin a strict JSON Schema for the model's output.
    # Adapters that advertise `structured_outputs=True` honour it; others
    # raise `UnsupportedCapabilityError`.
    output_schema: dict[str, Any] | None = None
    # Opt-in capabilities. Setting `stream=True` on an adapter that
    # declares `streaming=False` MUST raise `UnsupportedCapabilityError`.
    stream: bool = False
    prompt_caching: bool = False
    strict_tool_schemas: bool = False
    # Vendor-neutral pass-through knobs the adapter is free to honour or
    # declare unsupported.
    max_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Usage(BaseModel):
    """Token / cost accounting the adapter returns verbatim."""

    model_config = ConfigDict(extra="allow")

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0


class UnifiedResponse(BaseModel):
    """Model answer in OneShot vocabulary.

    `finish_reason` is one of a short, vendor-neutral set:
    `stop | length | tool_calls | content_filter | error`.
    """

    model_config = ConfigDict(extra="forbid")

    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: Literal["stop", "length", "tool_calls", "content_filter", "error"] = "stop"
    usage: Usage = Field(default_factory=Usage)
    # Opaque metadata the adapter wishes to expose (fingerprint, request
    # id, cache hit flag). Non-authoritative.
    raw: dict[str, Any] = Field(default_factory=dict)


class UnifiedEvent(BaseModel):
    """Single event from a streaming adapter."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["delta", "tool_call", "usage", "done", "error"]
    data: dict[str, Any] = Field(default_factory=dict)


class BatchHandle(BaseModel):
    """Handle returned by `.batch()` on adapters that support batching."""

    model_config = ConfigDict(extra="forbid")

    id: str
    provider: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"] = "pending"


class ProviderCapabilities(BaseModel):
    """Boolean matrix the adapter declares at construction time.

    A caller requesting a capability the matrix does not advertise MUST
    get `UnsupportedCapabilityError`. This is the explicit-not-silent
    contract: a workflow that depends on structured outputs will fail
    LOUDLY on an adapter that cannot provide them, rather than
    silently falling back to free-form content.
    """

    model_config = ConfigDict(extra="forbid")

    structured_outputs: bool = False
    streaming: bool = False
    batch: bool = False
    prompt_caching: bool = False
    strict_tool_schemas: bool = False
    # Free-form name list — adapters MAY document extensions here.
    extensions: list[str] = Field(default_factory=list)
