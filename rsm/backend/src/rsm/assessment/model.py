"""Pydantic DTOs for Source Assessment.

Deliberately small typed results, same style as rsm.reader.model.

A SourceAssessment answers:

    requires_observation  — is there any external source material that
                            RSM would observe and prepare? (True once a
                            Bucket exists; the architectural "source
                            materially required" classification lives in
                            the host app, not here.)
    requires_vision       — does any discovered File require Vision to be
                            observed (image or OPAQUE media)?
    files                 — SCAN-level counts (discovered / readable /
                            opaque / unreadable). Never deep content.
    source_size_bytes/chars — size of the Bucket's own canonical bytes.
    integrity             — the Bucket's sha256 identity (A1).
    reasons               — short, machine-readable reasons for why
                            observation is / is not required.
    limitations           — explicit list of what Reader could not
                            promise without additional capabilities
                            (e.g. a wired VisionProvider + image bytes).
"""

from __future__ import annotations

from enum import StrEnum
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceAssessmentReason(StrEnum):
    """Why observation is / is not required. Machine-readable."""
    SOURCE_PRESENT = "source_present"
    SOURCE_EMPTY = "source_empty"
    FOLDER_HAS_READABLE_FILES = "folder_has_readable_files"
    FOLDER_HAS_OPAQUE_FILES = "folder_has_opaque_files"
    FOLDER_HAS_UNREADABLE_FILES = "folder_has_unreadable_files"
    IMAGE_SOURCE = "image_source"
    PDF_SOURCE = "pdf_source"
    TEXT_SOURCE = "text_source"


class SourceAssessmentFiles(BaseModel):
    """SCAN-level counts, never deep content."""
    model_config = ConfigDict(extra="forbid")

    discovered: int = Field(..., ge=0)
    readable: int = Field(..., ge=0)
    opaque: int = Field(..., ge=0)
    unreadable: int = Field(..., ge=0)


class SourceAssessment(BaseModel):
    """Read-only architectural assessment of a Bucket.

    This is the Source Assessment surface. The host application calls
    into it before deciding whether to use RSM-first preparation or to
    hand control directly to the Agent for a no-source request.

    A SourceAssessment is derived from the frozen Bucket — it mutates
    nothing, calls no LLM, and makes no network request.
    """
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"

    bucket_id: str = Field(..., min_length=1)
    integrity: dict = Field(..., description="SHA-256 of the Bucket (A1 identity).")

    requires_observation: bool
    requires_vision: bool
    files: SourceAssessmentFiles
    source_size_bytes: int = Field(..., ge=0)
    source_size_chars: int = Field(..., ge=0)
    origin: str = Field(..., min_length=1)

    reasons: List[SourceAssessmentReason] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
