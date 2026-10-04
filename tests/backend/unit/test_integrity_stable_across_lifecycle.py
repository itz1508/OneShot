"""The hash reproduces across lifecycle mutations (A1 identity invariant)."""

from rsm.extraction.text import extract_text
from rsm.integrity.sha256 import canonical_preimage, sha256_bucket
import hashlib


def test_hash_reproduces_from_canonical_preimage():
    b = extract_text("stable identity")
    reproduced = hashlib.sha256(canonical_preimage(b.model_dump(mode="json"))).hexdigest()
    assert reproduced == b.hash.value


def test_lifecycle_change_does_not_invalidate_hash():
    """Simulate a lifecycle state mutation; A1 identity fields unchanged, hash reproduces."""
    b = extract_text("same identity, different state")
    original_hash = b.hash.value
    # Mutate mutable fields
    b.state = "STAGED"  # type: ignore[assignment]
    b.lifecycle.staged_at = b.provenance.produced_at
    reproduced = hashlib.sha256(canonical_preimage(b.model_dump(mode="json"))).hexdigest()
    assert reproduced == original_hash


def test_content_change_changes_hash():
    b1 = extract_text("content A")
    b2 = extract_text("content B")
    assert b1.hash.value != b2.hash.value


def test_metadata_change_changes_hash():
    import hashlib
    b = extract_text("hello")
    d1 = b.model_dump(mode="json")
    d2 = dict(d1)
    d2["metadata"] = {"tag": "added"}
    h1 = hashlib.sha256(canonical_preimage(d1)).hexdigest()
    h2 = hashlib.sha256(canonical_preimage(d2)).hexdigest()
    assert h1 != h2


def test_hash_field_excluded_from_preimage():
    b = extract_text("hello")
    d1 = b.model_dump(mode="json")
    d2 = dict(d1)
    d2["hash"] = {"algorithm": "sha256", "value": "f" * 64}
    # Changing hash field must not change the preimage of a bucket-shaped payload
    assert canonical_preimage(d1) == canonical_preimage(d2)
