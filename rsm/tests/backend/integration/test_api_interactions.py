"""V3 — HTTP coverage for the interactions router + ON/OFF gating (ADR 0009, 0010).

Covers:
- default OFF record on unknown interaction
- PUT lifecycle (enable, select bucket, clear bucket, disable)
- /stream fail-closed cases: unknown, disabled, no bucket selected
- /stream happy path shape (source="rsm", provenance, integrity, snapshot)
- /replay and /snapshot gating when interaction_id is supplied
- legacy /replay and /snapshot behaviour when interaction_id is omitted
- interaction isolation: A does not see B's bucket
- source revision: Bucket A → Bucket B (derived_from A); stream delivers B
"""

import json

from fastapi.testclient import TestClient
from rsm.api.app import create_app


def _client(tmp_path, monkeypatch):
    from rsm.daemon import service as svc
    from rsm.daemon.store import FsStore
    from rsm.daemon.eventlog import EventLog
    from rsm.interaction.store import InteractionStore
    daemon = svc.DaemonService(
        store=FsStore(tmp_path / "buckets"),
        eventlog=EventLog(tmp_path / "events.log"),
        interactions=InteractionStore(),
    )
    monkeypatch.setattr(svc, "_default_daemon", daemon)
    return TestClient(create_app())


def _ingest(client, text="hello"):
    r = client.post("/v1/buckets/", json={"content": text, "kind": "text"})
    assert r.status_code == 200, r.text
    return r.json()["bucket"]["bucket_id"]


# ---- GET / default ----

