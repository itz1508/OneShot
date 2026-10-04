"""SINGLE canonical transport payload builder (Spec §11 — transport parity)."""

from __future__ import annotations

from typing import TypedDict, Any

from ..bucket.model import Bucket
from ..bucket.serializer import canonical_dumps


class CanonicalPayload(TypedDict):
    bucket: dict
    canonical_bytes_sha256_hex: str  # convenience; matches bucket.hash.value
    schema_version: str


def build_payload(bucket: Bucket) -> CanonicalPayload:
    """Build the single payload every transport returns.

    All transports MUST round-trip this dict verbatim (E2E-11 asserts parity).
    """
    projected: dict[str, Any] = bucket.model_dump(mode="json")
    _ = canonical_dumps(projected)  # determinism touch-point; not emitted
    return CanonicalPayload(
        bucket=projected,
        canonical_bytes_sha256_hex=bucket.hash.value,
        schema_version=bucket.schema_version,
    )
