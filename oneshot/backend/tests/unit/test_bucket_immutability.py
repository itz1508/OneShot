"""A1 enforcement."""

import pytest
from rsm.bucket.immutability import BucketImmutabilityViolation, check_mutation


def _b(state: str, **over):
    base = {
        "schema_version": "1",
        "bucket_id": "bkt_1",
        "hash": {"algorithm": "sha256", "value": "a" * 64},
        "provenance": {"origin": "text", "produced_at": "2026-01-01T00:00:00Z"},
        "full_content": "hello",
        "metadata": {},
        "state": state,
    }
    base.update(over)
    return base


def test_mutable_before_stored_allowed():
    before = _b("STAGED")
    after = _b("STAGED", full_content="world")  # change content pre-STORED is allowed
    check_mutation(before, after)  # must not raise


def test_frozen_content_after_stored_rejected():
    before = _b("STORED")
    after = _b("STORED", full_content="world")
    with pytest.raises(BucketImmutabilityViolation):
        check_mutation(before, after)


def test_frozen_hash_after_activated_rejected():
    before = _b("ACTIVATED")
    after = _b("ACTIVATED", hash={"algorithm": "sha256", "value": "b" * 64})
    with pytest.raises(BucketImmutabilityViolation):
        check_mutation(before, after)


def test_mutable_state_change_after_stored_allowed():
    before = _b("STORED")
    after = _b("ACTIVATED")
    # 'state' is mutable; A1 does not block state progression
    check_mutation(before, after)
