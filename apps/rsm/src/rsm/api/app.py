"""FastAPI application factory for the RSM daemon."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .errors import RSMError
from .routers import assessment, buckets, events, health, interactions, prov, reader


def create_app() -> FastAPI:
    app = FastAPI(
        title="RSM Daemon",
        version="0.0.0",
        description="RSM V1 authoritative HTTP transport.",
    )

    @app.exception_handler(RSMError)
    async def _rsm_error_handler(_request, exc: RSMError):  # type: ignore[override]
        return JSONResponse(status_code=exc.http_status, content=exc.to_dict())

    app.include_router(buckets.router, prefix="/v1/buckets", tags=["buckets"])
    app.include_router(events.router, prefix="/v1/events", tags=["events"])
    app.include_router(prov.router, prefix="/v1/prov", tags=["prov"])
    app.include_router(interactions.router, prefix="/v1/interactions", tags=["interactions"])
    app.include_router(reader.router, prefix="/v1/buckets", tags=["reader"])
    app.include_router(assessment.router, prefix="/v1/buckets", tags=["assessment"])
    app.include_router(health.router)

    return app
