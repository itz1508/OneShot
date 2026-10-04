"""Phase 6 — Archive enumerator (ZIP) producing a deterministic manifest.

A thin, SAFE enumerator over a ZIP archive. Produces the SAME shape as the
folder manifest (``deterministic_ordering = "sorted_posix_path_ascending"``)
and routes under the existing size caps in
:class:`rsm.config.schema.Boundaries`.

Explicitly NOT:

* a general extraction service (does NOT write files to disk unless the
  caller asks),
* a workflow engine,
* a vendor archive handler.

Rejected inputs:

* zip-slip entries (names that start with ``/`` or ``..`` after normalisation),
* oversized entries (``archive_entry_bytes`` cap),
* oversized archive totals (``archive_total_bytes`` cap),
* non-UTF-8 names (we only persist UTF-8 names in the manifest),
* symlink entries (ZIP symlinks are a vector for traversal).

Returns a typed :class:`ArchiveManifest` the loader can hand to the Reader;
each entry's bytes can be fetched lazily via :meth:`read_entry`.
"""

from __future__ import annotations

import io
import os
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable

# Default caps match :class:`rsm.config.schema.Boundaries`; a caller may
# override them via `enumerate_zip(..., max_entry_bytes=, max_total_bytes=)`.
_DEFAULT_MAX_ENTRY_BYTES = 64 * 1024 * 1024
_DEFAULT_MAX_TOTAL_BYTES = 512 * 1024 * 1024
_DEFAULT_MAX_FILE_COUNT = 20_000


class ArchiveSafetyError(Exception):
    """Raised when a ZIP entry violates safety constraints."""


@dataclass(frozen=True)
class ArchiveManifestEntry:
    """One safely-enumerable entry inside a ZIP."""

    posix_path: str  # normalised, forward-slash, no leading "/" or ".."
    size_bytes: int
    is_dir: bool


@dataclass(frozen=True)
class ArchiveManifest:
    """Deterministic manifest for one ZIP archive.

    * ``source_path`` — the ZIP on disk.
    * ``entries`` — files only, sorted by POSIX path, with directory
      entries filtered out.
    * ``total_bytes`` — sum of ``size_bytes`` across ``entries``.
    * ``deterministic_ordering`` — frozen literal, mirrors the folder manifest.
    """

    source_path: Path
    entries: tuple[ArchiveManifestEntry, ...]
    total_bytes: int
    deterministic_ordering: str = "sorted_posix_path_ascending"

    def read_entry(self, entry: ArchiveManifestEntry) -> bytes:
        """Fetch the bytes of one entry.

        Opens the archive, reads the one entry, closes the archive.
        Enforces ``size_bytes`` as an upper bound on the actual read.
        """
        if entry.is_dir:
            raise ArchiveSafetyError(f"Cannot read a directory entry: {entry.posix_path}")
        with zipfile.ZipFile(self.source_path, "r") as zf:
            info = zf.getinfo(entry.posix_path)
            if info.file_size > entry.size_bytes:
                raise ArchiveSafetyError(
                    f"Entry grew between enumeration and read: {entry.posix_path}"
                )
            with zf.open(info, "r") as fp:
                data = fp.read(entry.size_bytes + 1)
        if len(data) > entry.size_bytes:
            raise ArchiveSafetyError(
                f"Entry read exceeded declared size: {entry.posix_path}"
            )
        return data


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    # external_attr high 16 bits encode UNIX mode; S_ISLNK test.
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _normalise_name(raw_name: str) -> str:
    # ZIP spec requires forward slashes, but some zips use backslashes.
    name = raw_name.replace("\\", "/")
    posix = PurePosixPath(name)
    if posix.is_absolute():
        raise ArchiveSafetyError(f"Absolute path inside archive: {raw_name!r}")
    parts = []
    for part in posix.parts:
        if part == "..":
            raise ArchiveSafetyError(f"Parent-dir traversal inside archive: {raw_name!r}")
        if part == ".":
            continue
        parts.append(part)
    normalised = "/".join(parts)
    return normalised


def enumerate_zip(
    zip_path: str | os.PathLike[str],
    *,
    max_entry_bytes: int = _DEFAULT_MAX_ENTRY_BYTES,
    max_total_bytes: int = _DEFAULT_MAX_TOTAL_BYTES,
    max_file_count: int = _DEFAULT_MAX_FILE_COUNT,
) -> ArchiveManifest:
    """Produce a deterministic manifest for ``zip_path``.

    All safety checks run eagerly during enumeration; the caller may then
    fetch bytes with :meth:`ArchiveManifest.read_entry` as needed.
    """
    src = Path(zip_path).expanduser()
    if not src.exists():
        raise ArchiveSafetyError(f"Archive does not exist: {src}")
    if not src.is_file():
        raise ArchiveSafetyError(f"Archive is not a regular file: {src}")

    try:
        zf = zipfile.ZipFile(src, "r")
    except zipfile.BadZipFile as e:
        raise ArchiveSafetyError(f"Not a valid ZIP: {src} ({e})") from e

    try:
        raw_entries: list[tuple[str, int, bool]] = []
        total = 0
        for info in zf.infolist():
            if _is_symlink(info):
                raise ArchiveSafetyError(
                    f"Symlink entries are not permitted: {info.filename!r}"
                )
            try:
                # UTF-8 reject non-decodable names.
                info.filename.encode("utf-8")
            except UnicodeEncodeError as e:
                raise ArchiveSafetyError(
                    f"Non-UTF-8 archive entry name: {info.filename!r}"
                ) from e
            is_dir = info.is_dir() or info.filename.endswith("/")
            normalised = _normalise_name(info.filename)
            if not normalised and not is_dir:
                raise ArchiveSafetyError(
                    f"Empty normalised entry name: {info.filename!r}"
                )
            if info.file_size < 0:
                raise ArchiveSafetyError(
                    f"Negative file_size on entry {normalised!r}"
                )
            if not is_dir and info.file_size > max_entry_bytes:
                raise ArchiveSafetyError(
                    f"Entry exceeds max_entry_bytes ({info.file_size} > {max_entry_bytes}): "
                    f"{normalised!r}"
                )
            if not is_dir:
                total += info.file_size
                if total > max_total_bytes:
                    raise ArchiveSafetyError(
                        f"Archive total exceeds max_total_bytes ({total} > {max_total_bytes})"
                    )
            raw_entries.append((normalised, info.file_size, is_dir))

        # Sort deterministically; drop directory entries from the manifest
        # (they are implied by the files beneath them).
        files_only = sorted(
            (e for e in raw_entries if not e[2]),
            key=lambda e: e[0],
        )
        if len(files_only) > max_file_count:
            raise ArchiveSafetyError(
                f"Archive file count exceeds max_file_count "
                f"({len(files_only)} > {max_file_count})"
            )
        entries = tuple(
            ArchiveManifestEntry(posix_path=p, size_bytes=s, is_dir=False)
            for (p, s, _d) in files_only
        )
    finally:
        zf.close()

    return ArchiveManifest(source_path=src, entries=entries, total_bytes=total)
