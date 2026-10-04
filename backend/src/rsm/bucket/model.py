"""Pydantic models for the V1 canonical bucket (Spec §6).

A2 — schema_version is a frozen literal "1" on every bucket.
A1 — enforced by rsm.bucket.immutability.check_mutation at write time
     in rsm.daemon.store.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


SchemaVersion = Literal["1"]


class Hash(BaseModel):
    """SHA-256 fingerprint of a bucket's canonical representation."""
    model_config = ConfigDict(extra="forbid")

    algorithm: Literal["sha256"] = "sha256"
    value: str = Field(..., pattern=r"^[0-9a-f]{64}$")


class Provenance(BaseModel):
    """Where this bucket came from.

    `derived_from` names a parent bucket_id (used by A3 folder children).
    """
    model_config = ConfigDict(extra="forbid")

    origin: Literal[
        "markdown",
        "text",
        "pasted",
        "stdin",
        "chatgpt_export",
        "pdf",
        "folder",
        "opaque",
    ]
    source_uri: Optional[str] = None
    derived_from: Optional[str] = None
    produced_at: datetime


class LifecycleTimestamps(BaseModel):
    """Mutable per-state timestamps and release counter (A1 mutable set)."""
    model_config = ConfigDict(extra="forbid")

    received_at: Optional[datetime] = None
    staged_at: Optional[datetime] = None
    stored_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    replayed_at: Optional[datetime] = None
    released_at: Optional[datetime] = None
    retired_at: Optional[datetime] = None
    release_count: int = 0


class Bucket(BaseModel):
    """V1 canonical bucket.

    `schema_version` and content-identity fields are FROZEN after STORED;
    see rsm.bucket.immutability.FROZEN_FIELDS.
    """
    model_config = ConfigDict(extra="forbid")

    schema_version: SchemaVersion = "1"
    bucket_id: str = Field(..., min_length=1)
    hash: Hash
    provenance: Provenance

    # Content-identity fields (frozen):
    full_content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    integrity_status: Literal["unverified", "verified", "corrupt"] = "unverified"

    # Mutable:
    state: Literal[
        "RECEIVED",
        "STAGED",
        "STORED",
        "ACTIVATED",
        "REPLAYED",
        "RELEASED",
        "RETIRED",
    ] = "RECEIVED"
    lifecycle: LifecycleTimestamps = Field(default_factory=LifecycleTimestamps)
    optional_summary: Optional[str] = None
