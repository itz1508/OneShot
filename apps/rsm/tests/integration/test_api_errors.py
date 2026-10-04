"""Structured error path coverage (spec §13)."""

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


def test_read_unknown_bucket_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.get("/v1/buckets/bkt_nope")
    assert r.status_code == 404
    body = r.json()
    assert body["code"] == "BUCKET_NOT_FOUND"
    assert body["details"]["bucket_id"] == "bkt_nope"


def test_prov_unknown_bucket_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.get("/v1/prov/bkt_nope")
    assert r.status_code == 404
    assert r.json()["code"] == "BUCKET_NOT_FOUND"


def test_replay_unknown_bucket_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.get("/v1/buckets/bkt_nope/replay")
    assert r.status_code == 404


def test_export_unknown_bucket_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.get("/v1/buckets/bkt_nope/export")
    assert r.status_code == 404


def test_classification_unknown_bucket_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.get("/v1/buckets/bkt_nope/classification")
    assert r.status_code == 404
    r = client.put(
        "/v1/buckets/bkt_nope/classification",
        json={"work_classification": "REVIEW"},
    )
    assert r.status_code == 404


def test_execution_unknown_bucket_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.get("/v1/buckets/bkt_nope/execution")
    assert r.status_code == 404


def test_illegal_transition_409(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    r = client.post(
        "/v1/buckets/",
        json={"content": "x", "kind": "text"},
    )
    bid = r.json()["bucket"]["bucket_id"]
    # RECEIVED -> ACTIVATED is illegal
    r = client.post(f"/v1/buckets/{bid}/transition", json={"to": "ACTIVATED"})
    assert r.status_code == 409
    assert r.json()["code"] == "ILLEGAL_LIFECYCLE_TRANSITION"
    # Non-existent state value
    r = client.post(f"/v1/buckets/{bid}/transition", json={"to": "NOT_A_STATE"})
    assert r.status_code == 409
