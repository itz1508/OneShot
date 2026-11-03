"""Streaming types for provider responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class StreamEventType(StrEnum):
    """Event types in a provider stream."""

    TEXT_DELTA = "text_delta"
    TOOL_REQUESTED = "tool_requested"
    USAGE = "usage"
    ERROR = "error"
    COMPLETED = "completed"


@dataclass(frozen=True)
class StreamEvent:
    """A single event from a provider stream."""

    event_type: StreamEventType
    provider: str
    content: str | None = None
    tool_call_id: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    input_tokens: int | None = None
    output_tokens: int | None = None
