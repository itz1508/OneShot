from datetime import datetime, timezone
from rsm.provenance.model import ProvenanceRecord
from rsm.provenance.prov_json import to_prov_json


def test_prov_json_contains_entity_and_activity():
    rec = ProvenanceRecord(
        bucket_id="bkt_1",
        origin="text",
        produced_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    doc = to_prov_json(rec)
    assert "rsm:bucket/bkt_1" in doc["entity"]
    assert "rsm:ingest/bkt_1" in doc["activity"]


def test_prov_json_derivation_links_parent():
    rec = ProvenanceRecord(
        bucket_id="child",
        origin="text",
        derived_from="parent",
        produced_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    doc = to_prov_json(rec)
    assert "wasDerivedFrom" in doc
    assert "rsm:bucket/parent" in doc["entity"]
