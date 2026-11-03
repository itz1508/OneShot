"""Provider adapter base — protocol, request/result types, capabilities."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class ProviderError(Exception):
    pass


class UnsupportedProviderError(ProviderError):
    pass


class UnsupportedCapabilityError(ProviderError):
    pass


class ProviderConfig(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    endpoint: str | None = None
    credential_ref: str = Field(min_length=1)
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProviderRequest(BaseModel):
    run_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    system_prompt: str = ""
    max_tokens: int = Field(default=4096, ge=1)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    model_config = ConfigDict(extra="forbid")


class ProviderResult(BaseModel):
    content: str = ""
    tool_calls: tuple[dict[str, Any], ...] = ()
    finish_reason: str = "stop"
    usage: dict[str, Any] = Field(default_factory=dict)
    provider: str = ""
    model: str = ""
    model_config = ConfigDict(extra="forbid")


class ProviderEvent(BaseModel):
    event_type: str = Field(min_length=1)
    content_delta: str = ""
    tool_call_id: str | None = None
    tool_call_name: str | None = None
    tool_call_args_delta: str | None = None
    finish_reason: str | None = None
    model_config = ConfigDict(extra="forbid")


class CapabilityDescriptor(BaseModel):
    structured_outputs: bool = False
    streaming: bool = False
    batch: bool = False
    prompt_caching: bool = False
    strict_tool_schemas: bool = False
    model_config = ConfigDict(extra="forbid", frozen=True)


@runtime_checkable
class ProviderAdapter(Protocol):
    """Protocol for all provider adapters."""

    def generate(self, request: ProviderRequest) -> ProviderResult: ...
    def declared_capabilities(self) -> CapabilityDescriptor: ...
