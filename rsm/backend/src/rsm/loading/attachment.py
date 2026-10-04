"""Phase 4/5 — Attachment intake.

A thin filesystem boundary that *stages* incoming external source material
before the Reader walks it. The stager:

* preserves bytes verbatim,
* computes the content SHA-256 (used only as an identity for the staged
  file; never as source authority — see ADR 0003 and prompt §19),
* records an optional caller-supplied SHA-256 for later verification,
* writes under ``./attachment/<content_sha256_prefix>/<name>``.

It never interprets content; it never produces RSM state. The downstream
loader + extractor + :class:`rsm.daemon.service.DaemonService` turn a staged
attachment into an authoritative Bucket.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from .runtime_dirs import DEFAULT_ATTACHMENT_DIR

# A conservative subset of filename characters we're willing to persist on
# disk. Everything else is replaced with "_". The caller's original name is
# NOT the source of identity (the SHA-256 is); this sanitisation is only to
# keep paths sane across filesystems.
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class AttachmentError(Exception):
    """Raised for staging failures (I/O, size, hash mismatch)."""


@dataclass(frozen=True)
class StagedAttachment:
    """A file staged under ``attachment/`` ready for the loader.

    * ``path`` — absolute POSIX path to the staged bytes.
    * ``size_bytes`` — exact size of the staged file.
    * ``content_sha256`` — hex SHA-256 of the staged bytes. Computed by the
      stager; this is NOT a verification result, only an identity used to
      address the staged file under the attachment root.
    * ``supplied_sha256`` — if the caller supplied a hex SHA-256 at stage
      time, it is recorded here. The stager compares it to
      ``content_sha256`` and raises :class:`AttachmentError` on mismatch;
      a verified match flips nothing on the Bucket (verification lives in
      :mod:`rsm.integrity.verify`). ``None`` when no hash was supplied.
    * ``original_name`` — the caller-supplied name, best-effort sanitised,
      preserved for provenance.
    """

    path: Path
    size_bytes: int
    content_sha256: str
    supplied_sha256: str | None
    original_name: str


def _safe_name(name: str) -> str:
    cleaned = _SAFE_NAME_RE.sub("_", name).strip("._")
    return cleaned or "file"


def _stage(
    data: bytes,
    *,
    attachment_dir: Path,
    original_name: str,
    supplied_sha256: str | None,
) -> StagedAttachment:
    digest = hashlib.sha256(data).hexdigest()
    if supplied_sha256 is not None:
        if supplied_sha256.lower() != digest:
            raise AttachmentError(
                "Supplied SHA-256 does not match staged bytes: "
                f"expected={supplied_sha256.lower()} actual={digest}"
            )
    # Fan out by first two hex chars to keep attachment/ dense but not flat.
    bucket_dir = attachment_dir / digest[:2]
    bucket_dir.mkdir(parents=True, exist_ok=True)
    dest = bucket_dir / f"{digest}_{_safe_name(original_name)}"
    # Write once; staging the same bytes under the same name is idempotent.
    if not dest.exists():
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, dest)
    return StagedAttachment(
        path=dest,
        size_bytes=len(data),
        content_sha256=digest,
        supplied_sha256=supplied_sha256.lower() if supplied_sha256 else None,
        original_name=original_name,
    )


def stage_attachment_bytes(
    data: bytes,
    *,
    original_name: str = "attachment",
    supplied_sha256: str | None = None,
    attachment_dir: str | os.PathLike[str] = DEFAULT_ATTACHMENT_DIR,
) -> StagedAttachment:
    """Stage raw bytes under ``attachment_dir``. Returns the staged record."""
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise AttachmentError("stage_attachment_bytes expects bytes-like input")
    return _stage(
        bytes(data),
        attachment_dir=Path(attachment_dir).expanduser(),
        original_name=original_name,
        supplied_sha256=supplied_sha256,
    )


def stage_attachment_path(
    path: str | os.PathLike[str],
    *,
    supplied_sha256: str | None = None,
    attachment_dir: str | os.PathLike[str] = DEFAULT_ATTACHMENT_DIR,
) -> StagedAttachment:
    """Stage the file at ``path`` under ``attachment_dir``."""
    src = Path(path).expanduser()
    if not src.exists():
        raise AttachmentError(f"Attachment source does not exist: {src}")
    if not src.is_file():
        raise AttachmentError(f"Attachment source is not a regular file: {src}")
    data = src.read_bytes()
    return _stage(
        data,
        attachment_dir=Path(attachment_dir).expanduser(),
        original_name=src.name,
        supplied_sha256=supplied_sha256,
    )
