"""HTTP coverage for the Reader endpoints."""

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


def _ingest(c, text="hello"):
    r = c.post("/v1/buckets/", json={"content": text, "kind": "text"})
    assert r.status_code == 200
    return r.json()["bucket"]["bucket_id"]


def test_scan_endpoint_simple_text(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "hi")
    r = c.get(f"/v1/buckets/{bid}/scan")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == "1"
    assert body["bucket_id"] == bid
    assert len(body["files"]) == 1
    assert body["files"][0]["index"] == 1
    assert body["files"][0]["availability"] == "readable"


def test_scan_unknown_bucket_404(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.get("/v1/buckets/bkt_missing/scan")
    assert r.status_code == 404
    assert r.json()["code"] == "BUCKET_NOT_FOUND"


def test_read_endpoint_shape(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "payload")
    r = c.get(f"/v1/buckets/{bid}/reader/read")
    assert r.status_code == 200
    body = r.json()
    assert body["bucket_id"] == bid
    assert isinstance(body["events"], list) and len(body["events"]) == 1
    t = body["trace"]
    assert t["discovered"] == 1
    assert t["latest_index"] == 1
    assert t["observed_count"] == 1
    assert t["complete"] is True
    assert t["failures"] == []


def test_trace_endpoint_only_returns_trace(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "payload")
    r = c.get(f"/v1/buckets/{bid}/reader/trace")
    assert r.status_code == 200
    body = r.json()
    assert "events" not in body
    assert body["bucket_id"] == bid
    assert body["complete"] is True
