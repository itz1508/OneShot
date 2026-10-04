"""In-memory `InteractionStore` (ADR 0009, ADR 0016, ADR 0017).

Discipline mirror of classification / execution stores on `DaemonService`:
process-lifetime, not persisted. Daemon restart ⇒ records cleared ⇒ next read
sees the fail-closed default.

ADR 0017 added an append-only, per-interaction event log on this same
store (`InteractionEvent`). The log reuses the record keyspace so the
record and its events share one identity (`interaction_id`) and one
process lifetime. No disk persistence — the §21 cancellation + §20
ordering guarantees are only in effect while the daemon runs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .events import (
    TERMINAL_KINDS,
    InteractionEvent,
    InteractionEventKind,
    make_event,
)
from .model import InteractionRecord, DEFAULT_INTERACTION


class InteractionTerminated(Exception):
    """Raised when a terminal event (completed/cancelled/failed) has
    already been written for this interaction and a further event is
    attempted. The caller must handle this as a no-op — the terminal
    is binding (§21 "already delivered material cannot be unsent" plus
    "cancellation stops further unreleased delivery").
    """

    def __init__(self, interaction_id: str, terminal_kind: InteractionEventKind):
        super().__init__(
            f"Interaction {interaction_id!r} already terminated by "
            f"{terminal_kind.value}; further events are refused."
        )
        self.interaction_id = interaction_id
        self.terminal_kind = terminal_kind


class InteractionStore:
    """Thread-safe-enough for FastAPI's dependency model (single-process).

    Owns both the authorisation record (`InteractionRecord`) and the
    append-only event log (`InteractionEvent`), keyed by `interaction_id`.
    """

    def __init__(self) -> None:
        self._records: Dict[str, InteractionRecord] = {}
        self._events: Dict[str, List[InteractionEvent]] = {}
        self._next_seq: Dict[str, int] = {}

    # ---- reads ----

    def get(self, interaction_id: str) -> InteractionRecord:
        """Return the stored record, or a fail-closed default if unknown.

        Reading NEVER persists a default record — callers that want the
        default persisted must `put` it explicitly.
        """
        existing = self._records.get(interaction_id)
        if existing is None:
            return DEFAULT_INTERACTION(interaction_id)
        return existing

    def exists(self, interaction_id: str) -> bool:
        return interaction_id in self._records

    # ---- writes ----

    def put(self, record: InteractionRecord) -> InteractionRecord:
        self._records[record.interaction_id] = record
        return record

    def mark_streamed(self, interaction_id: str) -> Optional[InteractionRecord]:
        """UX hint: stamp `last_streamed_at`. Returns None if unknown.

        Does NOT change authorization; a stream that reached this point was
        already authorised.
        """
        cur = self._records.get(interaction_id)
        if cur is None:
            return None
        stamped = InteractionRecord(
            interaction_id=cur.interaction_id,
            rsm_enabled=cur.rsm_enabled,
            selected_bucket_id=cur.selected_bucket_id,
            last_streamed_at=datetime.now(timezone.utc),
        )
        self._records[interaction_id] = stamped
        return stamped

    # ---- V3 interaction events (ADR 0017) ----

    def _next_sequence(self, interaction_id: str) -> int:
        """Issue the next monotonic sequence number for this interaction.

        Starts at 1. Pure allocator; does NOT create an event.
        """
        n = self._next_seq.get(interaction_id, 0) + 1
        self._next_seq[interaction_id] = n
        return n

    def terminal_kind(
        self, interaction_id: str
    ) -> Optional[InteractionEventKind]:
        """Return the terminal event kind if the interaction has one,
        else `None`. Readers use this to short-circuit before emitting.
        """
        events = self._events.get(interaction_id, [])
        for ev in reversed(events):
            if ev.kind in TERMINAL_KINDS:
                return ev.kind
        return None

    def append_event(
        self,
        *,
        interaction_id: str,
        kind: InteractionEventKind,
        bucket_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> InteractionEvent:
        """Append one `InteractionEvent` to this interaction's log.

        Raises `InteractionTerminated` if a terminal event already
        exists. Callers that race are expected to catch and treat it as
        a no-op — this guarantees §21 cancellation + §20 completion
        semantics without a lock around the entire request path.
        """
        existing_terminal = self.terminal_kind(interaction_id)
        if existing_terminal is not None:
            raise InteractionTerminated(interaction_id, existing_terminal)
        ev = make_event(
            interaction_id=interaction_id,
            sequence=self._next_sequence(interaction_id),
            kind=kind,
            bucket_id=bucket_id,
            payload=payload,
        )
        self._events.setdefault(interaction_id, []).append(ev)
        return ev

    def read_events(self, interaction_id: str) -> List[InteractionEvent]:
        """Return the events in append order (never mutates)."""
        return list(self._events.get(interaction_id, []))
