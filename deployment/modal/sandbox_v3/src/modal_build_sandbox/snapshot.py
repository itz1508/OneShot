"""Deterministic regular-file snapshots and fail-closed nofollow extraction."""

from __future__ import annotations

import hashlib
import os
import stat
import tarfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import cast

from .policy import normalize_path

EXCLUDED = {".git", ".venv", ".state", ".oneshot-state", ".pytest_cache", "__pycache__", "node_modules", ".env"}
MAX_MEMBERS = 20000


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@contextmanager
def _parent_fd(root: Path, path: str, *, create_dirs: bool = False) -> Iterator[tuple[int, str]]:
    normalize_path(path)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = path.split("/")
        for part in parts[:-1]:
            if create_dirs:
                with suppress(FileExistsError):
                    os.mkdir(part, 0o755, dir_fd=fd)
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        yield fd, parts[-1]
    finally:
        os.close(fd)


def secure_read(root: Path, path: str, max_bytes: int = 250 * 1024 * 1024) -> bytes:
    with _parent_fd(root, path) as (fd, name):
        f = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            st = os.fstat(f)
            if not stat.S_ISREG(st.st_mode) or st.st_size > max_bytes:
                raise ValueError("nonregular or oversized input")
            data = bytearray()
            while True:
                chunk = os.read(f, min(65536, max_bytes + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise ValueError("oversized input")
            return bytes(data)
        finally:
            os.close(f)


def secure_write(root: Path, path: str, data: bytes, mode: int = 0o644) -> None:
    """Create regular file, refusing existing links. Caller controls an isolated root."""
    with _parent_fd(root, path, create_dirs=True) as (fd, name):
        tmp = f".sandbox-write-{os.getpid()}-{hashlib.sha256(os.urandom(12)).hexdigest()[:12]}"
        f = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        try:
            with os.fdopen(f, "wb", closefd=False) as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.fchmod(f, mode)
        finally:
            os.close(f)
        try:
            # Fail rather than replace preexisting special files or symlinks.
            try:
                st = os.stat(name, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                if not stat.S_ISREG(st.st_mode):
                    raise ValueError("cannot replace nonregular path")
            os.replace(tmp, name, src_dir_fd=fd, dst_dir_fd=fd)
        except Exception:
            os.unlink(tmp, dir_fd=fd)
            raise


def secure_remove(root: Path, path: str) -> None:
    with _parent_fd(root, path) as (fd, name):
        st = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("cannot remove nonregular path")
        os.unlink(name, dir_fd=fd)


def scan_tree(
    root: Path, *, max_files: int = MAX_MEMBERS, max_bytes: int = 250 * 1024 * 1024
) -> dict[str, dict[str, object]]:
    """Reject links/special files; include every ordinary file and executable-mode identity."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("invalid workspace root")
    out: dict[str, dict[str, object]] = {}
    total = 0
    for base, dirs, files in os.walk(root, followlinks=False):
        for name in dirs:
            p = Path(base) / name
            normalize_path(p.relative_to(root).as_posix())
            if not stat.S_ISDIR(p.lstat().st_mode):
                raise ValueError("nonregular directory")
        for name in files:
            p = Path(base) / name
            rel = normalize_path(p.relative_to(root).as_posix())
            st = p.lstat()
            if not stat.S_ISREG(st.st_mode):
                raise ValueError("nonregular file")
            total += st.st_size
            if len(out) >= max_files or total > max_bytes:
                raise ValueError("snapshot resource limits exceeded")
            data = secure_read(root, rel, max_bytes=max_bytes)
            mode = 0o755 if st.st_mode & 0o111 else 0o644
            out[rel] = {"sha256": hashlib.sha256(data).hexdigest(), "mode": mode, "size": len(data)}
    return out


def tree_digest(snapshot: dict[str, dict[str, object]]) -> str:
    h = hashlib.sha256()
    for p, item in sorted(snapshot.items()):
        h.update(f"{p}\0{item['sha256']}\0{item['mode']}\n".encode())
    return h.hexdigest()


def archive_directory(root: Path, target: Path, *, max_bytes: int = 50 * 1024 * 1024) -> tuple[str, str]:
    root, target = Path(root), Path(target)
    entries = scan_tree(root)
    for rel in entries:
        if any(part in EXCLUDED for part in rel.split("/")):
            raise ValueError("source contains excluded paths")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w", format=tarfile.USTAR_FORMAT) as tar:
        for rel, meta in sorted(entries.items()):
            content = secure_read(root, rel)
            info = tarfile.TarInfo(rel)
            info.size = len(content)
            info.mtime = info.uid = info.gid = 0
            info.mode = cast(int, meta["mode"])
            import io

            tar.addfile(info, io.BytesIO(content))
    if target.stat().st_size > max_bytes:
        target.unlink()
        raise ValueError("archive exceeds limit")
    return sha256_file(target), tree_digest(entries)


def extract_verified_tar(
    src: Path,
    target: Path,
    *,
    archive_digest: str,
    expected_tree_digest: str,
    max_archive_bytes: int = 50 * 1024 * 1024,
    max_extracted_bytes: int = 250 * 1024 * 1024,
) -> dict[str, dict[str, object]]:
    src, target = Path(src), Path(target)
    if src.stat().st_size > max_archive_bytes or sha256_file(src) != archive_digest:
        raise ValueError("archive byte identity mismatch")
    if target.exists() and (target.is_symlink() or any(target.iterdir())):
        raise ValueError("extraction target must be an owned empty directory")
    target.mkdir(parents=True, exist_ok=True)
    seen: set[str] = set()
    total = 0
    with tarfile.open(src, "r:") as tar:
        members = tar.getmembers()
        if len(members) > MAX_MEMBERS:
            raise ValueError("too many archive members")
        for m in members:
            rel = normalize_path(m.name.rstrip("/") if m.isdir() else m.name)
            folded = rel.casefold()
            if folded in seen or (not m.isfile() and not m.isdir()) or m.mode & ~0o755:
                raise ValueError("duplicate, special or unsafe archive member")
            seen.add(folded)
            if m.isdir():
                with _parent_fd(target, rel, create_dirs=True) as (fd, name):
                    with suppress(FileExistsError):
                        os.mkdir(name, 0o755, dir_fd=fd)
                    ck = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    os.close(ck)
                continue
            if (m.mode & 0o222) not in {0o200, 0o220, 0o222} or m.mode & 0o6000:
                raise ValueError("unsafe file permissions")
            total += m.size
            if total > max_extracted_bytes or m.size < 0:
                raise ValueError("extracted content exceeds limit")
            stream = tar.extractfile(m)
            if stream is None:
                raise ValueError("missing member contents")
            with _parent_fd(target, rel, create_dirs=True) as (fd, name):
                output = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
                try:
                    remaining = m.size
                    while remaining:
                        chunk = stream.read(min(65536, remaining))
                        if not chunk:
                            raise ValueError("truncated archive member")
                        os.write(output, chunk)
                        remaining -= len(chunk)
                    os.fchmod(output, 0o755 if m.mode & 0o111 else 0o644)
                finally:
                    os.close(output)
    tree = scan_tree(target, max_bytes=max_extracted_bytes)
    if tree_digest(tree) != expected_tree_digest:
        raise ValueError("extracted-tree identity mismatch")
    return tree
