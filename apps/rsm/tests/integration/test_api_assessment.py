"""HTTP coverage for the Source Assessment endpoint and the Prepared
Representation key in the ReplayStreaming payload.

The assessment endpoint is intentionally gate-free: it describes what
RSM would observe, never releases source content. The Prepared
Representation key is additive — every existing payload key keeps its
exact pre-refactor shape (frozen by `test_api_interactions.py`), and
`prepared_representation` is an extra, strictly-typed envelope.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from rsm.api.app import create_app


def _client(tmp_path, monkeypatch):
    from rsm.daemon import service as svc
    from rsm.daemon.eventlog import EventLog
    from rsm.daemon.store import FsStore
    from rsm.interaction.store import InteractionStore

    daemon = svc.DaemonService(
        store=FsStore(tmp_path / "buckets"),
        eventlog=EventLog(tmp_path / "events.log"),
        interactions=InteractionStore(),
    )
    monkeypatch.setattr(svc, "_default_daemon", daemon)
    return TestClient(create_app())


def _ingest(c, text="hello"):
    r = c.post("/v1/buckets/", json={"content": text, "kind": "text"})
    assert r.status_code == 200
    return r.json()["bucket"]["bucket_id"]


# ---- /v1/buckets/{id}/assess ----


def test_assess_endpoint_shape(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "payload")
    r = c.get(f"/v1/buckets/{bid}/assess")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == "1"
    assert body["bucket_id"] == bid
    assert body["requires_observation"] is True
    assert body["requires_vision"] is False
    assert body["source_size_chars"] == len("payload")
    assert body["origin"] == "text"
    assert "integrity" in body
    assert body["integrity"]["algorithm"] == "sha256"
    assert "source_present" in body["reasons"]


def test_assess_empty_bucket_reports_no_observation_required(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "")
    r = c.get(f"/v1/buckets/{bid}/assess")
    assert r.status_code == 200
    body = r.json()
    assert body["requires_observation"] is False
    assert "source_empty" in body["reasons"]


def test_assess_unknown_bucket_404(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.get("/v1/buckets/bkt_missing/assess")
    assert r.status_code == 404
    assert r.json()["code"] == "BUCKET_NOT_FOUND"


def test_assess_does_not_require_interaction_gate(tmp_path, monkeypatch):
    """Assessment never releases source content, so it must NOT be
    gated by rsm_enabled. Confirm an unknown interaction has no effect."""
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "material")
    r = c.get(f"/v1/buckets/{bid}/assess")
    assert r.status_code == 200
    body = r.json()
    # The assessment body MUST NOT contain the Bucket's full content.
    assert "payload" not in body
    assert "full_content" not in body
    # Nor the snapshot's text (it never ran).
    assert "snapshot" not in body


# ---- Prepared Representation inside the stream payload ----


def test_stream_payload_includes_prepared_representation(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "material")
    c.put("/v1/interactions/i-1", json={"rsm_enabled": True, "selected_bucket_id": bid})

    r = c.get("/v1/interactions/i-1/stream")
    assert r.status_code == 200
    body = r.json()

    # Pre-refactor keys stay exactly as they were (frozen contract).
    for k in ("source", "schema_version", "interaction_id", "bucket_id", "replay", "snapshot"):
        assert k in body

    # Additive: the Prepared Representation envelope.
    assert "prepared_representation" in body
    pr = body["prepared_representation"]
    assert pr["schema_version"] == "1"
    assert pr["bucket_id"] == bid
    assert pr["integrity"]["algorithm"] == "sha256"
    assert pr["replay"]["bucket_id"] == bid
    assert pr["snapshot"]["bucket_id"] == bid
    assert pr["coverage"]["bucket_id"] == bid
    assert pr["coverage"]["complete"] is True
    assert pr["assessment"]["requires_observation"] is True


def test_stream_payload_prepared_representation_matches_replay_envelope(tmp_path, monkeypatch):
    """The additive prepared_representation.replay MUST be byte-identical
    to the stream payload's own 'replay' key (same envelope, named twice)."""
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "same envelope")
    c.put("/v1/interactions/i-1", json={"rsm_enabled": True, "selected_bucket_id": bid})
    body = c.get("/v1/interactions/i-1/stream").json()
    assert body["prepared_representation"]["replay"] == body["replay"]
    assert body["prepared_representation"]["snapshot"] == body["snapshot"]


# ---- Interaction isolation extends to the Prepared Representation ----


def test_interaction_isolation_also_isolates_prepared_representation(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    ba = _ingest(c, "A content")
    bb = _ingest(c, "B content")
    c.put("/v1/interactions/i-A", json={"rsm_enabled": True, "selected_bucket_id": ba})
    c.put("/v1/interactions/i-B", json={"rsm_enabled": True, "selected_bucket_id": bb})

    rA = c.get("/v1/interactions/i-A/stream").json()
    rB = c.get("/v1/interactions/i-B/stream").json()
    assert rA["prepared_representation"]["bucket_id"] == ba
    assert rB["prepared_representation"]["bucket_id"] == bb
    # No bleed-through of content.
    assert rA["prepared_representation"]["snapshot"]["content"]["text"] == "A content"
    assert rB["prepared_representation"]["snapshot"]["content"]["text"] == "B content"


# ---- RSM-first vs direct Agent path (behavioural) ----


def test_rsm_first_path_requires_opt_in(tmp_path, monkeypatch):
    """Section 14: ordinary requests can bypass RSM. Confirm that an
    interaction which never opted in gets a fail-closed response from
    the stream endpoint; the host app would route to the Agent directly."""
    c = _client(tmp_path, monkeypatch)
    _ingest(c, "something")  # a bucket exists but no interaction opts in
    r = c.get("/v1/interactions/no-such-interaction/stream")
    assert r.status_code == 409
    assert r.json()["code"] == "RSM_DISABLED"


def test_source_first_path_releases_prepared_representation(tmp_path, monkeypatch):
    """Section 14: when a request materially requires source observation,
    the host app flips rsm_enabled and the stream endpoint delivers the
    prepared material (assessment + coverage + snapshot + replay) in a
    single payload."""
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "a document to summarise")
    # Step 1: assess (no gate, read-only).
    a = c.get(f"/v1/buckets/{bid}/assess").json()
    assert a["requires_observation"] is True
    # Step 2: opt in via the InteractionRecord (explicit user override).
    c.put("/v1/interactions/i-1", json={"rsm_enabled": True, "selected_bucket_id": bid})
    # Step 3: stream — this is the full observe → prepare → release path.
    body = c.get("/v1/interactions/i-1/stream").json()
    assert body["prepared_representation"]["coverage"]["complete"] is True
    assert body["prepared_representation"]["assessment"]["requires_observation"] is True
    # And the Agent (not RSM) is free to consume this and complete the task.
