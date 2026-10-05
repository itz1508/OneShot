"""HTTP coverage for the Snapshot endpoint (spec §13)."""

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


def _ingest(c, content):
    return c.post("/v1/buckets/", json={"content": content, "kind": "text"}).json()["bucket"]["bucket_id"]


def test_snapshot_preserved_path(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "small content")
    r = c.get(f"/v1/buckets/{bid}/snapshot?budget_unit=characters&budget_value=200")
    assert r.status_code == 200
    s = r.json()
    assert s["bucket_id"] == bid
    assert s["schema_version"] == "1"
    assert s["context_budget"] == {"unit": "characters", "value": 200, "is_hard_limit": True}
    assert s["content"]["kind"] == "preserved"
    assert s["content"]["text"] == "small content"
    assert s["included_sources"] == [bid]
    assert s["reduced_sources"] == []
    assert s["integrity"]["algorithm"] == "sha256"
    assert len(s["integrity"]["value"]) == 64


def test_snapshot_overflow_null_returns_409(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "x" * 500)
    r = c.get(f"/v1/buckets/{bid}/snapshot?budget_unit=characters&budget_value=50")
    assert r.status_code == 409
    assert r.json()["code"] == "SUMMARY_UNAVAILABLE"


def test_snapshot_overflow_prefix_returns_summary(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "y" * 2000)
    r = c.get(f"/v1/buckets/{bid}/snapshot?budget_unit=characters&budget_value=120&reduce=prefix")
    assert r.status_code == 200
    s = r.json()
    assert s["content"]["kind"] == "summary"
    assert s["content"]["summary_provider"] == "prefix"
    assert s["content"]["size_chars"] <= 120
    assert s["reduced_sources"] == [bid]


def test_snapshot_unknown_bucket_404(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.get("/v1/buckets/nope/snapshot")
    assert r.status_code == 404


def test_snapshot_bad_budget_unit_422(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "x")
    r = c.get(f"/v1/buckets/{bid}/snapshot?budget_unit=parsec&budget_value=10")
    assert r.status_code == 422
    assert r.json()["code"] == "INVALID_BUDGET"


def test_snapshot_bad_reduce_422(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "x")
    r = c.get(f"/v1/buckets/{bid}/snapshot?reduce=black_magic")
    assert r.status_code == 422


def test_snapshot_does_not_mutate_bucket(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    bid = _ingest(c, "guard A1")
    before = c.get(f"/v1/buckets/{bid}").json()["bucket"]
    # Build a snapshot (preserved) and a reducing snapshot.
    c.get(f"/v1/buckets/{bid}/snapshot?budget_value=1000")
    c.get(f"/v1/buckets/{bid}/snapshot?budget_value=5&reduce=prefix")
    after = c.get(f"/v1/buckets/{bid}").json()["bucket"]
    for k in ("hash", "full_content", "metadata", "provenance", "bucket_id", "schema_version"):
        assert before[k] == after[k], f"A1 field {k!r} mutated"
