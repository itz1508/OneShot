"""Execution state records."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ExecutionStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class ExecutionTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    status: TaskStatus = TaskStatus.PENDING
    note: str | None = None


class ExecutionState(BaseModel):
    """Execution-side record keyed by bucket_id. Lives OUTSIDE the Bucket."""
    model_config = ConfigDict(extra="forbid")

    bucket_id: str
    state: ExecutionStatus = ExecutionStatus.NOT_STARTED
    tasks: list[ExecutionTask] = Field(default_factory=list)

    def to_envelope(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
