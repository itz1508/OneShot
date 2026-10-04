"""Phase 2 — runtime directory boundaries."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from rsm.loading import RuntimeDirError, ensure_runtime_dirs


def test_creates_both_dirs(tmp_path: Path) -> None:
    a = tmp_path / "attachment"
    s = tmp_path / "store"
    ar, sr = ensure_runtime_dirs(attachment_dir=a, store_dir=s)
    assert ar.is_dir()
    assert sr.is_dir()


def test_idempotent(tmp_path: Path) -> None:
    a = tmp_path / "attachment"
    s = tmp_path / "store"
    ensure_runtime_dirs(attachment_dir=a, store_dir=s)
    ensure_runtime_dirs(attachment_dir=a, store_dir=s)
    assert a.is_dir() and s.is_dir()


def test_rejects_same_root(tmp_path: Path) -> None:
    with pytest.raises(RuntimeDirError, match="distinct"):
        ensure_runtime_dirs(attachment_dir=tmp_path, store_dir=tmp_path)


def test_rejects_file_at_dir_path(tmp_path: Path) -> None:
    a = tmp_path / "a"
    a.write_text("not a dir", encoding="utf-8")
    s = tmp_path / "s"
    with pytest.raises(RuntimeDirError, match="not a directory"):
        ensure_runtime_dirs(attachment_dir=a, store_dir=s)
