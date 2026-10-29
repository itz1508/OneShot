"""Independent byte-level expectations for local scanning and admission."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from scanner import AdmittedSource, ScanRejected, admit_file, inspect_text


def test_file_admission_and_exact_repeated_line_offsets(tmp_path: Path) -> None:
    raw = b"keep\nowner approval required\nkeep\n7 days\n30 days\n"
    (tmp_path / "source.txt").write_bytes(raw)
    admitted = admit_file(trusted_root=tmp_path, relative_name="source.txt", source_id="s1")
    result = inspect_text(admitted)
    assert result["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result["byte_span"] == {"start": 0, "end": len(raw)}
    assert result["findings"] == [{"kind": "exact_repeated_line", "byte_spans": [[0, 4], [29, 33]]}]
    assert "7 days" in result["content"] and "30 days" in result["content"]
    assert result["complete_source"] is True
    assert (tmp_path / "source.txt").read_bytes() == raw


def test_non_equivalent_lines_are_not_declared_duplicates() -> None:
    raw = b"10 MB\n10 MB allowed only after approval\n"
    admitted = AdmittedSource("s1", "doc.txt", raw, hashlib.sha256(raw).hexdigest())
    assert inspect_text(admitted)["findings"] == []


def test_partial_utf8_and_exact_byte_span() -> None:
    raw = "alpha\néclair\n".encode()
    admitted = AdmittedSource("s1", "doc.txt", raw, hashlib.sha256(raw).hexdigest())
    result = inspect_text(admitted, start_byte=6, max_bytes=7)
    assert result["content"] == "éclair"
    assert result["byte_span"] == {"start": 6, "end": 13}
    assert result["complete_source"] is False
    assert result["findings"] == []
    with pytest.raises(ScanRejected, match="UTF-8"):
        inspect_text(admitted, start_byte=7, max_bytes=5)


def test_modified_snapshot_rejected() -> None:
    raw = b"original"
    source = AdmittedSource("s1", "doc", raw, hashlib.sha256(raw).hexdigest())
    with pytest.raises(ScanRejected, match="fingerprint"):
        inspect_text(replace(source, content=b"modified"))
    with pytest.raises(ScanRejected, match="fingerprint"):
        inspect_text(source, expected_sha256="0" * 64)


@pytest.mark.parametrize("bad", ["../secret", "/etc/passwd", "a/../b", "a\\b", "a//b", "a/./b", "C:/private", "./a", ""])
def test_untrusted_paths_rejected(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ScanRejected):
        admit_file(trusted_root=tmp_path, relative_name=bad, source_id="s1")


def test_symlink_rejected(tmp_path: Path) -> None:
    inside = tmp_path / "inside"
    inside.mkdir()
    (inside / "real.txt").write_text("private", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(inside / "real.txt")
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(ScanRejected, match="Linked"):
        admit_file(trusted_root=tmp_path, relative_name="link.txt", source_id="s1")


def test_empty_file_and_zero_length_slice(tmp_path: Path) -> None:
    (tmp_path / "empty").write_bytes(b"")
    result = inspect_text(admit_file(trusted_root=tmp_path, relative_name="empty", source_id="empty"))
    assert result["content"] == ""
    assert result["byte_span"] == {"start": 0, "end": 0}
    assert result["complete_source"] is True


def test_large_source_rejected(tmp_path: Path) -> None:
    (tmp_path / "large").write_bytes(b"x" * 1_000_001)
    with pytest.raises(ScanRejected, match="size limit"):
        admit_file(trusted_root=tmp_path, relative_name="large", source_id="s1")


def test_malformed_args_and_excerpts() -> None:
    raw = b"abc"
    source = AdmittedSource("s1", "doc", raw, hashlib.sha256(raw).hexdigest())
    for attrs in ({"start_byte": -1}, {"start_byte": 4}, {"max_bytes": -1}, {"max_bytes": 64001}, {"start_byte": True}):
        with pytest.raises(ScanRejected):
            inspect_text(source, **attrs)
    assert inspect_text(source, max_bytes=2)["limitations"]


def test_repeated_lines_bounded_and_disclosed() -> None:
    raw = b"repeat\n" * 1000
    source = AdmittedSource("s1", "doc", raw, hashlib.sha256(raw).hexdigest())
    result = inspect_text(source)
    assert len(result["findings"]) == 1
    assert len(result["findings"][0]["byte_spans"]) == 16
    assert any("bounded" in text for text in result["limitations"])
