from rsm.bucket.schema import canonical_schema, SCHEMA_VERSION


def test_schema_version_is_const_1():
    s = canonical_schema()
    assert SCHEMA_VERSION == "1"
    assert s["properties"]["schema_version"] == {"const": "1"}


def test_required_fields_present():
    s = canonical_schema()
    required = set(s["required"])
    assert {"schema_version", "bucket_id", "hash", "provenance", "full_content", "state"} <= required
