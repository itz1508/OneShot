"""FastAPI application factory for the RSM daemon."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .errors import RSMError
from .routers import assessment, buckets, events, health, interactions, prov, reader

# Dev origins for the Next.js UI (http://localhost:3000). The daemon binds
# loopback only, and CORS here widens nothing else: only these two exact
# origins get readable responses; everything else gets no ACAO header.
_DEV_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


def create_app() -> FastAPI:
    app = FastAPI(
        title="RSM Daemon",
        version="0.0.0",
        description="RSM V1 authoritative HTTP transport.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_DEV_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
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
