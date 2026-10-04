"""JSON export transport — writes canonical bytes to a bytes buffer."""

from __future__ import annotations

from ..bucket.serializer import canonical_dumps
from .canonical import CanonicalPayload


def to_json_export(payload: CanonicalPayload) -> bytes:
    """Return canonical JSON bytes identical to what the hash was computed over."""
    return canonical_dumps(
        {
            "schema_version": payload["schema_version"],
            "bucket": payload["bucket"],
            "integrity": {"sha256": payload["canonical_bytes_sha256_hex"]},
        }
    )
