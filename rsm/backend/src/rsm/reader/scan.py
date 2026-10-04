"""SCAN — fast, shallow discovery (see module docstring for the contract).

Determinism: `scan_bucket` is a pure function of the frozen Bucket. It never
reads full content for files beyond what is already in `Bucket.full_content`,
and it never performs OCR / vision / LLM work.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from ..bucket.model import Bucket
from .model import (
    FileAvailability,
    FileRef,
    FileType,
    ScanResult,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _file_type_for_name(name: str) -> FileType:
    lower = name.lower()
    if lower.endswith((".md", ".markdown")):
        return FileType.MARKDOWN
    if lower.endswith(".pdf"):
        return FileType.PDF
    if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")):
        return FileType.IMAGE
    if lower.endswith((".txt", ".json", ".log")):
        return FileType.TEXT
    return FileType.UNKNOWN


def _availability_from_opaque(name: str, type_: FileType) -> FileAvailability:
    # SCAN does not open opaque bytes. The folder manifest already records
    # which paths are opaque.
    if type_ == FileType.IMAGE:
        return FileAvailability.OPAQUE  # readable only when a Vision reader is wired
    return FileAvailability.READABLE


def _scan_folder_bucket(bucket: Bucket) -> list[FileRef]:
    """A folder-origin bucket carries a canonical manifest in `full_content`.

    The manifest\'s `entries.{supported, opaque, unsupported}` lists are the
    SCAN output. SCAN does NOT read the children\'s bytes.
    """
    try:
        manifest = json.loads(bucket.full_content)
    except Exception:
        return []
    entries = manifest.get("entries") or {}
    files: list[FileRef] = []
    i = 1
    for name in entries.get("supported", []) or []:
        t = _file_type_for_name(name)
        files.append(
            FileRef(
                file_id=f"{bucket.bucket_id}:f{i}",
                index=i,
                bucket_id=bucket.bucket_id,
                name=name,
                file_type=t,
                availability=_availability_from_opaque(name, t),
            )
        )
        i += 1
    for name in entries.get("opaque", []) or []:
        t = _file_type_for_name(name)
        files.append(
            FileRef(
                file_id=f"{bucket.bucket_id}:f{i}",
                index=i,
                bucket_id=bucket.bucket_id,
                name=name,
                file_type=t,
                availability=FileAvailability.OPAQUE,
                description="opaque: not deterministically readable without Vision",
            )
        )
        i += 1
    for name in entries.get("unsupported", []) or []:
        files.append(
            FileRef(
                file_id=f"{bucket.bucket_id}:f{i}",
                index=i,
                bucket_id=bucket.bucket_id,
                name=name,
                file_type=FileType.UNKNOWN,
                availability=FileAvailability.UNREADABLE,
                description="unsupported extension",
            )
        )
        i += 1
    return files


def _scan_simple_bucket(bucket: Bucket) -> list[FileRef]:
    """Simple-source Buckets (text/markdown/pasted/stdin/pdf/opaque) → one File."""
    origin = bucket.provenance.origin
    name = bucket.provenance.source_uri or bucket.bucket_id

    file_type = {
        "markdown": FileType.MARKDOWN,
        "text": FileType.TEXT,
        "pasted": FileType.TEXT,
        "stdin": FileType.TEXT,
        "chatgpt_export": FileType.TEXT,
        "pdf": FileType.PDF,
        "opaque": FileType.OPAQUE,
    }.get(origin, FileType.UNKNOWN)

    availability = (
        FileAvailability.OPAQUE
        if file_type in (FileType.OPAQUE,)
        else FileAvailability.READABLE
    )
    size_bytes = len(bucket.full_content.encode("utf-8"))
    page_count: Optional[int] = (
        int(bucket.metadata.get("page_count"))  # type: ignore[arg-type]
        if isinstance(bucket.metadata.get("page_count"), int) else None
    )
    return [
        FileRef(
            file_id=f"{bucket.bucket_id}:f1",
            index=1,
            bucket_id=bucket.bucket_id,
            name=name,
            file_type=file_type,
            availability=availability,
            size_bytes=size_bytes,
            page_count=page_count,
        )
    ]


def scan_bucket(bucket: Bucket) -> ScanResult:
    """Fast, shallow discovery for one Bucket.

    - Folder-origin bucket → one File per manifest entry (supported, opaque,
      unsupported) — order preserved, deterministic.
    - Any other origin → exactly one File addressing the Bucket itself.

    This function is pure, deterministic, LLM-free, and reads no bytes outside
    the Bucket's own `full_content`.
    """
    files = (
        _scan_folder_bucket(bucket)
        if bucket.provenance.origin == "folder"
        else _scan_simple_bucket(bucket)
    )
    return ScanResult(
        bucket_id=bucket.bucket_id,
        files=files,
        produced_at=_utcnow(),
    )