def test_get_unknown_interaction_returns_default_off(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.get("/v1/interactions/i-unknown")
    assert r.status_code == 200
    body = r.json()
    assert body["interaction_id"] == "i-unknown"
    assert body["rsm_enabled"] is False
    assert body["selected_bucket_id"] is None


# ---- PUT lifecycle ----

def test_put_then_get_roundtrip(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "doc")
    r = c.put(
        "/v1/interactions/i-1",
        json={"rsm_enabled": True, "selected_bucket_id": bid},
    )
    assert r.status_code == 200, r.text
    assert r.json()["rsm_enabled"] is True
    assert r.json()["selected_bucket_id"] == bid

    r2 = c.get("/v1/interactions/i-1").json()
    assert r2["rsm_enabled"] is True
    assert r2["selected_bucket_id"] == bid


def test_put_selected_bucket_id_null_clears(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "doc")
    c.put("/v1/interactions/i-1", json={"rsm_enabled": True, "selected_bucket_id": bid})
    r = c.put("/v1/interactions/i-1", json={"selected_bucket_id": None})
    assert r.status_code == 200
    assert r.json()["selected_bucket_id"] is None


def test_put_rejects_nonexistent_bucket(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.put(
        "/v1/interactions/i-1",
        json={"rsm_enabled": True, "selected_bucket_id": "bkt_does_not_exist"},
    )
    assert r.status_code == 404
    assert r.json()["code"] == "BUCKET_NOT_FOUND"


# ---- /stream fail-closed ----

def test_stream_unknown_interaction_fails_closed(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.get("/v1/interactions/i-unknown/stream")
    assert r.status_code == 409
    assert r.json()["code"] == "RSM_DISABLED"


def test_stream_disabled_fails_closed(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "doc")
    c.put("/v1/interactions/i-1", json={"rsm_enabled": False, "selected_bucket_id": bid})
    r = c.get("/v1/interactions/i-1/stream")
    assert r.status_code == 409
    assert r.json()["code"] == "RSM_DISABLED"


def test_stream_no_bucket_selected(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    c.put("/v1/interactions/i-1", json={"rsm_enabled": True})
    r = c.get("/v1/interactions/i-1/stream")
    assert r.status_code == 409
    assert r.json()["code"] == "NO_SOURCE_SELECTED"


def test_stream_bucket_vanished_404(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    # Create record pointing at a bucket, then simulate deletion by swapping store.
    bid = _ingest(c, "doc")
    c.put("/v1/interactions/i-1", json={"rsm_enabled": True, "selected_bucket_id": bid})
    # Force the store to forget the bucket (deletion is not a V1 feature, but we
    # emulate "bucket vanished" by rewriting the daemon's store with a fresh one).
    from rsm.daemon import service as svc
    daemon = svc._default_daemon
    daemon.store._path(bid).unlink()  # type: ignore[attr-defined]
    r = c.get("/v1/interactions/i-1/stream")
    assert r.status_code == 404
    assert r.json()["code"] == "BUCKET_NOT_FOUND"


# ---- /stream happy path ----

def test_stream_happy_path_shape(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "small content")
    c.put("/v1/interactions/i-1", json={"rsm_enabled": True, "selected_bucket_id": bid})

    r = c.get(
        "/v1/interactions/i-1/stream",
        params={"budget_unit": "characters", "budget_value": 1000},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")

    body = r.json()
    assert body["source"] == "rsm"
    assert body["schema_version"] == "1"
    assert body["interaction_id"] == "i-1"
    assert body["bucket_id"] == bid
    # Replay envelope invariants (V1 §14).
    rep = body["replay"]
    assert rep["source"] == "rsm"
    assert rep["bucket_id"] == bid
    assert rep["integrity"]["algorithm"] == "sha256"
    assert len(rep["integrity"]["value"]) == 64
    assert rep["provenance"]["origin"] == "text"
    # Snapshot invariants (V2 §3-§5).
    snap = body["snapshot"]
    assert snap["schema_version"] == "1"
    assert snap["bucket_id"] == bid
    assert snap["content"]["kind"] == "preserved"
    assert snap["content"]["text"] == "small content"
    assert snap["integrity"]["algorithm"] == "sha256"


def test_stream_marks_last_streamed_at(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "doc")
    c.put("/v1/interactions/i-1", json={"rsm_enabled": True, "selected_bucket_id": bid})
    before = c.get("/v1/interactions/i-1").json()
    assert before["last_streamed_at"] is None
    assert c.get("/v1/interactions/i-1/stream").status_code == 200
    after = c.get("/v1/interactions/i-1").json()
    assert after["last_streamed_at"] is not None


# ---- /replay and /snapshot opt-in gating ----

def test_replay_without_interaction_id_is_legacy(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "doc")
    # No interaction_id supplied — legacy V1/V2 behaviour.
    r = c.get(f"/v1/buckets/{bid}/replay")
    assert r.status_code == 200
    assert r.json()["source"] == "rsm"


def test_replay_with_disabled_interaction_rejected(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "doc")
    c.put("/v1/interactions/i-1", json={"rsm_enabled": False})
    r = c.get(f"/v1/buckets/{bid}/replay", params={"interaction_id": "i-1"})
    assert r.status_code == 409
    assert r.json()["code"] == "RSM_DISABLED"


def test_snapshot_with_unknown_interaction_rejected(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "doc")
    r = c.get(
        f"/v1/buckets/{bid}/snapshot",
        params={"interaction_id": "i-unknown"},
    )
    assert r.status_code == 409
    assert r.json()["code"] == "RSM_DISABLED"


def test_snapshot_without_interaction_id_is_legacy(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "doc")
    r = c.get(f"/v1/buckets/{bid}/snapshot")
    assert r.status_code == 200
    assert r.json()["bucket_id"] == bid


# ---- interaction isolation ----

def test_interaction_isolation(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    ba = _ingest(c, "A content")
    bb = _ingest(c, "B content")
    c.put("/v1/interactions/i-A", json={"rsm_enabled": True, "selected_bucket_id": ba})
    c.put("/v1/interactions/i-B", json={"rsm_enabled": True, "selected_bucket_id": bb})

    rA = c.get("/v1/interactions/i-A/stream").json()
    rB = c.get("/v1/interactions/i-B/stream").json()

    assert rA["bucket_id"] == ba
    assert rA["snapshot"]["content"]["text"] == "A content"
    assert rB["bucket_id"] == bb
    assert rB["snapshot"]["content"]["text"] == "B content"
    assert rA["bucket_id"] != rB["bucket_id"]


def test_interaction_isolation_disabled_a_cannot_read_b(tmp_path, monkeypatch):
    """A single disabled interaction cannot read another interaction's data."""
    c = _client(tmp_path, monkeypatch)
    ba = _ingest(c, "A content")
    bb = _ingest(c, "B content")
    c.put("/v1/interactions/i-A", json={"rsm_enabled": False, "selected_bucket_id": ba})
    c.put("/v1/interactions/i-B", json={"rsm_enabled": True, "selected_bucket_id": bb})
    r = c.get("/v1/interactions/i-A/stream")
    assert r.status_code == 409
    # And naming i-A on /replay for Bucket B is still gated.
    r2 = c.get(f"/v1/buckets/{bb}/replay", params={"interaction_id": "i-A"})
    assert r2.status_code == 409
    assert r2.json()["code"] == "RSM_DISABLED"


# ---- source revision chain (ADR 0012) ----

def test_source_revision_new_bucket_delivered(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    # Original Bucket A.
    ba = _ingest(c, "original source")
    hashA = c.get(f"/v1/buckets/{ba}").json()["bucket"]["hash"]["value"]
    c.put("/v1/interactions/i-1", json={"rsm_enabled": True, "selected_bucket_id": ba})
    s1 = c.get("/v1/interactions/i-1/stream").json()
    assert s1["bucket_id"] == ba
    assert s1["snapshot"]["content"]["text"] == "original source"
    # User correction: ingest a NEW Bucket B (A is not mutated).
    bb = _ingest(c, "corrected source")
    hashB = c.get(f"/v1/buckets/{bb}").json()["bucket"]["hash"]["value"]
    assert hashA != hashB
    # Select B on the same interaction, re-stream.
    c.put("/v1/interactions/i-1", json={"selected_bucket_id": bb})
    s2 = c.get("/v1/interactions/i-1/stream").json()
    assert s2["bucket_id"] == bb
    assert s2["snapshot"]["content"]["text"] == "corrected source"
    # A is still intact.
    assert c.get(f"/v1/buckets/{ba}").json()["bucket"]["hash"]["value"] == hashA


# ---- repeated replay / manual Replay ----

def test_repeated_stream_is_idempotent_in_payload(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "stable")
    c.put("/v1/interactions/i-1", json={"rsm_enabled": True, "selected_bucket_id": bid})
    a = c.get("/v1/interactions/i-1/stream").json()
    b = c.get("/v1/interactions/i-1/stream").json()
    # snapshot_id and created_at change per build, but bucket content + integrity do not.
    assert a["bucket_id"] == b["bucket_id"]
    assert a["replay"]["integrity"]["value"] == b["replay"]["integrity"]["value"]
    assert a["snapshot"]["content"]["text"] == b["snapshot"]["content"]["text"]
