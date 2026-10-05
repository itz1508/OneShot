"""FastAPI application factory for the RSM daemon."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..config import RSMConfig, resolve_config, set_active_config
from .errors import RSMError
from .routers import assessment, buckets, events, health, interactions, prov, reader


def create_app(config: RSMConfig | None = None) -> FastAPI:
    """Application factory.

    Configuration resolution (fail-closed) is documented in
    ``rsm.config.runtime``: explicit argument → ``RSM_CONFIG`` env var →
    ``./rsm.conf.toml`` → built-in defaults. The resolved config becomes the
    active one, so ``get_daemon()`` builds its store under
    ``persistence.root`` and CORS serves exactly ``daemon.allowed_origins``.
    """
    cfg = resolve_config(config)
    set_active_config(cfg)

    app = FastAPI(
        title="RSM Daemon",
        version="0.0.0",
        description="RSM V1 authoritative HTTP transport.",
    )

    # Fail-closed CORS (GAP-0007): only the configured exact origins get an
    # Access-Control-Allow-Origin header; everything else gets none. Defaults
    # are the two loopback dev origins; deployments override them in
    # rsm.conf.toml [daemon] allowed_origins.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.daemon.allowed_origins,
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
