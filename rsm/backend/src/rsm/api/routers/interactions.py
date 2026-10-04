"""V3 interaction router (ADR 0009, 0010, 0017).

Endpoints:

    GET  /v1/interactions/{interaction_id}
    PUT  /v1/interactions/{interaction_id}
    GET  /v1/interactions/{interaction_id}/stream
    GET  /v1/interactions/{interaction_id}/events    (ADR 0017)
    POST /v1/interactions/{interaction_id}/cancel    (ADR 0017)

Semantics (ADR 0009):

* Reading an unknown interaction returns the fail-closed default
  (`rsm_enabled=False`, no bucket selected) WITHOUT persisting it.
* PUT replaces the stored record for `interaction_id`. If the body selects a
  `selected_bucket_id`, that Bucket must exist (otherwise 404).
* The `/stream` endpoint fails closed:
    - unknown or disabled → 409 RSM_DISABLED,
    - no Bucket selected  → 409 NO_SOURCE_SELECTED,
    - Bucket vanished     → 404 BUCKET_NOT_FOUND.
  Otherwise it streams a single-chunk `application/json` body carrying both
  the replay envelope (`source="rsm"`, provenance, integrity) and the current
  bounded Snapshot (`SnapshotKind.PRESERVED` by default; `?reduce=prefix` for
  the deterministic bounded excerpt).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ...assessment import assess_source
from ...bucket.serializer import canonical_dumps
from ...daemon.service import DaemonService, get_daemon
from ...interaction.events import InteractionEventKind
from ...interaction.model import InteractionRecord
from ...interaction.store import InteractionTerminated
from ...prepared import build_prepared_representation
from ...reader import read_bucket
from ...replay.envelope import build_replay_envelope
from ...snapshot import (
    ContextBudget,
    BudgetUnit,
    NullSummaryProvider,
    PrefixSummaryProvider,
    SnapshotBuildError,
    SummaryUnavailable,
    build_snapshot,
)
from ..errors import (
    BucketNotFound,
    RSMError,
    RsmDisabled,
    NoSourceSelected,
)

router = APIRouter()


class _SnapshotBuildFailed(RSMError):
    code = "SNAPSHOT_BUILD_FAILED"
    http_status = 422


class _SummaryUnavailable(RSMError):
    code = "SUMMARY_UNAVAILABLE"
    http_status = 409


class _InvalidBudget(RSMError):
    code = "INVALID_BUDGET"
    http_status = 422


def _record_as_envelope(record: InteractionRecord) -> dict[str, Any]:
    return record.model_dump(mode="json")


@router.get("/{interaction_id}")
async def get_interaction(
    interaction_id: str, daemon: DaemonService = Depends(get_daemon)
):
    """Read the interaction record. Unknown ids return the fail-closed default."""
    return _record_as_envelope(daemon.get_interaction(interaction_id))


@router.put("/{interaction_id}")
async def put_interaction(
    interaction_id: str,
    body: dict,
    daemon: DaemonService = Depends(get_daemon),
):
    """Replace the stored interaction record.

    Body shape (all fields optional):
        {
          "rsm_enabled": true|false,
          "selected_bucket_id": "bkt_..." | null
        }

    Unset fields on an unknown interaction default to the fail-closed values.
    `selected_bucket_id: null` explicitly clears the selection.
    """
    current = daemon.get_interaction(interaction_id)
    rsm_enabled = bool(body.get("rsm_enabled", current.rsm_enabled))

    # Distinguish "key present with None" from "key absent".
    if "selected_bucket_id" in body:
        selected = body["selected_bucket_id"]
        if selected is not None and not isinstance(selected, str):
            raise _InvalidBudget(
                "selected_bucket_id must be a string or null",
                details={"selected_bucket_id": selected},
            )
    else:
        selected = current.selected_bucket_id

    updated = InteractionRecord(
        interaction_id=interaction_id,
        rsm_enabled=rsm_enabled,
        selected_bucket_id=selected,
        last_streamed_at=current.last_streamed_at,
    )
    daemon.put_interaction(updated)

    # ADR 0017 — emit `interaction.created` the first time this
    # interaction becomes known to the store. `exists` is used instead
    # of counting events so we never emit twice for the same
    # interaction (PUT is routinely idempotent).
    # The record was persisted above; its very first appearance in the
    # store is "created". Terminal interactions do not re-create; a PUT
    # to a terminated interaction is accepted (idempotent record update)
    # but does not emit a new event — the `InteractionTerminated` guard
    # in `append_event` enforces that.
    store = daemon.interactions
    try:
        store.append_event(
            interaction_id=interaction_id,
            kind=InteractionEventKind.CREATED,
            bucket_id=selected,
            payload={"rsm_enabled": rsm_enabled},
        )
    except InteractionTerminated:
        pass  # already terminal — no further events allowed (§21).

    # Re-read in case the daemon normalised anything.
    return _record_as_envelope(daemon.get_interaction(interaction_id))


def _build_stream_payload(
    daemon: DaemonService,
    record: InteractionRecord,
    *,
    budget_unit: str,
    budget_value: int,
    reduce: str,
) -> dict[str, Any]:
    # Authorization gate: fail closed.
    if not record.rsm_enabled:
        raise RsmDisabled(
            "RSM is disabled for this interaction",
            details={"interaction_id": record.interaction_id},
        )
    if record.selected_bucket_id is None:
        raise NoSourceSelected(
            "No source Bucket selected for this interaction",
            details={"interaction_id": record.interaction_id},
        )

    bucket = daemon.store.read(record.selected_bucket_id)
    if bucket is None:
        raise BucketNotFound(
            f"No bucket with id {record.selected_bucket_id!r}",
            details={"bucket_id": record.selected_bucket_id},
        )

    try:
        unit = BudgetUnit(budget_unit)
        budget = ContextBudget(unit=unit, value=budget_value)
    except Exception as e:
        raise _InvalidBudget(
            f"Invalid budget: {e}",
            details={"budget_unit": budget_unit, "budget_value": budget_value},
        )
    provider = {
        "null": NullSummaryProvider(),
        "prefix": PrefixSummaryProvider(),
    }.get(reduce)
    if provider is None:
        raise _InvalidBudget(
            f"Unknown reduce mode {reduce!r}", details={"reduce": reduce}
        )

    try:
        snap = build_snapshot(bucket, budget=budget, summary_provider=provider)
    except SummaryUnavailable as e:
        raise _SummaryUnavailable(str(e), details={"bucket_id": bucket.bucket_id})
    except SnapshotBuildError as e:
        raise _SnapshotBuildFailed(str(e), details={"bucket_id": bucket.bucket_id})

    classification = daemon.get_classification(bucket.bucket_id)
    envelope = build_replay_envelope(bucket, classification=classification)

    # Reader coverage over the frozen Bucket. Pure, deterministic, no I/O
    # beyond `bucket.full_content` (A1 preserved). This is the "what was
    # actually observed" half of the Prepared Representation; Snapshot is
    # the "what was prepared" half.
    read_result = read_bucket(bucket)

    # Prepared Representation — the typed Processor→Replay boundary. It
    # unites assessment + coverage + snapshot + replay envelope under one
    # name. Added additively; the existing top-level keys are unchanged.
    prepared = build_prepared_representation(
        bucket=bucket,
        assessment=assess_source(bucket),
        read_result=read_result,
        snapshot=snap,
        replay_envelope=envelope,
    )

    return {
        "source": "rsm",
        "schema_version": "1",
        "interaction_id": record.interaction_id,
        "bucket_id": bucket.bucket_id,
        "replay": envelope,
        "snapshot": snap.model_dump(mode="json"),
        # V3 Prepared Representation (additive). Same observations and
        # same snapshot, under the architectural name doctrine §9/§10.
        "prepared_representation": prepared.model_dump(mode="json"),
    }


def _emit(
    daemon: DaemonService,
    interaction_id: str,
    kind: InteractionEventKind,
    *,
    bucket_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Best-effort emit; terminal interactions silently absorb (§21)."""
    try:
        daemon.interactions.append_event(
            interaction_id=interaction_id,
            kind=kind,
            bucket_id=bucket_id,
            payload=payload or {},
        )
    except InteractionTerminated:
        pass


