"""Interaction-level events — minimal cross-boundary lifecycle log.

The repository already carries typed per-sub-boundary events:

    * `rsm.lifecycle.events.LifecycleEvent`  — append-only bucket state
      transitions on the FS `EventLog`.
    * `rsm.reader.model.ReaderEvent`         — per-File observation events
      in `ReadResult.events`.

Both are correctly scoped to their domain. What was missing — identified
in the §20 "Events and Streaming Audit" — is a single ordered view of
*what happened to one interaction* across all those sub-boundaries. This
module adds that view with the smallest possible machinery:

    * `InteractionEvent`  — one pydantic DTO.
    * `InteractionEventKind` — eight terminal / non-terminal kinds that
      map directly onto the §20 vocabulary.
    * NO new runtime, NO manager class, NO cross-interaction bus.

The ordering guarantees are made per-interaction:

    * `interaction_id` — stable identity (unchanged from ADR 0009).
    * `sequence`       — strictly monotonic unsigned integer, starting
                         at 1 for the first event an interaction emits.
                         Issued by `InteractionStore.next_sequence`.
    * `at`             — UTC wall-clock timestamp (same discipline as
                         `LifecycleEvent.at` and `ReaderEvent.at`).

Terminal / non-terminal classification (see `TERMINAL_KINDS` below):

    * terminal (an interaction with a terminal event cannot emit again):
      `completed`, `cancelled`, `failed`.
    * non-terminal:
      `created`, `started`, `observed`, `prepared_ready`.

Payloads reference existing stable DTOs by identity (counts, ids),
NEVER duplicate their full state. `coverage_summary` carries just the
ReaderTrace counts (`discovered` / `observed_count` / `failed_count` /
`complete`). The full ReaderTrace continues to live inside
`PreparedRepresentation.coverage` on the stream payload — this event
log is a lifecycle view, not a Replay alternative.

This module imports only stdlib + pydantic (same discipline as the rest
of `rsm.interaction`). The boundary gate guarantees nothing else creeps
in.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class InteractionEventKind(StrEnum):
    """Minimal §20 lifecycle vocabulary — NOT an OpenAI Response schema."""
    CREATED = "interaction.created"
    STARTED = "interaction.started"
    OBSERVED = "interaction.observed"           # Reader finished for this stream.
    PREPARED_READY = "interaction.prepared_ready"  # Processor built the PR.
    COMPLETED = "interaction.completed"         # Replay body written. Terminal.
    FAILED = "interaction.failed"               # Terminal.
    CANCELLED = "interaction.cancelled"         # Terminal.


# Terminal kinds — after any of these, `InteractionStore.append_event`
# will refuse further emissions for the same interaction (idempotent
# cancel, hard failure).
#
# `COMPLETED` is deliberately NOT terminal. The §20 "completed"
# vocabulary describes one successful stream; a well-behaved caller may
# re-stream the same (interaction, bucket) pair repeatedly (see
# `test_repeated_stream_is_idempotent_in_payload`) and each successful
# stream emits a fresh `completed` event. Making COMPLETED terminal
# would break that contract.
#
# `FAILED` IS terminal because the structured error paths (RSM_DISABLED
# / NO_SOURCE_SELECTED / BUCKET_NOT_FOUND / etc.) already return 4xx and
# the client typically needs to re-configure the record before the next
# attempt. If the client fixes the condition (e.g. flips `rsm_enabled`
# back on) the daemon has, by design, already lost the terminal event
# on restart; within a single process lifetime the deliberate choice is
# "once failed, stay failed" so the audit log is honest.
#
# `CANCELLED` is the §21 explicit terminal.
TERMINAL_KINDS: frozenset[InteractionEventKind] = frozenset({
    InteractionEventKind.CANCELLED,
    InteractionEventKind.FAILED,
})


class InteractionEvent(BaseModel):
    """One ordered interaction-lifecycle record.

    * `interaction_id`  — opaque, runtime-owned (ADR 0009).
    * `sequence`        — strictly monotonic per interaction (≥1).
    * `kind`            — see `InteractionEventKind`.
    * `at`              — UTC wall-clock.
    * `bucket_id`       — the Bucket the interaction had selected at the
                          moment the event was emitted (may be `None` on
                          `created` / `cancelled` / `failed` before a
                          Bucket was selected).
    * `payload`         — bounded, schema-free, references by identity.
                          Examples:
                            observed       → {"discovered", "observed",
                                              "partial", "failed",
                                              "complete"}
                            prepared_ready → {"snapshot_integrity"}
                            completed      → {"snapshot_integrity",
                                              "integrity"}
                            failed         → {"code", "message"}
                            cancelled      → {"reason"}
                          Payloads NEVER duplicate full source content.
    """
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    interaction_id: str = Field(..., min_length=1)
    sequence: int = Field(..., ge=1)
    kind: InteractionEventKind
    at: datetime
    bucket_id: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


def utcnow() -> datetime:
    """Deterministic timezone-aware UTC `datetime.now()`.

    Exposed so tests may monkeypatch; production emits always use UTC.
    """
    return datetime.now(timezone.utc)


def make_event(
    *,
    interaction_id: str,
    sequence: int,
    kind: InteractionEventKind,
    bucket_id: Optional[str] = None,
    payload: Optional[dict[str, Any]] = None,
) -> InteractionEvent:
    """Pure constructor — stamps `at = utcnow()` and returns the DTO."""
    return InteractionEvent(
        interaction_id=interaction_id,
        sequence=sequence,
        kind=kind,
        at=utcnow(),
        bucket_id=bucket_id,
        payload=payload or {},
    )
