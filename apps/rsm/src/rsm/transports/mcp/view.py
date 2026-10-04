"""Shape the canonical payload for MCP resource reads.

MCP is a transport, not a persistence layer. Resource URI shape:
  rsm://bucket/<bucket_id>
"""

from __future__ import annotations

from typing import Any

from ..canonical import CanonicalPayload


def mcp_resource_view(payload: CanonicalPayload) -> dict[str, Any]:
    bucket = payload["bucket"]
    return {
        "uri": f"rsm://bucket/{bucket['bucket_id']}",
        "mimeType": "application/json",
        "text": None,  # payload travels in `contents` below for raw text if any
        "payload": {
            "schema_version": payload["schema_version"],
            "bucket": bucket,
            "integrity": {"sha256": payload["canonical_bytes_sha256_hex"]},
        },
    }
