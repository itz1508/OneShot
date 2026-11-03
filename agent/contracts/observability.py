"""Observability contracts -- hash-chained execution events and trace context."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field

from agent.contracts.common import ContractModel, Sha256


class EventStatus(StrEnum):
    """Lifecycle of an execution event."""

    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    INTERRUPTED = "interrupted"


class ExecutionEvent(ContractModel):
    """Hash-chained event log entry for operations and stages."""

    event_id: str = Field(min_length=1)
    previous_event_digest: Sha256 | None = None
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    operation_id: str | None = None
    provider: str | None = None
    tool_identity: str | None = None
    status: EventStatus
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    input_digest: Sha256 | None = None
    output_digest: Sha256 | None = None
    receipt_ref: str | None = None
    error_class: str | None = None


class TraceContext(ContractModel):
    """Distributed trace linking for cross-stage observability."""

    trace_id: str = Field(min_length=1)
    group_id: str | None = None
    parent_span_id: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
