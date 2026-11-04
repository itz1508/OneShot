"""Modal entrypoint for deploying the existing OneShot FastAPI backend.

This reuses ``mvp.api:app`` and keeps durable state in a Modal Volume so the
API can survive container restarts. The same FastAPI app also serves
``/live.html`` from the repository's ``web/public`` folder.
"""

from __future__ import annotations

import os

import modal

APP_NAME = "oneshot"
STATE_VOLUME_NAME = "oneshot-state"
STATE_ROOT = "/data"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("modal")
    .pip_install_from_requirements("requirements.txt")
)
state_volume = modal.Volume.from_name(STATE_VOLUME_NAME, create_if_missing=True)
app = modal.App(APP_NAME)


@app.function(
    image=image,
    timeout=300,
    volumes={STATE_ROOT: state_volume},
)
@modal.asgi_app()
def web() -> object:
    os.environ.setdefault("ONESHOT_STATE_ROOT", STATE_ROOT)
    os.environ.setdefault("ONESHOT_WEB_ORIGIN", "https://*.modal.run")
    from mvp.api import app as fastapi_app

    return fastapi_app
