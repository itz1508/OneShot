"""Phase 18 — explicit failure-boundary tests not covered elsewhere."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rsm.api.app import create_app
from rsm.daemon import service as svc
from rsm.daemon.eventlog import EventLog
from rsm.daemon.store import FsStore
from rsm.extraction.text import extract_text
from rsm.integrity.sha256 import sha256_bucket
from rsm.integrity.verify import SuppliedHashMismatch, verify_supplied_hash


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    daemon = svc.DaemonService(
        store=FsStore(tmp_path / "store"),
        eventlog=EventLog(tmp_path / "events.log"),
    )
    monkeypatch.setattr(svc, "_default_daemon", daemon)
    return TestClient(create_app())


def test_folder_missing_rejected(client: TestClient, tmp_path: Path) -> None:
    with pytest.raises(Exception):
        # TestClient re-raises server errors by default.
        client.post(
            "/v1/buckets/",
            json={"kind": "folder", "path": str(tmp_path / "does-not-exist")},
        )
    bl = client.get("/v1/buckets/")
    assert bl.status_code == 200
    assert bl.json()["bucket_ids"] == []


def test_zip_missing_rejected(client: TestClient, tmp_path: Path) -> None:
    with pytest.raises(Exception):
        client.post(
            "/v1/buckets/",
            json={"kind": "zip", "path": str(tmp_path / "nope.zip")},
        )
    bl = client.get("/v1/buckets/")
    assert bl.json()["bucket_ids"] == []


def test_wrong_hash_leaves_no_accepted_bucket(client: TestClient) -> None:
    r = client.post(
        "/v1/buckets/",
        json={"kind": "text", "content": "x", "expected_hash": "0" * 64},
    )
    assert r.status_code == 422
    bl = client.get("/v1/buckets/")
    assert bl.status_code == 200
    assert bl.json()["bucket_ids"] == []


def test_verify_supplied_hash_pure() -> None:
    b = extract_text("verify-pure")
    expected = sha256_bucket(b.model_dump(mode="json"))
    v = verify_supplied_hash(b, expected)
    assert v.integrity_status == "verified"
    assert b.integrity_status == "unverified"
    with pytest.raises(SuppliedHashMismatch):
        verify_supplied_hash(b, "f" * 64)
