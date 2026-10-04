"""rsm.reader — Scan + Reader + ReaderTrace (V3 Reader architecture).

Boundaries (see docs/rsm-v3-reader-processor.md):

    SCAN      — fast, shallow discovery. Answers "What exists and how can it
                be accessed?" NEVER an LLM, NEVER composes AgentContext.
    FILE      — a bounded, addressable representation of source material used
                by Reader. `file_id` is the opaque identifier. A File is NOT a
                new authoritative Source.
    READER    — the actual content-observation boundary. Vision is a Reader
                CAPABILITY, not a separate top-level subsystem.
    TRACE     — one continuous lightweight observation surface answering
                "What has Reader actually observed?" Isolated per-File
                failures do NOT fail the whole Reader operation.

    This module imports only stdlib + pydantic + rsm.bucket; the boundary
    gate (`tools/verification/check_boundaries.py`) must list `rsm.reader` with
    the same restriction set as `rsm.classification`/`rsm.execution`.

    PROCESSOR and REPLAY live elsewhere (`rsm.snapshot` is the current
    bounded-prepared-representation implementation; `rsm.replay` /
    `rsm.api.routers.interactions.stream` is the delivery layer). This
    module is NOT the Processor — Reader stops at observation.
"""

from .model import (
    FileRef,
    FileType,
    FileAvailability,
    ReaderMethod,
    ReaderStatus,
    ReaderEvent,
    ReaderEventKind,
    FailureInfo,
    FileCoverage,
    ReaderTrace,
    ScanResult,
    ReadResult,
)
from .scan import scan_bucket
from .reader import read_bucket

__all__ = [
    "FileRef",
    "FileType",
    "FileAvailability",
    "ReaderMethod",
    "ReaderStatus",
    "ReaderEvent",
    "ReaderEventKind",
    "FailureInfo",
    "FileCoverage",
    "ReaderTrace",
    "ScanResult",
    "ReadResult",
    "scan_bucket",
    "read_bucket",
]
