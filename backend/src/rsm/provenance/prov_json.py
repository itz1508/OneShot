"""W3C PROV-JSON projection of a provenance record.

Reference: https://www.w3.org/TR/prov-json/
"""

from __future__ import annotations

from datetime import timezone
from typing import Any

from .model import ProvenanceRecord


def to_prov_json(record: ProvenanceRecord) -> dict[str, Any]:
    """Produce a minimal PROV-JSON doc for one bucket's provenance."""
    bucket_qname = f"rsm:bucket/{record.bucket_id}"
    activity_qname = f"rsm:ingest/{record.bucket_id}"
    produced_at = (
        record.produced_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        if record.produced_at.tzinfo
        else record.produced_at.isoformat() + "Z"
    )

    doc: dict[str, Any] = {
        "prefix": {
            "rsm": "https://modelcontextprotocol.io/rsm#",
            "prov": "http://www.w3.org/ns/prov#",
        },
        "entity": {
            bucket_qname: {
                "prov:type": "rsm:Bucket",
                "rsm:origin": record.origin,
            }
        },
        "activity": {
            activity_qname: {
                "prov:type": "rsm:Ingest",
                "prov:startTime": produced_at,
                "prov:endTime": produced_at,
            }
        },
        "wasGeneratedBy": {
            f"_:gen-{record.bucket_id}": {
                "prov:entity": bucket_qname,
                "prov:activity": activity_qname,
                "prov:time": produced_at,
            }
        },
    }

    if record.source_uri:
        doc["entity"][bucket_qname]["rsm:sourceUri"] = record.source_uri

    if record.derived_from:
        parent = f"rsm:bucket/{record.derived_from}"
        doc["entity"].setdefault(parent, {"prov:type": "rsm:Bucket"})
        doc["wasDerivedFrom"] = {
            f"_:deriv-{record.bucket_id}": {
                "prov:generatedEntity": bucket_qname,
                "prov:usedEntity": parent,
            }
        }
    return doc
