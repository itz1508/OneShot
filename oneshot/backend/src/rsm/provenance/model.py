"""Internal provenance record (distinct from the compact Bucket.provenance)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ProvenanceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bucket_id: str
    origin: str
    source_uri: str | None = None
    derived_from: str | None = None
    produced_at: datetime
    extras: dict[str, Any] = {}
