"""Unit tests for rsm.reader — SCAN + Reader + ReaderTrace invariants."""

from pathlib import Path

from rsm.extraction.folder import extract_folder
from rsm.extraction.text import extract_text
from rsm.reader import (
    FileAvailability,
    FileType,
    ReaderEventKind,
    ReaderMethod,
    ReaderStatus,
    read_bucket,
    scan_bucket,
)


# ---- SCAN ----

def test_scan_simple_text_bucket_single_file():
    b = extract_text("hello world", source_uri="demo.txt")
    s = scan_bucket(b)
    assert s.bucket_id == b.bucket_id
    assert len(s.files) == 1
    f = s.files[0]
    assert f.index == 1
    assert f.file_id.endswith(":f1")
    assert f.file_type == FileType.TEXT
    assert f.availability == FileAvailability.READABLE
    assert f.size_bytes == len("hello world".encode("utf-8"))


def test_scan_is_deterministic():
    b = extract_text("same input")
    f1 = [f.model_dump() for f in scan_bucket(b).files]
    f2 = [f.model_dump() for f in scan_bucket(b).files]
    assert f1 == f2


def test_scan_folder_enumerates_entries(tmp_path: Path):
    root = tmp_path / "r"
    root.mkdir()
    (root / "a.md").write_text("# a")
    (root / "b.txt").write_text("b content")
    (root / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")   # opaque
    (root / "weird.xyz").write_text("whatever")              # unsupported
    res = extract_folder(root)
    parent = res.parent
    s = scan_bucket(parent)
    names = [f.name for f in s.files]
    assert sorted(names) == sorted(["a.md", "b.txt", "image.png", "weird.xyz"])
    # indexing is 1-based and dense:
    assert [f.index for f in s.files] == [1, 2, 3, 4]
    by_name = {f.name: f for f in s.files}
    assert by_name["a.md"].availability == FileAvailability.READABLE
    assert by_name["b.txt"].availability == FileAvailability.READABLE
    assert by_name["image.png"].availability == FileAvailability.OPAQUE
    assert by_name["weird.xyz"].availability == FileAvailability.UNREADABLE


# ---- Reader ----

def test_reader_simple_text_observes_one_file():
    b = extract_text("hello world")
    r = read_bucket(b)
    assert len(r.events) == 1
    ev = r.events[0]
    assert ev.kind == ReaderEventKind.FILE_OBSERVED
    assert ev.method == ReaderMethod.TEXT
    assert ev.observed_bytes == len("hello world".encode("utf-8"))
    t = r.trace
    assert t.discovered == 1
    assert t.latest_index == 1
    assert t.observed_count == 1
    assert t.failed_count == 0
    assert t.complete is True
    assert t.failures == []


def test_reader_folder_one_file_failure_does_not_fail_whole_read(tmp_path: Path):
    root = tmp_path / "r"
    root.mkdir()
    (root / "a.md").write_text("# a")
    (root / "b.txt").write_text("b")
    (root / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (root / "weird.xyz").write_text("x")
    res = extract_folder(root)
    r = read_bucket(res.parent)
    # ONE event per discovered File — isolation invariant.
    assert len(r.events) == len(r.trace.coverage) == 4
    # Reader kept going despite the two failures.
    assert r.trace.latest_index == 4
    assert r.trace.observed_count == 2
    assert r.trace.failed_count == 2
    assert r.trace.complete is True
    # Failures are per-file_id and keep the readable successes valid.
    reasons = {f.reason for f in r.trace.failures}
    assert reasons == {"vision_unavailable", "unsupported_extension"}
    statuses = {c.status for c in r.trace.coverage}
    assert ReaderStatus.OBSERVED in statuses
    assert ReaderStatus.FAILED in statuses


def test_reader_does_not_mutate_bucket():
    b = extract_text("don\'t touch me")
    before = b.model_dump(mode="json")
    _ = read_bucket(b)
    assert b.model_dump(mode="json") == before
    assert b.hash.value == before["hash"]["value"]


def test_reader_latest_index_increases_monotonically(tmp_path: Path):
    root = tmp_path / "r"
    root.mkdir()
    for i in range(5):
        (root / f"a{i}.txt").write_text(str(i))
    res = extract_folder(root)
    r = read_bucket(res.parent)
    # Events are emitted in Scan order; latest_index after N events is N.
    for i, ev in enumerate(r.events, start=1):
        assert ev.index == i
    assert r.trace.latest_index == 5
