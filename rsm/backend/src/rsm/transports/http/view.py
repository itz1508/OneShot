"""Shape the canonical payload for the FastAPI HTTP layer.

The adapter is intentionally thin: FastAPI serializes a dict as JSON itself.
"""

from __future__ import annotations

from typing import Any

from ..canonical import CanonicalPayload


def http_view(payload: CanonicalPayload) -> dict[str, Any]:
    return {
        "schema_version": payload["schema_version"],
        "bucket": payload["bucket"],
        "integrity": {"sha256": payload["canonical_bytes_sha256_hex"]},
    }
