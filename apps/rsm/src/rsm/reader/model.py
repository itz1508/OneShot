"""Pydantic models for rsm.reader.

These are deliberately small typed results. No workflow engine, no graph
abstraction, no new "domain" beyond what the Reader architecture requires.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class FileType(StrEnum):
    TEXT = "text"
    MARKDOWN = "markdown"
    PDF = "pdf"
    IMAGE = "image"
    OPAQUE = "opaque"
    UNKNOWN = "unknown"


class FileAvailability(StrEnum):
    READABLE = "readable"
    OPAQUE = "opaque"       # material present but not deterministically readable
    UNREADABLE = "unreadable"


class ReaderMethod(StrEnum):
    """Observation strategy actually used for a File."""
    TEXT = "text"
    DOCUMENT = "document"
    OCR = "ocr"
    VISION = "vision"
    NONE = "none"


class ReaderStatus(StrEnum):
    OBSERVED = "OBSERVED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    NOT_OBSERVED = "NOT_OBSERVED"


class ReaderEventKind(StrEnum):
    FILE_OBSERVED = "FILE_OBSERVED"
    FILE_PARTIAL = "FILE_PARTIAL"
    FILE_FAILED = "FILE_FAILED"
    READER_COMPLETE = "READER_COMPLETE"


class FileRef(BaseModel):
    """Bounded, addressable representation of source material. NOT a Source."""
    model_config = ConfigDict(extra="forbid")

    file_id: str = Field(..., min_length=1)
    index: int = Field(..., ge=1)  # 1-based for UX readouts
    bucket_id: str = Field(..., min_length=1)  # authoritative Source
    name: str = Field(..., min_length=1)
    file_type: FileType = FileType.UNKNOWN
    availability: FileAvailability = FileAvailability.READABLE
    size_bytes: int = Field(0, ge=0)
    # Optional lightweight structural hints discovered by SCAN. Never deep content.
    page_count: Optional[int] = None
    description: Optional[str] = None


class FailureInfo(BaseModel):
    """Isolated per-File failure. Does NOT fail the whole Reader operation."""
    model_config = ConfigDict(extra="forbid")

    file_id: str
    index: int = Field(..., ge=1)
    reason: str = Field(..., min_length=1)
    at: datetime


class FileCoverage(BaseModel):
    """Per-File coverage summary, derived from the event stream."""
    model_config = ConfigDict(extra="forbid")

    file_id: str
    index: int = Field(..., ge=1)
    status: ReaderStatus = ReaderStatus.NOT_OBSERVED
    method: ReaderMethod = ReaderMethod.NONE
    vision: bool = False
    observed_bytes: int = Field(0, ge=0)
    observed_chars: int = Field(0, ge=0)


class ReaderEvent(BaseModel):
    """One update in the continuous Reader observation trace."""
    model_config = ConfigDict(extra="forbid")

    kind: ReaderEventKind
    at: datetime
    file_id: str
    index: int = Field(..., ge=1)
    method: ReaderMethod = ReaderMethod.NONE
    vision: bool = False
    observed_bytes: int = Field(0, ge=0)
    observed_chars: int = Field(0, ge=0)
    reason: Optional[str] = None


class ReaderTrace(BaseModel):
    """Lightweight continuous observation surface.

    Rendering rule: ONE continuous bar whose fill is `latest_index / discovered`
    and whose right-side number is `latest_index`. The UI does NOT render one
    bar per File. Failures are a separate flat list.
    """
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    bucket_id: str
    discovered: int = Field(..., ge=0)         # files discovered by SCAN
    latest_index: int = Field(0, ge=0)         # latest File reached (1-based)
    observed_count: int = Field(0, ge=0)       # files with status OBSERVED
    partial_count: int = Field(0, ge=0)
    failed_count: int = Field(0, ge=0)
    complete: bool = False
    failures: list[FailureInfo] = Field(default_factory=list)
    coverage: list[FileCoverage] = Field(default_factory=list)


class ScanResult(BaseModel):
    """SCAN result: what exists and how can it be accessed. Fast and shallow."""
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    bucket_id: str
    files: list[FileRef]
    produced_at: datetime


class ReadResult(BaseModel):
    """Reader result: the ordered event sequence + the final ReaderTrace."""
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    bucket_id: str
    events: list[ReaderEvent]
    trace: ReaderTrace
