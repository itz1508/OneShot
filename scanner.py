"""OneShot deterministic local text scanner.

The caller establishes the trusted root; a source name alone never authorizes
reading outside it. Scanner performs no agent inference, writes, or execution.
"""
from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

MAX_SOURCE_BYTES = 1_000_000
MAX_EXCERPT_BYTES = 64_000
MAX_FINDINGS = 50
MAX_SPANS_PER_FINDING = 16


class ScanRejected(ValueError):
    """A source or excerpt violates the supported read boundary."""


@dataclass(frozen=True, slots=True)
class AdmittedSource:
    """Immutable source snapshot returned by the caller's authorized read."""

    source_id: str
    name: str
    content: bytes
    sha256: str


def _check_relative_name(name: str) -> tuple[str, ...]:
    if not isinstance(name, str) or not name or "\\" in name or "\x00" in name:
        raise ScanRejected("Invalid source name")
    parsed = PurePosixPath(name)
    if (parsed.is_absolute() or parsed.as_posix() != name
            or any(part in ("", ".", "..") for part in name.split("/"))
            or ":" in name):
        raise ScanRejected("Source name must be a normalized relative path")
    return parsed.parts


def _no_link(path: Path) -> None:
    """Reject symlinks and Windows junctions at every path component."""
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ScanRejected("Source path cannot be read") from exc
    if stat.S_ISLNK(mode) or (hasattr(path, "is_junction") and path.is_junction()):
        raise ScanRejected("Linked source path is not permitted")


def admit_file(*, trusted_root: Path, relative_name: str, source_id: str) -> AdmittedSource:
    """Snapshot one explicitly admitted file under a trusted operator root.

    The trusted root and name must originate at the authorizing host boundary.
    On Windows the standard-library check is not a defense against concurrent
    path replacement; do not grant this helper to an untrusted MCP client.
    """
    if not isinstance(source_id, str) or not source_id.strip():
        raise ScanRejected("source_id must be a nonempty string")
    parts = _check_relative_name(relative_name)
    trusted_root = Path(trusted_root)
    _no_link(trusted_root)
    if not trusted_root.is_dir():
        raise ScanRejected("Trusted source root must be a directory")
    current = trusted_root
    for i, part in enumerate(parts):
        current = current / part
        _no_link(current)
        if i < len(parts) - 1 and not current.is_dir():
            raise ScanRejected("Source parent must be a directory")
    if not current.is_file():
        raise ScanRejected("Only regular source files are supported")
    # Bounded read; no need to load or hash unbounded file contents.
    try:
        with current.open("rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ScanRejected("Source is not a regular file")
            content = handle.read(MAX_SOURCE_BYTES + 1)
    except OSError as exc:
        raise ScanRejected("Source cannot be opened") from exc
    if len(content) > MAX_SOURCE_BYTES:
        raise ScanRejected("Source exceeds the admission size limit")
    return AdmittedSource(source_id, relative_name, content, hashlib.sha256(content).hexdigest())


def inspect_text(
    source: AdmittedSource,
    *,
    start_byte: int = 0,
    max_bytes: int = MAX_EXCERPT_BYTES,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Return a byte-accurate UTF-8 excerpt and conservative exact repetitions.

    No claim is made about semantic equivalence or contradictory meaning.
    """
    if (not isinstance(source, AdmittedSource) or
            not isinstance(source.source_id, str) or not source.source_id.strip() or
            not isinstance(source.name, str) or
            not isinstance(source.content, bytes)):
        raise ScanRejected("Invalid admitted source")
    raw = source.content
    digest = hashlib.sha256(raw).hexdigest()
    if digest != source.sha256 or (expected_sha256 is not None and digest != expected_sha256):
        raise ScanRejected("Source fingerprint mismatch")
    if len(raw) > MAX_SOURCE_BYTES:
        raise ScanRejected("Source exceeds the inspection size limit")
    if (type(start_byte) is not int or type(max_bytes) is not int
            or start_byte < 0 or start_byte > len(raw)
            or max_bytes < 0 or max_bytes > MAX_EXCERPT_BYTES):
        raise ScanRejected("Invalid excerpt range")
    end = min(len(raw), start_byte + max_bytes)
    try:
        content = raw[start_byte:end].decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ScanRejected("Excerpt is not valid UTF-8 at this byte boundary") from exc
    complete = start_byte == 0 and end == len(raw)
    limitations = []
    if not complete:
        limitations.append("Excerpt does not cover the complete source")
    findings = []
    if complete:
        # Exact duplicate nonblank *lines*, with byte offsets. Repeated meaning
        # and similar-looking text are intentionally outside this operation.
        positions: dict[bytes, list[list[int]]] = {}
        repeated_truncated = False
        offset = 0
        for line in raw.splitlines(keepends=True):
            body = line.rstrip(b"\r\n")
            if body.strip():
                spans = positions.setdefault(body, [])
                if len(spans) < MAX_SPANS_PER_FINDING:
                    spans.append([offset, offset + len(body)])
                else:
                    repeated_truncated = True
            offset += len(line)
        for occurrences in positions.values():
            if len(occurrences) > 1:
                if len(findings) >= MAX_FINDINGS:
                    repeated_truncated = True
                    break
                findings.append({"kind": "exact_repeated_line", "byte_spans": occurrences})
        if repeated_truncated:
            limitations.append("Exact repetition findings are bounded and may be incomplete")
    return {
        "source_id": source.source_id,
        "source_name": source.name,
        "source_sha256": digest,
        "source_size": len(raw),
        "byte_span": {"start": start_byte, "end": end},
        "content": content,
        "complete_source": complete,
        "findings": findings,
        "limitations": limitations,
    }
