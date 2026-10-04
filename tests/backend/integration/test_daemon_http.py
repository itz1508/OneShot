"""HTTP transport sanity using FastAPI TestClient."""

from fastapi.testclient import TestClient
from rsm.api.app import create_app


def test_healthz():
    app = create_app()
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["schema_version"] == "1"


def test_ingest_and_read_round_trip(tmp_path, monkeypatch):
    from rsm.daemon import service as svc
    from rsm.daemon.store import FsStore
    from rsm.daemon.eventlog import EventLog
    daemon = svc.DaemonService(
        store=FsStore(tmp_path / "buckets"),
        eventlog=EventLog(tmp_path / "events.log"),
    )
    monkeypatch.setattr(svc, "_default_daemon", daemon)

    app = create_app()
    client = TestClient(app)

    r = client.post("/v1/buckets/", json={"content": "hello", "kind": "text"})
    assert r.status_code == 200, r.text
    bid = r.json()["bucket"]["bucket_id"]

    r2 = client.get(f"/v1/buckets/{bid}")
    assert r2.status_code == 200
    assert r2.json()["bucket"]["full_content"] == "hello"
