"""Phase 8 — multi-origin ingest dispatcher via DaemonService + HTTP router."""
from __future__ import annotations

import base64
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rsm.api.app import create_app
from rsm.daemon import service as svc
from rsm.daemon.eventlog import EventLog
from rsm.daemon.store import FsStore


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    daemon = svc.DaemonService(
        store=FsStore(tmp_path / "store"),
        eventlog=EventLog(tmp_path / "events.log"),
    )
    monkeypatch.setattr(svc, "_default_daemon", daemon)
    return TestClient(create_app())


def test_ingest_text(client: TestClient) -> None:
    r = client.post("/v1/buckets/", json={"kind": "text", "content": "hi"})
    assert r.status_code == 200, r.text
    assert r.json()["bucket"]["provenance"]["origin"] == "text"


def test_ingest_markdown(client: TestClient) -> None:
    r = client.post("/v1/buckets/", json={"kind": "markdown", "content": "# hello"})
    assert r.status_code == 200, r.text
    assert r.json()["bucket"]["provenance"]["origin"] == "markdown"


def test_ingest_opaque(client: TestClient) -> None:
    data = base64.b64encode(b"\x00\x01\x02").decode()
    r = client.post(
        "/v1/buckets/",
        json={"kind": "opaque", "content_base64": data, "filename": "blob.bin"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["bucket"]["provenance"]["origin"] == "opaque"


def test_ingest_folder(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "folder"
    root.mkdir()
    (root / "a.txt").write_text("A", encoding="utf-8")
    (root / "b.md").write_text("# B", encoding="utf-8")
    r = client.post("/v1/buckets/", json={"kind": "folder", "path": str(root)})
    assert r.status_code == 200, r.text
    parent_id = r.json()["bucket"]["bucket_id"]
    r = client.get("/v1/buckets/")
    assert r.status_code == 200
    ids = r.json()["bucket_ids"]
    assert parent_id in ids
    assert len(ids) >= 3  # parent + 2 children


def test_ingest_zip(client: TestClient, tmp_path: Path) -> None:
    zp = tmp_path / "pack.zip"
    with zipfile.ZipFile(zp, "w") as zf:
        zf.writestr("docs/readme.md", "# hello")
        zf.writestr("notes.txt", "note")
    r = client.post("/v1/buckets/", json={"kind": "zip", "path": str(zp)})
    assert r.status_code == 200, r.text
    parent = r.json()["bucket"]
    assert parent["metadata"]["archive_kind"] == "zip"
    assert parent["metadata"]["entry_count"] == 2


def test_ingest_rejects_wrong_hash(client: TestClient) -> None:
    r = client.post(
        "/v1/buckets/",
        json={"kind": "text", "content": "x", "expected_hash": "0" * 64},
    )
    assert r.status_code == 422, r.text
    body = r.json()
    # HTTPException wraps the dict under `detail`
    assert body["detail"]["code"] == "HASH_MISMATCH"


def test_unsupported_kind(client: TestClient) -> None:
    r = client.post("/v1/buckets/", json={"kind": "nope"})
    assert r.status_code == 400, r.text
