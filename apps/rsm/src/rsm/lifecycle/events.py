"""Append-only lifecycle event records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .states import State


class LifecycleEvent(BaseModel):
    """A single append-only lifecycle event."""
    model_config = ConfigDict(extra="forbid")

    bucket_id: str
    from_state: State | None
    to_state: State
    at: datetime
    actor: str = "daemon"
    note: str | None = None


def event_log_entry(
    bucket_id: str,
    *,
    from_state: State | None,
    to_state: State,
    actor: str = "daemon",
    note: str | None = None,
) -> dict[str, Any]:
    """Build an event-log dict ready for the daemon's append-only log."""
    ev = LifecycleEvent(
        bucket_id=bucket_id,
        from_state=from_state,
        to_state=to_state,
        at=datetime.now(timezone.utc),
        actor=actor,
        note=note,
    )
    return ev.model_dump(mode="json")
