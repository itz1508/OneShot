"""Local demo entrypoint: serves the existing API and web/public/live.html from one origin (no npm, no Modal)."""

from pathlib import Path

from fastapi.staticfiles import StaticFiles

from mvp.api import app

app.mount("/", StaticFiles(directory=Path(__file__).parent / "web" / "public", html=True), name="web")
