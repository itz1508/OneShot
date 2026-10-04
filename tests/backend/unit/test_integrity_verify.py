"""Phase 9 — supplied-hash verification helper."""
from __future__ import annotations

import pytest

from rsm.extraction.text import extract_text
from rsm.integrity.sha256 import sha256_bucket
from rsm.integrity.verify import SuppliedHashMismatch, verify_supplied_hash


def test_matches_sets_verified() -> None:
    bucket = extract_text("integrity test")
    expected = sha256_bucket(bucket.model_dump(mode="json"))
    assert bucket.integrity_status == "unverified"
    verified = verify_supplied_hash(bucket, expected)
    assert verified.integrity_status == "verified"
    # Original is unchanged (we returned a copy).
    assert bucket.integrity_status == "unverified"


def test_mismatch_raises() -> None:
    bucket = extract_text("integrity test")
    with pytest.raises(SuppliedHashMismatch) as e:
        verify_supplied_hash(bucket, "0" * 64)
    assert e.value.expected == "0" * 64
    assert len(e.value.actual) == 64


def test_malformed_hash_raises() -> None:
    bucket = extract_text("x")
    with pytest.raises(SuppliedHashMismatch):
        verify_supplied_hash(bucket, "not-a-hash")
    with pytest.raises(SuppliedHashMismatch):
        verify_supplied_hash(bucket, "a" * 63)   # short
    with pytest.raises(SuppliedHashMismatch):
        verify_supplied_hash(bucket, "z" * 64)   # wrong charset
