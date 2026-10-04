"""Supplied-hash verification (ADR 0003 + prompt §19 principle).

RSM verifies hashes supplied by a caller. It does NOT silently create source
authority by hashing content. The Bucket's A1 identity hash is always
computed by :func:`rsm.integrity.sha256.sha256_bucket`; this module adds
*caller-supplied* verification on top of it.

Flow:

    source bytes
        ↓
    build_bucket (identity hash computed)
        ↓
    verify_supplied_hash(bucket, expected_hex)
        → integrity_status = "verified" | "corrupt"
        → "verified": caller-supplied hash matches canonical preimage
        → "corrupt":  caller supplied a hash and it did NOT match

When no caller-supplied hash exists, the field stays ``"unverified"`` and
the Bucket is accepted — same as pre-Phase-9 behaviour.
"""

from __future__ import annotations

from ..bucket.model import Bucket
from .sha256 import sha256_bucket


class SuppliedHashMismatch(Exception):
    """Raised when a caller supplies a hash that does not match the Bucket's A1 identity."""

    def __init__(self, bucket_id: str, expected: str, actual: str) -> None:
        super().__init__(
            f"Supplied SHA-256 does not match Bucket {bucket_id!r} identity: "
            f"expected={expected} actual={actual}"
        )
        self.bucket_id = bucket_id
        self.expected = expected
        self.actual = actual


def verify_supplied_hash(bucket: Bucket, expected_hex: str) -> Bucket:
    """Verify a *caller-supplied* SHA-256 against the Bucket's A1 identity.

    On a match, returns a Bucket with ``integrity_status = "verified"``;
    on a mismatch, raises :class:`SuppliedHashMismatch` (the Bucket is NOT
    silently returned with ``"corrupt"``). The caller — typically a
    :class:`rsm.daemon.service.DaemonService` ingest method — is responsible
    for either reporting the failure or persisting a corrupt record;
    the current contract is: a hash mismatch rejects the ingestion entirely.
    """
    expected = (expected_hex or "").strip().lower()
    if len(expected) != 64 or not all(c in "0123456789abcdef" for c in expected):
        raise SuppliedHashMismatch(
            bucket.bucket_id,
            expected=expected_hex,
            actual="(malformed expected hash)",
        )
    actual = sha256_bucket(bucket.model_dump(mode="json"))
    if actual != expected:
        raise SuppliedHashMismatch(bucket.bucket_id, expected=expected, actual=actual)
    # pydantic BaseModel.model_copy preserves immutability-at-write enforcement
    # since this is an in-memory object; the write-back is done by the daemon.
    return bucket.model_copy(update={"integrity_status": "verified"})
