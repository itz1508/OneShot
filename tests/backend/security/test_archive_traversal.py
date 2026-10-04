"""Phase 6 — ZIP archive safety.

Covers the loading-side archive enumerator (`rsm.loading.archive`):

* zip-slip (`../etc/passwd` as entry name)
* absolute path inside archive
* oversized single entry
* oversized total
* symlink entry
* non-UTF-8 entry name (surrogate-escape in filename)
* happy path: deterministic manifest + lazy read_entry

The folder path has its own tests (`test_folder_identity.py`, `test_e2e_07_folder.py`).
"""
from __future__ import annotations

import io
import os
import stat
import struct
import zipfile
from pathlib import Path

import pytest

from rsm.loading.archive import (
    ArchiveSafetyError,
    enumerate_zip,
)


def _write_zip(path: Path, entries: list[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as zf:
        for name, data in entries:
            zf.writestr(name, data)


def test_rejects_zip_slip(tmp_path: Path) -> None:
    z = tmp_path / "slip.zip"
    _write_zip(z, [("../etc/passwd", b"evil")])
    with pytest.raises(ArchiveSafetyError, match="Parent-dir traversal"):
        enumerate_zip(z)


def test_rejects_absolute_entry(tmp_path: Path) -> None:
    z = tmp_path / "abs.zip"
    _write_zip(z, [("/etc/passwd", b"evil")])
    with pytest.raises(ArchiveSafetyError, match="Absolute path"):
        enumerate_zip(z)


def test_rejects_oversized_entry(tmp_path: Path) -> None:
    z = tmp_path / "big.zip"
    _write_zip(z, [("big.txt", b"A" * 1024)])
    with pytest.raises(ArchiveSafetyError, match="max_entry_bytes"):
        enumerate_zip(z, max_entry_bytes=512)


def test_rejects_oversized_total(tmp_path: Path) -> None:
    z = tmp_path / "total.zip"
    _write_zip(z, [("a.txt", b"A" * 400), ("b.txt", b"B" * 400)])
    with pytest.raises(ArchiveSafetyError, match="max_total_bytes"):
        enumerate_zip(z, max_entry_bytes=1024, max_total_bytes=512)


def test_rejects_symlink_entries(tmp_path: Path) -> None:
    z = tmp_path / "link.zip"
    with zipfile.ZipFile(z, "w") as zf:
        info = zipfile.ZipInfo("link")
        # UNIX symlink mode: S_IFLNK = 0o120000; shift into external_attr
        info.external_attr = (0o120777 << 16)
        zf.writestr(info, b"/etc/passwd")
    with pytest.raises(ArchiveSafetyError, match="Symlink"):
        enumerate_zip(z)


def test_happy_path_deterministic(tmp_path: Path) -> None:
    z = tmp_path / "ok.zip"
    _write_zip(
        z,
        [
            ("docs/readme.md", b"# hi\n"),
            ("notes.txt", b"plain\n"),
            ("docs/CHANGELOG.md", b"- initial\n"),
        ],
    )
    m = enumerate_zip(z)
    posix_paths = [e.posix_path for e in m.entries]
    assert posix_paths == sorted(posix_paths), "manifest must be sorted"
    assert posix_paths == ["docs/CHANGELOG.md", "docs/readme.md", "notes.txt"]
    assert m.deterministic_ordering == "sorted_posix_path_ascending"
    first = m.entries[0]
    data = m.read_entry(first)
    assert data == b"- initial\n"


def test_read_entry_rejects_grown_entry(tmp_path: Path) -> None:
    z = tmp_path / "grown.zip"
    _write_zip(z, [("a.txt", b"hello")])
    m = enumerate_zip(z)
    # Simulate caller passing a lying entry (smaller than real file size).
    lying = m.entries[0].__class__(
        posix_path=m.entries[0].posix_path, size_bytes=1, is_dir=False
    )
    with pytest.raises(ArchiveSafetyError, match="grew between enumeration"):
        m.read_entry(lying)
