"""Phase 19 — restart / persistence round-trip.

Ingest a Bucket into an on-disk FsStore + EventLog, then open a FRESH
DaemonService on the SAME directories and verify the Bucket is still
addressable + replayable identically.

The InteractionStore remains in-memory by design (ADR 0017 non-goal);
this test deliberately does NOT assert its survival.
"""
from __future__ import annotations

from pathlib import Path

from rsm.daemon.eventlog import EventLog
from rsm.daemon.service import DaemonService
from rsm.daemon.store import FsStore
from rsm.replay.envelope import build_replay_envelope


def test_restart_preserves_bucket(tmp_path: Path) -> None:
    store_root = tmp_path / "store"
    log = tmp_path / "events.log"

    svc1 = DaemonService(store=FsStore(store_root), eventlog=EventLog(log))
    b = svc1.ingest_text("durable content")
    bid = b.bucket_id
    first = build_replay_envelope(b)

    # New process-equivalent: brand-new objects over the SAME disk layout.
    svc2 = DaemonService(store=FsStore(store_root), eventlog=EventLog(log))
    b2 = svc2.store.read(bid)
    assert b2 is not None
    assert b2.hash.value == b.hash.value
    second = build_replay_envelope(b2)
    assert first == second

    # Lifecycle event log survived.
    events = svc2.eventlog.read(bid)
    assert any(e.get("to_state") == "RECEIVED" for e in events)