@router.get("/{interaction_id}/stream")
async def stream_interaction(
    interaction_id: str,
    budget_unit: str = "characters",
    budget_value: int = 2000,
    reduce: str = "null",
    daemon: DaemonService = Depends(get_daemon),
):
    """ReplayStreaming — chunked HTTP, exactly one JSON chunk (ADR 0010).

    Emits ADR 0017 interaction events as the request progresses. The
    HTTP contract is unchanged: 200 → single JSON chunk; 4xx → same
    structured error codes (RSM_DISABLED / NO_SOURCE_SELECTED /
    BUCKET_NOT_FOUND / SUMMARY_UNAVAILABLE / SNAPSHOT_BUILD_FAILED /
    INVALID_BUDGET). A terminated interaction (cancelled or already
    failed) still returns the same 4xx envelope — ADR 0017 adds the
    event log, not a new error shape.

    Errors (fail closed): see module docstring.
    """
    record = daemon.get_interaction(interaction_id)

    # Refuse to serve a stream after a terminal event — this is the
    # §21 cancellation discipline. The record's `rsm_enabled` would also
    # catch this if `cancel` had flipped it, but we DO NOT flip it: the
    # terminal event is the authority (so the record stays inspectable
    # by the UI without inventing an extra flag).
    terminal = daemon.interactions.terminal_kind(interaction_id)
    if terminal is not None:
        raise RsmDisabled(
            "Interaction is terminated and cannot be streamed",
            details={
                "interaction_id": interaction_id,
                "terminal_kind": terminal.value,
            },
        )

    # Pre-auth: emit `interaction.started` only after the gate passes
    # (so a disabled interaction never gets a `started` in its log).
    try:
        payload = _build_stream_payload(
            daemon,
            record,
            budget_unit=budget_unit,
            budget_value=budget_value,
            reduce=reduce,
        )
    except RSMError as e:
        # Non-200 path: emit `interaction.failed` carrying the stable
        # error code the client already sees.
        _emit(
            daemon,
            interaction_id,
            InteractionEventKind.FAILED,
            bucket_id=record.selected_bucket_id,
            payload={"code": e.code, "message": e.message},
        )
        raise

    bid = record.selected_bucket_id  # guaranteed non-None past the gate
    _emit(
        daemon,
        interaction_id,
        InteractionEventKind.STARTED,
        bucket_id=bid,
    )
    coverage = payload["prepared_representation"]["coverage"]
    _emit(
        daemon,
        interaction_id,
        InteractionEventKind.OBSERVED,
        bucket_id=bid,
        payload={
            "discovered": coverage["discovered"],
            "observed": coverage["observed_count"],
            "partial": coverage["partial_count"],
            "failed": coverage["failed_count"],
            "complete": coverage["complete"],
        },
    )
    _emit(
        daemon,
        interaction_id,
        InteractionEventKind.PREPARED_READY,
        bucket_id=bid,
        payload={
            "snapshot_integrity": payload["snapshot"]["integrity"]["value"],
            "integrity": payload["replay"]["integrity"]["value"],
        },
    )

    # Mark delivered AFTER payload build succeeded. Does not affect authorization.
    if daemon.interactions.exists(interaction_id):
        daemon.interactions.mark_streamed(interaction_id)

    # The response body is produced synchronously; `interaction.completed`
    # is emitted BEFORE handing the body to FastAPI's StreamingResponse.
    # Rationale: the HTTP connection could close before the client reads
    # the chunk, but by the time this code runs the daemon has in fact
    # produced the authorised prepared material. The §20 "completed"
    # vocabulary applies to RSM's work, not to the socket.
    _emit(
        daemon,
        interaction_id,
        InteractionEventKind.COMPLETED,
        bucket_id=bid,
        payload={
            "snapshot_integrity": payload["snapshot"]["integrity"]["value"],
            "integrity": payload["replay"]["integrity"]["value"],
        },
    )

    body = canonical_dumps(payload)

    def _chunker():  # pragma: no cover - trivial generator
        yield body

    return StreamingResponse(_chunker(), media_type="application/json")


