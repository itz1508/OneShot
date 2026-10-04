"""Event-log read endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ...daemon.service import DaemonService, get_daemon

router = APIRouter()


@router.get("/{bucket_id}")
async def events_for(bucket_id: str, daemon: DaemonService = Depends(get_daemon)):
    return {"bucket_id": bucket_id, "events": daemon.eventlog.read(bucket_id)}
