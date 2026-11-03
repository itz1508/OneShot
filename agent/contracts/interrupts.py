"""Interrupt contracts -- durable pause/resume boundary independent from provider session state."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from agent.contracts.common import ContractModel, Sha256


class InterruptStatus(StrEnum):
    """Lifecycle of an interrupt request."""

    REQUESTED = "requested"
    PAUSED = "paused"
    RESUMED = "resumed"
    CANCELLED = "cancelled"


class InterruptRecord(ContractModel):
    """Durable pause/resume record tied to a checkpoint."""

    interrupt_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    checkpoint_id: str = Field(min_length=1)
    checkpoint_revision: int = Field(ge=1)
    checkpoint_digest: Sha256
    status: InterruptStatus
    reason: str = Field(min_length=1)
    response_schema_ref: str | None = None
    response_digest: Sha256 | None = None
