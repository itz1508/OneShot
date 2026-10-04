"""V3 Source Assessment endpoint — read-only.

Endpoint:

    GET /v1/buckets/{bucket_id}/assess

Returns a `SourceAssessment` DTO (see `rsm.assessment`). Pure, read-only;
no interaction gate (an assessment never releases source content — it
only describes what RSM's observation + preparation boundary promises).
Does NOT mutate the Bucket (A1 preserved).

This exists so that a host application can answer the §14 "RSM-first"
question — *does this request materially require external source
observation?* — without first opting into delivery via an
`InteractionRecord`. If the assessment answers no, the application may
proceed directly to the Agent; if yes, it configures an interaction and
streams the Prepared Representation through
`GET /v1/interactions/{id}/stream`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...assessment import assess_source
from ...daemon.service import DaemonService, get_daemon
from ..errors import BucketNotFound

router = APIRouter()


@router.get("/{bucket_id}/assess")
async def assess(
    bucket_id: str, daemon: DaemonService = Depends(get_daemon)
):
    """Read-only Source Assessment for a Bucket.

    No interaction gate: an assessment describes what RSM *would* observe
    and release; it does NOT release source content itself.
    """
    b = daemon.store.read(bucket_id)
    if b is None:
        raise BucketNotFound(
            f"No bucket with id {bucket_id!r}", details={"bucket_id": bucket_id}
        )
    return assess_source(b).model_dump(mode="json")
