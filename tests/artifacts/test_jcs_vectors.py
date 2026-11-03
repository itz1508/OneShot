"""RFC 8785/JCS canonicalization tests — CAN01-CAN10."""

import hashlib

from pydantic import BaseModel

from agent.runtime.canonical_serialization import (
    SERIALIZER_PROFILE,
    canonical_bytes,
    canonical_bytes_from_dict,
    digest_dict,
    digest_model,
    digest_raw,
)


class SimpleDataModel(BaseModel):
    name: str
    value: int


class TestJCSVectors:
    def test_serializer_profile_defined(self):
        """CAN01: Serializer profile is defined and versioned."""
        assert SERIALIZER_PROFILE == "rfc8785-jcs-sha256-v1"

    def test_deterministic_serialization(self):
        """CAN02: Same model produces same canonical bytes."""
        m1 = SimpleDataModel(name="test", value=42)
        m2 = SimpleDataModel(name="test", value=42)
        assert canonical_bytes(m1) == canonical_bytes(m2)

    def test_digest_stability(self):
        """CAN03: Digest is stable SHA-256 hex."""
        m = SimpleDataModel(name="test", value=42)
        d = digest_model(m)
        assert len(d) == 64
        assert all(c in "0123456789abcdef" for c in d)

    def test_different_content_different_digest(self):
        """CAN04: Different content produces different digests."""
        m1 = SimpleDataModel(name="test", value=42)
        m2 = SimpleDataModel(name="test", value=43)
        assert digest_model(m1) != digest_model(m2)

    def test_raw_bytes_digest(self):
        """CAN05: Raw bytes digest matches hashlib."""
        data = b"hello world"
        assert digest_raw(data) == hashlib.sha256(data).hexdigest()

    def test_dict_canonicalization(self):
        """CAN06: Dict canonicalization is deterministic."""
        d1 = {"b": 2, "a": 1, "c": 3}
        d2 = {"a": 1, "b": 2, "c": 3}
        # JCS sorts keys, so different insertion order should produce same output
        assert canonical_bytes_from_dict(d1) == canonical_bytes_from_dict(d2)

    def test_unicode_preserved(self):
        """CAN07: Unicode strings preserved without normalization."""
        d = {"text": "café"}
        result = canonical_bytes_from_dict(d)
        assert "café".encode() in result

    def test_key_ordering(self):
        """CAN08: Keys are sorted by JCS rules."""
        d = {"zebra": 1, "apple": 2, "mango": 3}
        result = canonical_bytes_from_dict(d).decode("utf-8")
        # JCS sorts by UTF-16 code units
        assert result.index("apple") < result.index("mango")
        assert result.index("mango") < result.index("zebra")

    def test_digest_dict_stable(self):
        """CAN09: Dict digest is stable."""
        d = {"key": "value", "number": 42}
        assert digest_dict(d) == digest_dict(d)

    def test_empty_model_digest(self):
        """CAN10: Empty/minimal model produces valid digest."""

        class EmptyData(BaseModel):
            pass

        d = digest_model(EmptyData())
        assert len(d) == 64
