import hashlib
from rsm.integrity.sha256 import sha256_bytes, sha256_bucket


def test_sha256_bytes_matches_hashlib():
    assert sha256_bytes(b"abc") == hashlib.sha256(b"abc").hexdigest()


def test_sha256_bucket_excludes_hash_field():
    draft = {
        "schema_version": "1",
        "bucket_id": "x",
        "hash": {"algorithm": "sha256", "value": "0" * 64},
        "full_content": "hello",
    }
    without_hash = {k: v for k, v in draft.items() if k != "hash"}
    assert sha256_bucket(draft) == sha256_bucket(without_hash)
