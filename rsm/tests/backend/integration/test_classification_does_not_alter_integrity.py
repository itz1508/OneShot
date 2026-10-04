"""Changing classification MUST NOT change the bucket hash (A1 invariant)."""

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


def test_classification_change_leaves_hash_identical(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    bid = client.post("/v1/buckets/", json={"content": "guarded"}).json()["bucket"]["bucket_id"]
    h0 = client.get(f"/v1/buckets/{bid}").json()["bucket"]["hash"]["value"]
    for cls in ("STORE", "REVIEW", "REVIEW_TODO", "READY_EXECUTION"):
        client.put(
            f"/v1/buckets/{bid}/classification",
            json={"work_classification": cls},
        )
        assert client.get(f"/v1/buckets/{bid}").json()["bucket"]["hash"]["value"] == h0


def test_execution_change_leaves_hash_identical(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    bid = client.post("/v1/buckets/", json={"content": "guarded"}).json()["bucket"]["bucket_id"]
    h0 = client.get(f"/v1/buckets/{bid}").json()["bucket"]["hash"]["value"]
    client.put(
        f"/v1/buckets/{bid}/execution",
        json={
            "state": "IN_PROGRESS",
            "tasks": [{"id": "t1", "status": "COMPLETE"}],
        },
    )
    assert client.get(f"/v1/buckets/{bid}").json()["bucket"]["hash"]["value"] == h0


def test_lifecycle_transition_leaves_hash_identical(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    bid = client.post("/v1/buckets/", json={"content": "same identity"}).json()["bucket"]["bucket_id"]
    h0 = client.get(f"/v1/buckets/{bid}").json()["bucket"]["hash"]["value"]
    for to in ("STAGED", "STORED", "ACTIVATED", "RELEASED", "RETIRED"):
        client.post(f"/v1/buckets/{bid}/transition", json={"to": to})
        assert client.get(f"/v1/buckets/{bid}").json()["bucket"]["hash"]["value"] == h0
