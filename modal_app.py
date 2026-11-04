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
PRIVATE_MODE_VALUE = os.environ.get("ONESHOT_MODAL_PRIVATE_MODE", "false").strip().lower()
if PRIVATE_MODE_VALUE not in {"true", "false"}:
    raise ValueError("ONESHOT_MODAL_PRIVATE_MODE must be true or false")
PRIVATE_MODE = PRIVATE_MODE_VALUE == "true"
if MODEL_SECRET_NAME and not PRIVATE_MODE:
    raise ValueError("model credentials require ONESHOT_MODAL_PRIVATE_MODE=true (Modal proxy authentication)")

# uv_sync installs locked dependencies but NOT the local project. Mount just
# the runtime source into a dedicated, virtualenv-free scan directory and put
# that directory on Python's module search path.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .uv_sync(extras=["meta", "mvp"], groups=[])
    .env({"PYTHONPATH": SOURCE_ROOT, "ONESHOT_STATE_ROOT": STATE_ROOT})
    .workdir(SOURCE_ROOT)
    .add_local_dir("agent", remote_path=f"{SOURCE_ROOT}/agent")
    .add_local_dir("mvp", remote_path=f"{SOURCE_ROOT}/mvp")
    .add_local_dir("api_fundamentals", remote_path=f"{SOURCE_ROOT}/api_fundamentals")
    .add_local_dir(".agents", remote_path=f"{SOURCE_ROOT}/.agents")
    .add_local_dir("settings", remote_path=f"{SOURCE_ROOT}/settings")
    .add_local_dir(
        "web",
        remote_path=f"{SOURCE_ROOT}/web",
        ignore=["**/node_modules/**", "**/dist/**", "**/.env*", "**/playwright-report/**", "**/test-results/**"],
    )
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
@modal.asgi_app(requires_proxy_auth=PRIVATE_MODE)
def web() -> object:
    import asyncio

    from fastapi import Request

    # These values must be set BEFORE importing mvp.api, because the host
    # captures both workspace authorization and state root at import time.
    os.environ["ONESHOT_STATE_ROOT"] = STATE_ROOT
    os.environ["MCP_WORKSPACE_ROOT"] = SOURCE_ROOT
    os.environ["MCP_TRUSTED_ANCESTRY"] = "true"
    os.environ["ONESHOT_RESEARCH_DISABLED"] = "false" if PRIVATE_MODE else "true"

    from fastapi.responses import JSONResponse

    from mvp.api import app as fastapi_app

    # Keep the SSE connection outside this lock. Only mutating requests and
    # their corresponding commit need serialization in the single container.
    mutation_lock = asyncio.Lock()

    @fastapi_app.middleware("http")
    async def persist_mutations(request: Request, call_next):
        # The public Audit demo never exposes model-backed Research, even if
        # a parent environment accidentally configures an MCP transport.
        if not PRIVATE_MODE and request.method == "POST" and request.url.path.endswith("/research"):
            return JSONResponse(status_code=403, content={"detail": "Research disabled on public Audit deployment"})
        if request.method not in {"POST", "PATCH"}:
            return await call_next(request)
        async with mutation_lock:
            response = await call_next(request)
            # Mutations are persisted before success is acknowledged. A failure
            # must propagate; Modal Volume does not offer SQLite transactions
            # across separately mounted containers or active revisions.
            await asyncio.to_thread(state_volume.commit)
            return response

    return fastapi_app
