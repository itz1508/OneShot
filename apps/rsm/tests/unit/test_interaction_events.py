"""Unit tests for the ADR 0017 interaction event vocabulary.

Scope: identity, ordering, lifecycle vocabulary, failure terminals,
cancellation semantics, isolation, idempotency.
"""

from __future__ import annotations

import pytest

from rsm.interaction import (
    InteractionEvent,
    InteractionEventKind,
    InteractionStore,
    InteractionTerminated,
    TERMINAL_KINDS,
    make_event,
)


# ---- Vocabulary / terminals ----


def test_vocabulary_matches_section_20():
    """The §20 vocabulary — created, started, progress, observed, failed,
    ready, completed, cancelled — maps onto these seven kinds. 'progress'
    is not its own kind; it's represented by the sequence of `observed`
    events (per discovered File) + the aggregate ReaderTrace that lives
    on `PreparedRepresentation.coverage`.
    """
    assert {k.value for k in InteractionEventKind} == {
        "interaction.created",
        "interaction.started",
        "interaction.observed",
        "interaction.prepared_ready",
        "interaction.completed",
        "interaction.failed",
        "interaction.cancelled",
    }


def test_terminal_kinds_are_cancelled_and_failed_only():
    """COMPLETED is deliberately NOT terminal — repeated streams keep
    producing fresh completed events (the HTTP contract already allows
    that; see `test_repeated_stream_is_idempotent_in_payload`).
    """
    assert TERMINAL_KINDS == frozenset({
        InteractionEventKind.CANCELLED,
        InteractionEventKind.FAILED,
    })


# ---- Sequence allocator ----


def test_sequence_is_monotonic_per_interaction():
    s = InteractionStore()
    a1 = s.append_event(interaction_id="i-A", kind=InteractionEventKind.CREATED)
    a2 = s.append_event(interaction_id="i-A", kind=InteractionEventKind.STARTED)
    a3 = s.append_event(interaction_id="i-A", kind=InteractionEventKind.OBSERVED)
    assert [e.sequence for e in (a1, a2, a3)] == [1, 2, 3]


def test_sequence_is_independent_per_interaction():
    """Interaction A and interaction B maintain independent sequences —
    there is no global event bus."""
    s = InteractionStore()
    a = s.append_event(interaction_id="i-A", kind=InteractionEventKind.CREATED)
    b = s.append_event(interaction_id="i-B", kind=InteractionEventKind.CREATED)
    a2 = s.append_event(interaction_id="i-A", kind=InteractionEventKind.STARTED)
    assert a.sequence == 1
    assert b.sequence == 1
    assert a2.sequence == 2


def test_events_carry_identity_and_timestamp():
    s = InteractionStore()
    ev = s.append_event(
        interaction_id="i-1",
        kind=InteractionEventKind.CREATED,
        bucket_id="bkt_abc",
        payload={"rsm_enabled": True},
    )
    assert isinstance(ev, InteractionEvent)
    assert ev.schema_version == "1"
    assert ev.interaction_id == "i-1"
    assert ev.bucket_id == "bkt_abc"
    assert ev.sequence == 1
    assert ev.payload == {"rsm_enabled": True}
    assert ev.at.tzinfo is not None  # timezone-aware UTC


# ---- Terminal / idempotency ----


def test_cancelled_is_terminal():
    s = InteractionStore()
    s.append_event(interaction_id="i-1", kind=InteractionEventKind.CREATED)
    s.append_event(interaction_id="i-1", kind=InteractionEventKind.CANCELLED)
    with pytest.raises(InteractionTerminated) as cm:
        s.append_event(interaction_id="i-1", kind=InteractionEventKind.STARTED)
    assert cm.value.terminal_kind == InteractionEventKind.CANCELLED


def test_failed_is_terminal():
    s = InteractionStore()
    s.append_event(interaction_id="i-1", kind=InteractionEventKind.FAILED,
                   payload={"code": "RSM_DISABLED"})
    with pytest.raises(InteractionTerminated) as cm:
        s.append_event(interaction_id="i-1", kind=InteractionEventKind.STARTED)
    assert cm.value.terminal_kind == InteractionEventKind.FAILED


def test_completed_is_not_terminal():
    """§20 'completed' is per-stream; the interaction may stream again."""
    s = InteractionStore()
    s.append_event(interaction_id="i-1", kind=InteractionEventKind.CREATED)
    s.append_event(interaction_id="i-1", kind=InteractionEventKind.COMPLETED)
    # A second successful stream appends a fresh event sequence.
    s.append_event(interaction_id="i-1", kind=InteractionEventKind.STARTED)
    s.append_event(interaction_id="i-1", kind=InteractionEventKind.COMPLETED)
    kinds = [ev.kind for ev in s.read_events("i-1")]
    assert kinds == [
        InteractionEventKind.CREATED,
        InteractionEventKind.COMPLETED,
        InteractionEventKind.STARTED,
        InteractionEventKind.COMPLETED,
    ]


def test_terminal_kind_lookup():
    s = InteractionStore()
    assert s.terminal_kind("i-missing") is None
    s.append_event(interaction_id="i-1", kind=InteractionEventKind.CREATED)
    assert s.terminal_kind("i-1") is None
    s.append_event(interaction_id="i-1", kind=InteractionEventKind.CANCELLED)
    assert s.terminal_kind("i-1") == InteractionEventKind.CANCELLED


# ---- Isolation ----


def test_read_events_isolates_per_interaction():
    s = InteractionStore()
    s.append_event(interaction_id="i-A", kind=InteractionEventKind.CREATED,
                   bucket_id="bkt_A")
    s.append_event(interaction_id="i-B", kind=InteractionEventKind.CREATED,
                   bucket_id="bkt_B")
    a = s.read_events("i-A")
    b = s.read_events("i-B")
    assert [e.bucket_id for e in a] == ["bkt_A"]
    assert [e.bucket_id for e in b] == ["bkt_B"]


def test_read_events_returns_copy_not_mutable_reference():
    s = InteractionStore()
    s.append_event(interaction_id="i-1", kind=InteractionEventKind.CREATED)
    events = s.read_events("i-1")
    events.clear()
    assert len(s.read_events("i-1")) == 1
