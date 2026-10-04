"""V3 Reader endpoints — SCAN / Reader / ReaderTrace.

Read-only. Does NOT mutate the Bucket (A1 preserved). Does NOT touch Snapshot
or Replay delivery. Fails closed on unknown Bucket.

Endpoints:
    GET /v1/buckets/{bucket_id}/scan
    GET /v1/buckets/{bucket_id}/reader/read     (single bounded JSON chunk;
                                                 includes events[] + trace)
    GET /v1/buckets/{bucket_id}/reader/trace    (final trace only — the
                                                 continuous observation surface)

Rendering contract (consumed by the frontend ReaderTrace component):
  * ONE continuous bar; fill = latest_index / discovered; right-side number = latest_index.
  * NOT one bar per File.
  * Failures are a flat list keyed by `file_id` + `index`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...daemon.service import DaemonService, get_daemon
from ...reader import read_bucket, scan_bucket
from ..errors import BucketNotFound

router = APIRouter()


@router.get("/{bucket_id}/scan")
async def scan(bucket_id: str, daemon: DaemonService = Depends(get_daemon)):
    """Fast, shallow discovery for the Bucket.

    Simple-source Buckets return exactly one File. Folder-origin Buckets
    enumerate manifest entries (supported, opaque, unsupported) in canonical
    order. No bytes outside the Bucket's own `full_content` are read.
    """
    b = daemon.store.read(bucket_id)
    if b is None:
        raise BucketNotFound(
            f"No bucket with id {bucket_id!r}", details={"bucket_id": bucket_id}
        )
    return scan_bucket(b).model_dump(mode="json")


@router.get("/{bucket_id}/reader/read")
async def read(bucket_id: str, daemon: DaemonService = Depends(get_daemon)):
    """Reader observation over Scan output.

    Returns the ordered event sequence (`events[]`) and the derived
    `trace`. A per-File failure never terminates the loop (isolation
    invariant); the operation is `complete=True` once every discovered
    File has produced exactly one event.
    """
    b = daemon.store.read(bucket_id)
    if b is None:
        raise BucketNotFound(
            f"No bucket with id {bucket_id!r}", details={"bucket_id": bucket_id}
        )
    return read_bucket(b).model_dump(mode="json")


@router.get("/{bucket_id}/reader/trace")
async def trace(bucket_id: str, daemon: DaemonService = Depends(get_daemon)):
    """Current ReaderTrace only — the continuous observation surface.

    V3 Reader is deterministic and pure, so trace == read_bucket(b).trace;
    this endpoint is exposed separately so the UI can poll just the trace
    without re-receiving the event sequence.
    """
    b = daemon.store.read(bucket_id)
    if b is None:
        raise BucketNotFound(
            f"No bucket with id {bucket_id!r}", details={"bucket_id": bucket_id}
        )
    return read_bucket(b).trace.model_dump(mode="json")
