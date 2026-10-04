"""Phase 4/5 — attachment staging + supplied-hash capture."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from rsm.loading import stage_attachment_bytes, stage_attachment_path
from rsm.loading.attachment import AttachmentError


def test_stage_bytes_returns_record(tmp_path: Path) -> None:
    data = b"hello"
    rec = stage_attachment_bytes(data, original_name="h.txt", attachment_dir=tmp_path)
    assert rec.path.exists()
    assert rec.path.read_bytes() == data
    assert rec.size_bytes == len(data)
    assert rec.content_sha256 == hashlib.sha256(data).hexdigest()
    assert rec.supplied_sha256 is None


def test_stage_bytes_matches_supplied_hash(tmp_path: Path) -> None:
    data = b"hi"
    expected = hashlib.sha256(data).hexdigest()
    rec = stage_attachment_bytes(
        data, original_name="h.txt",
        supplied_sha256=expected, attachment_dir=tmp_path,
    )
    assert rec.supplied_sha256 == expected


def test_stage_bytes_rejects_wrong_hash(tmp_path: Path) -> None:
    with pytest.raises(AttachmentError, match="Supplied SHA-256 does not match"):
        stage_attachment_bytes(
            b"hi", original_name="h.txt",
            supplied_sha256="0" * 64, attachment_dir=tmp_path,
        )


def test_stage_is_deterministic(tmp_path: Path) -> None:
    r1 = stage_attachment_bytes(b"xx", original_name="a.txt", attachment_dir=tmp_path)
    r2 = stage_attachment_bytes(b"xx", original_name="a.txt", attachment_dir=tmp_path)
    assert r1.path == r2.path
    assert r1.content_sha256 == r2.content_sha256


def test_stage_distinct_bytes_distinct_paths(tmp_path: Path) -> None:
    r1 = stage_attachment_bytes(b"xx", original_name="a.txt", attachment_dir=tmp_path)
    r2 = stage_attachment_bytes(b"yy", original_name="a.txt", attachment_dir=tmp_path)
    assert r1.path != r2.path
    assert r1.content_sha256 != r2.content_sha256


def test_stage_path_round_trip(tmp_path: Path) -> None:
    f = tmp_path / "input.txt"
    f.write_bytes(b"PATH")
    attach = tmp_path / "attachment"
    rec = stage_attachment_path(f, attachment_dir=attach)
    assert rec.path.read_bytes() == b"PATH"
    assert rec.original_name == "input.txt"


def test_stage_path_requires_file(tmp_path: Path) -> None:
    with pytest.raises(AttachmentError, match="does not exist"):
        stage_attachment_path(tmp_path / "nope.txt", attachment_dir=tmp_path)
    d = tmp_path / "d"
    d.mkdir()
    with pytest.raises(AttachmentError, match="not a regular file"):
        stage_attachment_path(d, attachment_dir=tmp_path)
