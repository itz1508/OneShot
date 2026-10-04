"""Reader — actual observation of discovered Files.

A single File's observation produces exactly one `ReaderEvent` of kind
`FILE_OBSERVED` / `FILE_PARTIAL` / `FILE_FAILED`. Any `UNREADABLE` File
yields `FILE_FAILED` and is isolated to that File only — the Reader
operation continues for the rest.

Reader does NOT:
  - mutate the Bucket (A1 preserved by not calling any store write path),
  - produce the prepared representation (that is `rsm.snapshot`),
  - call an LLM in rsm core (Vision is an INJECTED capability, see below).

Vision is a Reader capability, not a separate top-level subsystem. The
`read_bucket` entry point accepts an optional `vision_provider` and an
optional `image_bytes` lookup; when both are supplied, image Files are
observed via `rsm.vision.observe_image(...)` and recorded as
`ReaderEvent(method=VISION, vision=True)`. The default (no provider /
no bytes) preserves the honest `FILE_FAILED(reason="vision_unavailable")`
representation, so existing callers behave byte-identically.

Image bytes travel through the caller because `rsm.bucket` does NOT store
binary image payloads for folder-origin Buckets — the folder manifest
lists image children by name but their bytes stay on disk. Reader does
not reopen those files itself (that would duplicate rsm.extraction's
boundary); the daemon / caller is the smallest place where the bytes can
be re-materialised, and this signature keeps that choice outside Reader.
Reader never fetches credentials, never constructs a provider, and never
decides what endpoint to call.

Failure isolation is preserved end-to-end: a `VisionUnavailable` /
`VisionError` for one File becomes a `FILE_FAILED` for that File and the
Reader loop keeps going.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Iterator, Mapping, Optional, Union

from ..bucket.model import Bucket
from ..vision import (
    VisionError,
    VisionProvider,
    VisionUnavailable,
    observe_image,
)
from .model import (
    FailureInfo,
    FileAvailability,
    FileCoverage,
    FileRef,
    FileType,
    ReadResult,
    ReaderEvent,
    ReaderEventKind,
    ReaderMethod,
    ReaderStatus,
    ReaderTrace,
)
from .scan import scan_bucket


DEFAULT_VISION_PROMPT = (
    "Describe the observable content of this image for downstream text use."
)

# Only the mimes `rsm.vision.ALLOWED_MIMES` accepts; anything else fails per-File.
_MIME_FROM_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}

# A caller supplies image bytes either as a dict keyed by file_id or a callable
# that returns the bytes (or None) for a FileRef. Both shapes stay out of core
# domain state and never touch the Bucket.
ImageBytesSource = Union[
    Mapping[str, bytes],
    Callable[[FileRef], Optional[bytes]],
    None,
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_image_bytes(src: ImageBytesSource, f: FileRef) -> Optional[bytes]:
    if src is None:
        return None
    if callable(src):
        try:
            return src(f)
        except Exception:  # noqa: BLE001 - isolation invariant; caller cb may fail
            return None
    # Mapping path — accept bytes/bytearray values.
    val = src.get(f.file_id)
    if val is None:
        return None
    return bytes(val)


def _mime_for(name: str) -> Optional[str]:
    lower = name.lower()
    for ext, mime in _MIME_FROM_SUFFIX.items():
        if lower.endswith(ext):
            return mime
    return None


def _observe_image_via_vision(
    f: FileRef,
    provider: VisionProvider,
    image_bytes: bytes,
    prompt: str,
) -> ReaderEvent:
    """Invoke Vision for one image File and translate the result/failure
    into the existing Reader event model. Never raises — a Vision failure
    becomes a `FILE_FAILED` for this File only.
    """
    mime = _mime_for(f.name)
    if mime is None:
        # NIM VLM API only documents JPG/JPEG/PNG; .gif/.bmp/.webp fall here.
        return ReaderEvent(
            kind=ReaderEventKind.FILE_FAILED,
            at=_utcnow(),
            file_id=f.file_id,
            index=f.index,
            method=ReaderMethod.NONE,
            reason="vision_unsupported_mime",
        )
    try:
        result = observe_image(
            provider,
            image_bytes=image_bytes,
            mime=mime,
            prompt=prompt,
        )
    except VisionUnavailable:
        return ReaderEvent(
            kind=ReaderEventKind.FILE_FAILED,
            at=_utcnow(),
            file_id=f.file_id,
            index=f.index,
            method=ReaderMethod.NONE,
            reason="vision_unavailable",
        )
    except VisionError as e:
        return ReaderEvent(
            kind=ReaderEventKind.FILE_FAILED,
            at=_utcnow(),
            file_id=f.file_id,
            index=f.index,
            method=ReaderMethod.NONE,
            reason=f"vision_{e.kind}",
        )
    except Exception as e:  # noqa: BLE001 - last-resort isolation
        return ReaderEvent(
            kind=ReaderEventKind.FILE_FAILED,
            at=_utcnow(),
            file_id=f.file_id,
            index=f.index,
            method=ReaderMethod.NONE,
            reason=f"vision_error:{type(e).__name__}",
        )
    text = result.text or ""
    return ReaderEvent(
        kind=ReaderEventKind.FILE_OBSERVED,
        at=_utcnow(),
        file_id=f.file_id,
        index=f.index,
        method=ReaderMethod.VISION,
        vision=True,
        observed_bytes=len(text.encode("utf-8")),
        observed_chars=len(text),
    )


def _observe_simple(bucket: Bucket, f: FileRef) -> ReaderEvent:
    """Observe a simple-source File. Reads bytes from `bucket.full_content`."""
    text = bucket.full_content
    method = ReaderMethod.TEXT
    if f.file_type == FileType.MARKDOWN:
        method = ReaderMethod.TEXT
    elif f.file_type == FileType.PDF:
        method = ReaderMethod.DOCUMENT
    return ReaderEvent(
        kind=ReaderEventKind.FILE_OBSERVED,
        at=_utcnow(),
        file_id=f.file_id,
        index=f.index,
        method=method,
        vision=False,
        observed_bytes=len(text.encode("utf-8")),
        observed_chars=len(text),
    )


def _observe_folder_child(
    f: FileRef,
    *,
    vision_provider: Optional[VisionProvider],
    image_bytes_src: ImageBytesSource,
    vision_prompt: str,
) -> ReaderEvent:
    """Observe a child entry from a folder manifest.

    This build does not re-open child files from disk (Reader is scoped to
    the authoritative Bucket's own bytes); folder children are recorded as
    OBSERVED with method=TEXT and zero observed bytes (the manifest lists
    them but the children live outside the Bucket's canonical bytes).
    Opaque / unsupported entries emit FILE_FAILED with the appropriate
    reason — isolated to that file_id.

    When a `vision_provider` is wired AND image bytes are supplied for an
    image File, Vision is invoked for that File; the resulting observation
    is recorded with `method=VISION, vision=True`. If no provider or no
    bytes are supplied for an image File, the existing honest failure
    (`FILE_FAILED(reason="vision_unavailable")`) is preserved.
    """
    if f.availability == FileAvailability.UNREADABLE:
        return ReaderEvent(
            kind=ReaderEventKind.FILE_FAILED,
            at=_utcnow(),
            file_id=f.file_id,
            index=f.index,
            method=ReaderMethod.NONE,
            reason="unsupported_extension",
        )
    if f.availability == FileAvailability.OPAQUE:
        # Image / archive / etc. — Vision is the only path for images.
        if f.file_type == FileType.IMAGE and vision_provider is not None:
            img = _resolve_image_bytes(image_bytes_src, f)
            if img is not None:
                return _observe_image_via_vision(
                    f, vision_provider, img, vision_prompt
                )
            # Provider wired but no bytes available — honest failure.
            return ReaderEvent(
                kind=ReaderEventKind.FILE_FAILED,
                at=_utcnow(),
                file_id=f.file_id,
                index=f.index,
                method=ReaderMethod.NONE,
                reason="vision_unavailable",
            )
        return ReaderEvent(
            kind=ReaderEventKind.FILE_FAILED,
            at=_utcnow(),
            file_id=f.file_id,
            index=f.index,
            method=ReaderMethod.NONE,
            reason="vision_unavailable" if f.file_type == FileType.IMAGE else "opaque",
        )
    # Readable manifest entry — recorded as observed-by-reference.
    return ReaderEvent(
        kind=ReaderEventKind.FILE_OBSERVED,
        at=_utcnow(),
        file_id=f.file_id,
        index=f.index,
        method=ReaderMethod.TEXT,
        vision=False,
        observed_bytes=0,
        observed_chars=0,
    )


def _iter_events(
    bucket: Bucket,
    files: list[FileRef],
    *,
    vision_provider: Optional[VisionProvider],
    image_bytes_src: ImageBytesSource,
    vision_prompt: str,
) -> Iterator[ReaderEvent]:
    is_folder = bucket.provenance.origin == "folder"
    for f in files:
        try:
            if is_folder:
                yield _observe_folder_child(
                    f,
                    vision_provider=vision_provider,
                    image_bytes_src=image_bytes_src,
                    vision_prompt=vision_prompt,
                )
            else:
                yield _observe_simple(bucket, f)
        except Exception as e:  # pragma: no cover - defensive, isolation invariant
            yield ReaderEvent(
                kind=ReaderEventKind.FILE_FAILED,
                at=_utcnow(),
                file_id=f.file_id,
                index=f.index,
                method=ReaderMethod.NONE,
                reason=f"reader_error:{type(e).__name__}",
            )


def _build_trace(bucket: Bucket, discovered: int, events: list[ReaderEvent]) -> ReaderTrace:
    coverage: dict[str, FileCoverage] = {}
    failures: list[FailureInfo] = []
    latest = 0
    observed = partial = failed = 0

    for ev in events:
        latest = max(latest, ev.index)
        if ev.kind == ReaderEventKind.FILE_OBSERVED:
            observed += 1
            status = ReaderStatus.OBSERVED
        elif ev.kind == ReaderEventKind.FILE_PARTIAL:
            partial += 1
            status = ReaderStatus.PARTIAL
        elif ev.kind == ReaderEventKind.FILE_FAILED:
            failed += 1
            status = ReaderStatus.FAILED
            failures.append(
                FailureInfo(
                    file_id=ev.file_id,
                    index=ev.index,
                    reason=ev.reason or "unknown",
                    at=ev.at,
                )
            )
        else:
            continue
        coverage[ev.file_id] = FileCoverage(
            file_id=ev.file_id,
            index=ev.index,
            status=status,
            method=ev.method,
            vision=ev.vision,
            observed_bytes=ev.observed_bytes,
            observed_chars=ev.observed_chars,
        )

    cov_list = sorted(coverage.values(), key=lambda c: c.index)
    return ReaderTrace(
        bucket_id=bucket.bucket_id,
        discovered=discovered,
        latest_index=latest,
        observed_count=observed,
        partial_count=partial,
        failed_count=failed,
        complete=True,
        failures=failures,
        coverage=cov_list,
    )


def read_bucket(
    bucket: Bucket,
    *,
    vision_provider: Optional[VisionProvider] = None,
    image_bytes: ImageBytesSource = None,
    vision_prompt: str = DEFAULT_VISION_PROMPT,
) -> ReadResult:
    """Deterministic Reader operation over the Scan result.

    Parameters:
        bucket:          The frozen authoritative Bucket (A1 preserved).
        vision_provider: Optional VisionProvider. When ``None`` (the default),
                         image Files remain `FILE_FAILED(reason="vision_unavailable")`
                         — identical to the pre-wiring behaviour.
        image_bytes:     Optional lookup of image bytes keyed by `file_id`,
                         either a `Mapping[str, bytes]` or a
                         `Callable[[FileRef], bytes | None]`. Bucket content
                         is never read for image bytes; the caller supplies them.
        vision_prompt:   Prompt sent to the VisionProvider. Default is a
                         bounded "describe this image" prompt.

    Isolation invariant: a per-File failure never terminates the loop. A
    VisionUnavailable / VisionError / unsupported mime for one File yields
    `FILE_FAILED` for that File only; subsequent Files are still observed.

    Returns the ordered event sequence plus the final `ReaderTrace`.
    """
    scan = scan_bucket(bucket)
    events = list(
        _iter_events(
            bucket,
            scan.files,
            vision_provider=vision_provider,
            image_bytes_src=image_bytes,
            vision_prompt=vision_prompt,
        )
    )
    trace = _build_trace(bucket, discovered=len(scan.files), events=events)
    return ReadResult(bucket_id=bucket.bucket_id, events=events, trace=trace)
