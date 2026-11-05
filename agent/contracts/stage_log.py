"""Typed, host-owned stage journal events; JSONL is a projection, not task state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, field_validator

from agent.contracts.common import ContractModel

StageName = Literal["search", "audit", "plan", "build", "mem"]


class StageLogEvent(ContractModel):
    event_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    workspace_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    task_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    stage: StageName
    event: str = Field(min_length=1)
    status: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    todo_id: str | None = None
    attempt_id: str | None = None
    tool_call_id: str | None = None
    artifact_ref: str | None = None
    receipt_ref: str | None = None
    evidence_ref: str | None = None
    template_ref: str | None = None
    source_build_ref: str | None = None
    verification_receipt_ref: str | None = None
    reusable_scope: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("created_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        offset = value.utcoffset()
        if value.tzinfo is None or offset is None:
            raise ValueError("created_at must be timezone aware")
        if offset.total_seconds() != 0:
            raise ValueError("created_at must be UTC")
        return value
