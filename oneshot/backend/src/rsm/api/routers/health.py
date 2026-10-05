"""Health endpoint — thin router that mirrors the inline /healthz."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "schema_version": "1"}
