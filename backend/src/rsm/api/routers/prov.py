"""W3C PROV-JSON projection endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...daemon.service import DaemonService, get_daemon
from ...provenance.model import ProvenanceRecord
from ...provenance.prov_json import to_prov_json
from ..errors import BucketNotFound

router = APIRouter()


@router.get("/{bucket_id}")
async def prov_for(bucket_id: str, daemon: DaemonService = Depends(get_daemon)):
    b = daemon.store.read(bucket_id)
    if b is None:
        raise BucketNotFound(
            f"No bucket with id {bucket_id!r}", details={"bucket_id": bucket_id}
        )
    rec = ProvenanceRecord(
        bucket_id=b.bucket_id,
        origin=b.provenance.origin,
        source_uri=b.provenance.source_uri,
        derived_from=b.provenance.derived_from,
        produced_at=b.provenance.produced_at,
    )
    return to_prov_json(rec)
