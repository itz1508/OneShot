"""Shared helpers used by all extractors."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from ..bucket.model import Bucket, Hash, Provenance
from ..integrity.sha256 import sha256_bucket


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_bucket_id() -> str:
    return f"bkt_{uuid.uuid4().hex}"


def build_bucket(
    *,
    origin: str,
    full_content: str,
    source_uri: str | None = None,
    derived_from: str | None = None,
    metadata: dict[str, Any] | None = None,
    bucket_id: str | None = None,
) -> Bucket:
    """Assemble a V1 Bucket with a computed SHA-256 hash."""
    bid = bucket_id or new_bucket_id()
    produced_at = _utcnow()

    draft = {
        "schema_version": "1",
        "bucket_id": bid,
        "provenance": {
            "origin": origin,
            "source_uri": source_uri,
            "derived_from": derived_from,
            "produced_at": produced_at.isoformat().replace("+00:00", "Z"),
        },
        "full_content": full_content,
        "metadata": metadata or {},
        "integrity_status": "unverified",
        "state": "RECEIVED",
        "lifecycle": {"received_at": produced_at.isoformat().replace("+00:00", "Z")},
        "optional_summary": None,
    }
    digest = sha256_bucket(draft)

    return Bucket(
        schema_version="1",
        bucket_id=bid,
        hash=Hash(algorithm="sha256", value=digest),
        provenance=Provenance(
            origin=origin,  # type: ignore[arg-type]
            source_uri=source_uri,
            derived_from=derived_from,
            produced_at=produced_at,
        ),
        full_content=full_content,
        metadata=metadata or {},
    )