@router.get("/{interaction_id}/events")
async def list_interaction_events(
    interaction_id: str, daemon: DaemonService = Depends(get_daemon)
):
    """Read-only view of the ADR 0017 event log for one interaction.

    Returns events in append order with a monotonic `sequence` per
    interaction. The response is intentionally un-paginated: a single
    interaction's lifecycle log is bounded (at most one each of
    created / started / observed / prepared_ready / completed /
    cancelled / failed, by construction of the emit sites).

    Unknown interactions return `events: []` — same discipline as a
    GET on `/v1/interactions/{id}` returning the fail-closed default.
    """
    events = daemon.interactions.read_events(interaction_id)
    return {
        "interaction_id": interaction_id,
        "terminal_kind": (
            daemon.interactions.terminal_kind(interaction_id).value
            if daemon.interactions.terminal_kind(interaction_id) is not None
            else None
        ),
        "events": [ev.model_dump(mode="json") for ev in events],
    }


@router.post("/{interaction_id}/cancel")
async def cancel_interaction(
    interaction_id: str,
    body: dict | None = None,
    daemon: DaemonService = Depends(get_daemon),
):
    """§21 cancellation — stop further unreleased delivery.

    Appends `interaction.cancelled` to the event log. This is a terminal
    event: subsequent `/stream` calls return `409 RSM_DISABLED` with
    `terminal_kind="interaction.cancelled"` in `details`. Does NOT
    touch Source (A1 preserved) and does NOT flip `rsm_enabled` on the
    record — the terminal event is the authority.

    Idempotent: cancelling an already-terminated interaction returns the
    existing terminal state without appending a new event.
    """
    reason = None
    if isinstance(body, dict):
        reason = body.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise _InvalidBudget(
                "reason must be a string if present",
                details={"reason": reason},
            )

    record = daemon.get_interaction(interaction_id)
    existing_terminal = daemon.interactions.terminal_kind(interaction_id)
    if existing_terminal is not None:
        return {
            "interaction_id": interaction_id,
            "terminal_kind": existing_terminal.value,
            "already_terminated": True,
        }
    _emit(
        daemon,
        interaction_id,
        InteractionEventKind.CANCELLED,
        bucket_id=record.selected_bucket_id,
        payload={"reason": reason} if reason is not None else {},
    )
    return {
        "interaction_id": interaction_id,
        "terminal_kind": InteractionEventKind.CANCELLED.value,
        "already_terminated": False,
    }
