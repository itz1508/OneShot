from rsm.bucket.model import Bucket, Hash, Provenance
from datetime import datetime, timezone


def test_bucket_requires_schema_version_1():
    b = Bucket(
        bucket_id="bkt_x",
        hash=Hash(value="0" * 64),
        provenance=Provenance(origin="text", produced_at=datetime.now(timezone.utc)),
        full_content="hi",
    )
    assert b.schema_version == "1"


def test_bucket_rejects_bad_hash_pattern():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Hash(value="not-a-hex")
