"""Modal deployment of the existing OneShot FastAPI MVP.

The ASGI function serves the web/API runtime. Isolated Builder execution
belongs to a separate Modal Sandbox, not this function.
"""

from __future__ import annotations

import os

import modal

APP_NAME = os.environ.get("ONESHOT_MODAL_APP_NAME", "oneshot")
STATE_VOLUME_NAME = os.environ.get("ONESHOT_MODAL_VOLUME_NAME", "oneshot-state")
STATE_ROOT = "/data"
MODEL_SECRET_NAME = os.environ.get("ONESHOT_MODAL_MODEL_SECRET", "").strip()

# uv.lock is authoritative for runtime dependencies. The MVP extra includes
# FastAPI and MCP, which were missing from the meta-only requirements export.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .uv_sync(extras=["meta", "mvp"], groups=[])
    .add_local_dir("agent", remote_path="/root/agent")
    .add_local_dir("mvp", remote_path="/root/mvp")
    .add_local_dir("api_fundamentals", remote_path="/root/api_fundamentals")
    .add_local_dir(".agents", remote_path="/root/.agents")
    .add_local_dir("settings", remote_path="/root/settings")
    .add_local_dir("web/public", remote_path="/root/web/public")
)
state_volume = modal.Volume.from_name(STATE_VOLUME_NAME, create_if_missing=True)
app = modal.App(APP_NAME)
model_secrets = [modal.Secret.from_name(MODEL_SECRET_NAME)] if MODEL_SECRET_NAME else []


@app.function(
    image=image,
    timeout=300,
    max_containers=1,  # SQLite state is not safe for multi-container shared-file writes.
    volumes={STATE_ROOT: state_volume},
    secrets=model_secrets,
)
@modal.asgi_app()
def web() -> object:
    import asyncio

    from fastapi import Request

    os.environ["ONESHOT_STATE_ROOT"] = STATE_ROOT
    from mvp.api import app as fastapi_app

    @fastapi_app.middleware("http")
    async def persist_mutations(request: Request, call_next):
        response = await call_next(request)
        if request.method in {"POST", "PATCH"}:
            # Commit host records before acknowledging a mutating request.
            # A Modal Volume is not a distributed transactional database.
            await asyncio.to_thread(state_volume.commit)
        return response

    return fastapi_app
