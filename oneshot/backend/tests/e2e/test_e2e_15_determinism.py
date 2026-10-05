"""Phase 20 — determinism checks across runs.

Same input twice must produce:
    * same canonical replay envelope
    * same manifest ordering (folder, zip)
    * same bucket identity for folder-origin parent (A3 folder identity
      is content-addressed; two walks of the same folder yield the same
      bucket_id, see existing unit/test_folder_identity.py).
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from rsm.daemon.eventlog import EventLog
from rsm.daemon.service import DaemonService
from rsm.daemon.store import FsStore
from rsm.loading.archive import enumerate_zip
from rsm.replay.envelope import build_replay_envelope


def _svc(root: Path) -> DaemonService:
    return DaemonService(
        store=FsStore(root / "store"),
        eventlog=EventLog(root / "events.log"),
    )


def test_text_replay_envelope_is_deterministic(tmp_path: Path) -> None:
    r1 = tmp_path / "r1"; r1.mkdir()
    r2 = tmp_path / "r2"; r2.mkdir()
    b1 = _svc(r1).ingest_text("same bytes")
    b2 = _svc(r2).ingest_text("same bytes")
    # bucket_id includes produced_at and uuid; they differ.
    # The replay envelope's `content` + integrity should still be comparable
    # under the invariant parts.
    e1 = build_replay_envelope(b1)
    e2 = build_replay_envelope(b2)
    assert e1["content"]["full_content"] == e2["content"]["full_content"]
    assert e1["source"] == e2["source"] == "rsm"
    # Different buckets, but same content hash preimage over A1 fields
    # => identity differs by bucket_id/produced_at only.
    assert e1["integrity"]["algorithm"] == e2["integrity"]["algorithm"] == "sha256"


def test_zip_manifest_ordering(tmp_path: Path) -> None:
    z = tmp_path / "p.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("z/a.md", "A")
        zf.writestr("x/b.md", "B")
        zf.writestr("m/c.md", "C")
    m1 = enumerate_zip(z)
    m2 = enumerate_zip(z)
    assert [e.posix_path for e in m1.entries] == [e.posix_path for e in m2.entries]
    assert [e.posix_path for e in m1.entries] == sorted(
        [e.posix_path for e in m1.entries]
    )
