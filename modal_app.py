"""Modal ASGI wrapper for OneShot's existing FastAPI MVP.

The public deployment provides a source-bundle Audit demo only. Build
execution remains in a separately authorized Modal Sandbox. A model-backed
Research deployment needs separate access controls and MCP configuration.
"""

from __future__ import annotations

import os

import modal

APP_NAME = os.environ.get("ONESHOT_MODAL_APP_NAME", "oneshot")
STATE_VOLUME_NAME = os.environ.get("ONESHOT_MODAL_VOLUME_NAME", "oneshot-state")
STATE_ROOT = "/data"
SOURCE_ROOT = "/root/oneshot-source"
MODEL_SECRET_NAME = os.environ.get("ONESHOT_MODAL_MODEL_SECRET", "").strip()

# uv_sync installs locked dependencies but NOT the local project. Mount just
# the runtime source into a dedicated, virtualenv-free scan directory and put
# that directory on Python's module search path.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .uv_sync(extras=["meta", "mvp"], groups=[])
    .env({"PYTHONPATH": SOURCE_ROOT, "ONESHOT_STATE_ROOT": STATE_ROOT})
    .add_local_dir("agent", remote_path=f"{SOURCE_ROOT}/agent")
    .add_local_dir("mvp", remote_path=f"{SOURCE_ROOT}/mvp")
    .add_local_dir("api_fundamentals", remote_path=f"{SOURCE_ROOT}/api_fundamentals")
    .add_local_dir(".agents", remote_path=f"{SOURCE_ROOT}/.agents")
    .add_local_dir("settings", remote_path=f"{SOURCE_ROOT}/settings")
    .add_local_dir("web/public", remote_path=f"{SOURCE_ROOT}/web/public")
)
state_volume = modal.Volume.from_name(STATE_VOLUME_NAME, create_if_missing=True)
app = modal.App(APP_NAME)
# No model secret is attached by default. Never enable this on an unprotected
# public endpoint: model-backed Research requires operator-owned access control.
model_secrets = [modal.Secret.from_name(MODEL_SECRET_NAME)] if MODEL_SECRET_NAME else []


@app.function(
    image=image,
    timeout=300,
    max_containers=1,  # Do not share mutable SQLite files across Modal containers.
    volumes={STATE_ROOT: state_volume},
    secrets=model_secrets,
)
@modal.concurrent(max_inputs=20)  # SSE must not monopolize the only ASGI input slot.
@modal.asgi_app()
def web() -> object:
    import asyncio

    from fastapi import Request

    # These values must be set BEFORE importing mvp.api, because the host
    # captures both workspace authorization and state root at import time.
    os.environ["ONESHOT_STATE_ROOT"] = STATE_ROOT
    os.environ["MCP_WORKSPACE_ROOT"] = SOURCE_ROOT
    os.environ["MCP_TRUSTED_ANCESTRY"] = "true"

    from mvp.api import app as fastapi_app

    @fastapi_app.middleware("http")
    async def persist_mutations(request: Request, call_next):
        response = await call_next(request)
        if request.method in {"POST", "PATCH"}:
            # The Volume is explicit-commit storage, not a transactional DB.
            # Do not report durable completion if commit fails.
            await asyncio.to_thread(state_volume.commit)
        return response

    return fastapi_app
