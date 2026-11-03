"""RFC 8785/JCS canonical serialization with SHA-256 digests.

Uses the `rfc8785` library for JSON Canonicalization Scheme and
hashlib for SHA-256. All digest-bearing artifacts use this module
to compute canonical bytes and digests.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

import rfc8785
from pydantic import BaseModel

if TYPE_CHECKING:
    pass

SERIALIZER_PROFILE = "rfc8785-jcs-sha256-v1"


def canonical_bytes(model: BaseModel) -> bytes:
    """Canonicalize a Pydantic model to RFC 8785 JSON bytes.

    Uses model_dump(mode="json") then rfc8785.dumps for canonicalization.
    rfc8785.dumps() returns bytes directly.
    """
    json_data = model.model_dump(mode="json")
    return rfc8785.dumps(json_data)


def digest_model(model: BaseModel) -> str:
    """Compute SHA-256 digest of canonicalized model bytes."""
    return hashlib.sha256(canonical_bytes(model)).hexdigest()


def digest_raw(data: bytes) -> str:
    """Compute SHA-256 digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def canonical_bytes_from_dict(data: dict[str, Any]) -> bytes:
    """Canonicalize a dict to RFC 8785 JSON bytes."""
    return rfc8785.dumps(data)


def digest_dict(data: dict[str, Any]) -> str:
    """Compute SHA-256 digest of canonicalized dict bytes."""
    return hashlib.sha256(canonical_bytes_from_dict(data)).hexdigest()
