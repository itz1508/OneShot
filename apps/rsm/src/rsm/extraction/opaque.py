"""Opaque binary attachments — never claim extracted text."""

from __future__ import annotations

from ..bucket.model import Bucket
from ..integrity.sha256 import sha256_bytes
from ._common import build_bucket


def extract_opaque(
    data: bytes,
    *,
    source_uri: str | None = None,
    media_type: str | None = None,
) -> Bucket:
    """Produce a bucket whose full_content is empty and whose metadata notes
    the opaque payload's hash and length. Never fabricates a textual body."""
    metadata = {
        "opaque": True,
        "byte_length": len(data),
        "sha256_of_bytes": sha256_bytes(data),
        "media_type": media_type,
    }
    return build_bucket(
        origin="opaque",
        full_content="",
        source_uri=source_uri,
        metadata=metadata,
    )
