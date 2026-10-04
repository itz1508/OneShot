"""SHA-256 integrity for canonical bucket payloads.

The hash fingerprints only the IDENTITY of the bucket content, i.e. the
frozen fields (A1):

    schema_version, bucket_id, provenance, full_content, metadata

Mutable fields (`state`, `lifecycle.*`, `integrity_status`, `optional_summary`)
are NOT part of the preimage, so lifecycle transitions never invalidate the
hash. The `hash` field is of course excluded from its own preimage.
"""

from __future__ import annotations

import hashlib
from typing import Any

from ..bucket.serializer import canonical_dumps

# Must match rsm.bucket.immutability.FROZEN_FIELDS. We duplicate it here
# because `rsm.integrity` is allowed to import from `rsm.bucket.serializer`
# only; redeclaring the tuple keeps `integrity` boundary-clean.
_IDENTITY_FIELDS: tuple[str, ...] = (
    "schema_version",
    "bucket_id",
    "provenance",
    "full_content",
    "metadata",
)


def sha256_bytes(data: bytes) -> str:
    """Hex SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def canonical_preimage(payload: Any) -> bytes:
    """Return the canonical bytes that `sha256_bucket` will hash.

    For a bucket-shaped dict: project to the IDENTITY (A1-frozen) fields and
    canonical-dump them. For any other dict/payload: canonical-dump as-is,
    excluding a top-level `hash` key if present.
    """
    if isinstance(payload, dict) and "bucket_id" in payload:
        projected = {k: payload[k] for k in _IDENTITY_FIELDS if k in payload}
        return canonical_dumps(projected)
    if isinstance(payload, dict) and "hash" in payload:
        return canonical_dumps({k: v for k, v in payload.items() if k != "hash"})
    return canonical_dumps(payload)


def sha256_bucket(payload: Any) -> str:
    """Hex SHA-256 over `canonical_preimage(payload)`.

    For a bucket-shaped payload the preimage is the A1-frozen identity fields.
    For other payloads (e.g. folder manifest) it's `canonical_dumps(payload)`.
    """
    return hashlib.sha256(canonical_preimage(payload)).hexdigest()
