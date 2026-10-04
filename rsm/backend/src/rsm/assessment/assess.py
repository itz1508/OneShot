"""`assess_source` — pure function from Bucket to SourceAssessment.

Reads only the Bucket's own frozen bytes and the SCAN output. Never calls
an LLM, never performs network I/O, never mutates the Bucket.

The host application calls this BEFORE deciding whether the current
request materially requires external source observation. If a request is
plainly answerable without any source material, the application may
bypass RSM entirely (direct Agent path, §14 "RSM-first" rule). If the
assessment indicates the Bucket is non-empty and the request references
it, the application proceeds through the Reader → Processor → Replay
pipeline before releasing to the Agent.
"""

from __future__ import annotations

from ..bucket.model import Bucket
from ..reader.model import FileAvailability, FileType
from ..reader.scan import scan_bucket
from .model import (
    SourceAssessment,
    SourceAssessmentFiles,
    SourceAssessmentReason,
)


def assess_source(bucket: Bucket) -> SourceAssessment:
    """Derive the Source Assessment for a frozen Bucket.

    Pure function:
      * reads `bucket.full_content` sizes;
      * runs `scan_bucket(bucket)` for file counts;
      * NEVER reads image bytes;
      * NEVER mutates the Bucket;
      * NEVER calls an LLM / network / shell.

    `requires_vision` is True if SCAN finds any File of type IMAGE OR any
    File with `FileAvailability.OPAQUE` whose type is IMAGE. Non-image
    OPAQUE files (archives, binaries) do NOT mark the assessment as
    "requires vision" — they are honest limitations instead.
    """
    scan = scan_bucket(bucket)

    discovered = len(scan.files)
    readable = sum(1 for f in scan.files if f.availability == FileAvailability.READABLE)
    opaque = sum(1 for f in scan.files if f.availability == FileAvailability.OPAQUE)
    unreadable = sum(1 for f in scan.files if f.availability == FileAvailability.UNREADABLE)

    size_bytes = len(bucket.full_content.encode("utf-8"))
    size_chars = len(bucket.full_content)

    reasons: list[SourceAssessmentReason] = []
    limitations: list[str] = []

    # Requires observation is True iff the Bucket actually has source
    # material. An empty Bucket (source_count == 0 AND full_content == "")
    # is honestly "nothing to observe". A non-empty Bucket is observable
    # even if the only Files are opaque / unreadable (Reader will report
    # per-File failures — that is still RSM's contract).
    # "Has source" means something to actually observe.
    # Folder-origin Bucket  → ≥1 readable/opaque/unreadable file.
    # Opaque-origin Bucket  → the Bucket itself is the binary payload
    #                         (full_content is empty by design — see
    #                         rsm.extraction.opaque); its single SCAN
    #                         file carries the OPAQUE availability.
    # Any other simple-source Bucket → size_bytes > 0.
    is_folder = bucket.provenance.origin == "folder"
    if is_folder:
        has_source = (readable + opaque + unreadable) > 0
    elif bucket.provenance.origin == "opaque":
        has_source = opaque > 0 or size_bytes > 0
    else:
        has_source = size_bytes > 0
    requires_observation = has_source
    reasons.append(
        SourceAssessmentReason.SOURCE_PRESENT if has_source
        else SourceAssessmentReason.SOURCE_EMPTY
    )

    # Auxiliary reasons only make sense once we actually have something
    # to observe. An empty text Bucket's single-file manifest is a SCAN
    # artefact (one FileRef per simple-source Bucket), not real material.
    if has_source and is_folder:
        if readable > 0:
            reasons.append(SourceAssessmentReason.FOLDER_HAS_READABLE_FILES)
        if opaque > 0:
            reasons.append(SourceAssessmentReason.FOLDER_HAS_OPAQUE_FILES)
        if unreadable > 0:
            reasons.append(SourceAssessmentReason.FOLDER_HAS_UNREADABLE_FILES)
            limitations.append(
                "Some files use unsupported extensions — Reader will emit "
                "FILE_FAILED(reason=\"unsupported_extension\") for each."
            )

    # Per-origin reasons — only meaningful when there IS source to observe.
    origin = bucket.provenance.origin
    requires_vision = has_source and any(
        f.file_type == FileType.IMAGE for f in scan.files
    )
    if has_source:
        if origin == "pdf":
            reasons.append(SourceAssessmentReason.PDF_SOURCE)
        elif origin == "opaque":
            limitations.append(
                "Simple opaque Bucket — no textual content to observe; "
                "a Vision reader is required for images."
            )
        if requires_vision:
            reasons.append(SourceAssessmentReason.IMAGE_SOURCE)
            limitations.append(
                "Image Files require a wired VisionProvider AND "
                "caller-supplied image bytes; Reader emits "
                "FILE_FAILED(reason=\"vision_unavailable\") otherwise."
            )
        if (not requires_vision) and origin in (
            "text", "markdown", "pasted", "stdin", "chatgpt_export"
        ):
            reasons.append(SourceAssessmentReason.TEXT_SOURCE)

    return SourceAssessment(
        bucket_id=bucket.bucket_id,
        integrity={
            "algorithm": bucket.hash.algorithm,
            "value": bucket.hash.value,
        },
        requires_observation=requires_observation,
        requires_vision=requires_vision,
        files=SourceAssessmentFiles(
            discovered=discovered,
            readable=readable,
            opaque=opaque,
            unreadable=unreadable,
        ),
        source_size_bytes=size_bytes,
        source_size_chars=size_chars,
        origin=origin,
        reasons=reasons,
        limitations=limitations,
    )
