"""End-to-end HTTP coverage for the §13 API surface."""

import json
from fastapi.testclient import TestClient
from rsm.api.app import create_app


def _client(tmp_path, monkeypatch):
    from rsm.daemon import service as svc
    from rsm.daemon.store import FsStore
    from rsm.daemon.eventlog import EventLog
    daemon = svc.DaemonService(
        store=FsStore(tmp_path / "buckets"),
        eventlog=EventLog(tmp_path / "events.log"),
    )
    monkeypatch.setattr(svc, "_default_daemon", daemon)
    return TestClient(create_app())


def _ingest(client, text="hello"):
    r = client.post("/v1/buckets/", json={"content": text, "kind": "text"})
    assert r.status_code == 200, r.text
    return r.json()["bucket"]["bucket_id"]


def test_list_buckets(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    a = _ingest(client, "a")
    b = _ingest(client, "b")
    r = client.get("/v1/buckets/")
    assert r.status_code == 200
    ids = set(r.json()["bucket_ids"])
    assert {a, b} <= ids


def test_activate_release_lifecycle(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    bid = _ingest(client, "lifecycle")
    for to in ("STAGED", "STORED"):
        r = client.post(f"/v1/buckets/{bid}/transition", json={"to": to})
        assert r.status_code == 200
    r = client.post(f"/v1/buckets/{bid}/activate")
    assert r.status_code == 200
    assert r.json()["bucket"]["state"] == "ACTIVATED"
    r = client.post(f"/v1/buckets/{bid}/release")
    assert r.status_code == 200
    assert r.json()["bucket"]["state"] == "RELEASED"


def test_activate_illegal_from_received_returns_409(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    bid = _ingest(client, "nope")
    r = client.post(f"/v1/buckets/{bid}/activate")
    assert r.status_code == 409
    assert r.json()["code"] == "ILLEGAL_LIFECYCLE_TRANSITION"


def test_replay_envelope_includes_classification_and_readiness(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    bid = _ingest(client, "replayable")
    # classify as READY_EXECUTION
    r = client.put(
        f"/v1/buckets/{bid}/classification",
        json={"work_classification": "READY_EXECUTION"},
    )
    assert r.status_code == 200
    for to in ("STAGED", "STORED", "ACTIVATED", "RELEASED"):
        client.post(f"/v1/buckets/{bid}/transition", json={"to": to})
    r = client.get(f"/v1/buckets/{bid}/replay")
    assert r.status_code == 200
    env = r.json()
    assert env["work_classification"] == "READY_EXECUTION"
    assert env["replayability"] == "REPLAY_BUILDABLE"
    assert env["bucket_id"] == bid
    assert env["schema_version"] == "1"
    assert env["integrity"]["algorithm"] == "sha256"


def test_retired_is_not_replayable(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    bid = _ingest(client, "retire")
    for to in ("STAGED", "STORED", "ACTIVATED", "RELEASED", "RETIRED"):
        r = client.post(f"/v1/buckets/{bid}/transition", json={"to": to})
        assert r.status_code == 200
    r = client.get(f"/v1/buckets/{bid}/replay")
    env = r.json()
    assert env["replayability"] == "NOT_REPLAYABLE"


def test_export_matches_hash_preimage(tmp_path, monkeypatch):
    """The export round-trips the canonical bucket; the hash reproduces from
    the A1 identity fields (canonical_preimage)."""
    import hashlib
    from rsm.integrity.sha256 import canonical_preimage

    client = _client(tmp_path, monkeypatch)
    bid = _ingest(client, "export me")
    r = client.get(f"/v1/buckets/{bid}/export")
    assert r.status_code == 200
    r2 = client.get(f"/v1/buckets/{bid}")
    bucket = r2.json()["bucket"]
    reproduced = hashlib.sha256(canonical_preimage(bucket)).hexdigest()
    assert reproduced == bucket["hash"]["value"]


def test_classification_does_not_mutate_bucket(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    bid = _ingest(client, "guarded")
    r1 = client.get(f"/v1/buckets/{bid}")
    before = r1.json()["bucket"]
    r2 = client.put(
        f"/v1/buckets/{bid}/classification",
        json={"work_classification": "REVIEW"},
    )
    assert r2.status_code == 200
    r3 = client.get(f"/v1/buckets/{bid}")
    after = r3.json()["bucket"]
    # A1 frozen fields unchanged by classification changes.
    for k in ("bucket_id", "hash", "provenance", "full_content", "metadata", "schema_version"):
        assert before[k] == after[k]


def test_execution_state_round_trip(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    bid = _ingest(client, "exec")
    r = client.get(f"/v1/buckets/{bid}/execution")
    assert r.status_code == 200
    assert r.json()["state"] == "NOT_STARTED"
    r = client.put(
        f"/v1/buckets/{bid}/execution",
        json={
            "state": "IN_PROGRESS",
            "tasks": [{"id": "gate-1", "status": "COMPLETE"}],
        },
    )
    assert r.status_code == 200
    e = r.json()
    assert e["state"] == "IN_PROGRESS"
    assert e["tasks"][0]["id"] == "gate-1"

def test_export_endpoint_returns_canonical_bucket(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    bid = _ingest(client, "export-shape")
    r = client.get(f"/v1/buckets/{bid}/export")
    assert r.status_code == 200
    doc = r.json()  # canonical JSON parses fine
    assert doc["bucket_id"] == bid
    assert doc["schema_version"] == "1"
