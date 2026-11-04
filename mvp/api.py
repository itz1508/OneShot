"""FastAPI local MVP: real persisted input, state, replay and SSE; no fake agent execution."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agent.runtime.providers.base import ProviderError
from mvp.auth import AuthError, AuthManager
from mvp.mcp_research import mcp_transport_config
from mvp.service import MVPError, MVPService

DEFAULT_ROOT = Path(os.environ.get("ONESHOT_STATE_ROOT", "./.oneshot-state"))


def _csv_env(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    values = [value.strip() for value in raw.split(",") if value.strip()]
    return values or default


allowed_hosts = _csv_env("ONESHOT_ALLOWED_HOSTS", ["localhost", "127.0.0.1", "[::1]", "testserver"])
allowed_origins = _csv_env(
    "ONESHOT_WEB_ORIGINS",
    [os.environ.get("ONESHOT_WEB_ORIGIN", "http://localhost:5173")],
)

app = FastAPI(title="OneShot MVP API", version="0.1.0")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "Last-Event-ID"],
)
service = MVPService(DEFAULT_ROOT)
auth = AuthManager(DEFAULT_ROOT)
logger = logging.getLogger(__name__)


class SubmitTask(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    purpose: str = Field(default="research", pattern=r"^(research|audit)$")


class UpdateInput(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    expected_revision: int = Field(ge=1)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=2000)


def failure(exc: MVPError) -> HTTPException:
    message = str(exc)
    return HTTPException(
        status_code=404 if "not found" in message else 409 if "conflict" in message else 400,
        detail=message,
    )


def require_auth(request: Request) -> None:
    auth.require_request(request)


@app.get("/api/health")
def health(request: Request) -> dict[str, object]:
    try:
        mcp_transport_config()
    except ProviderError:
        configured = False
    else:
        configured = True
    payload = {"status": "ok", "mcp_transport_configured": configured}
    payload.update(auth.status(request))
    return payload


@app.get("/api/auth/session")
def auth_session(request: Request) -> dict[str, object]:
    return auth.status(request)


@app.post("/api/auth/login")
def auth_login(body: LoginRequest, request: Request, response: Response) -> dict[str, object]:
    try:
        session_id = auth.login(body.username, body.password)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    auth.set_cookie(response, request, session_id)
    return auth.status(request)


@app.post("/api/auth/logout")
def auth_logout(request: Request, response: Response) -> dict[str, object]:
    auth.revoke_request_session(request)
    auth.clear_cookie(response)
    return auth.status(request)


@app.post("/api/tasks", status_code=201, dependencies=[Depends(require_auth)])
def create_task(input: SubmitTask) -> dict[str, object]:
    try:
        return service.create(input.prompt, input.purpose)
    except MVPError as exc:
        raise failure(exc) from exc


@app.post("/api/tasks/{task_id}/research", dependencies=[Depends(require_auth)])
def start_research(task_id: str) -> dict[str, object]:
    from mvp.research_host import execute_research

    try:
        return execute_research(service, task_id)
    except MVPError as exc:
        if str(exc).startswith("Research execution blocked:"):
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        raise failure(exc) from exc


@app.post("/api/tasks/{task_id}/audit", dependencies=[Depends(require_auth)])
def start_audit(task_id: str) -> dict[str, object]:
    from mvp.research_host import execute_audit

    try:
        return execute_audit(service, task_id)
    except MVPError as exc:
        if str(exc).startswith("Audit execution blocked:"):
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        raise failure(exc) from exc


@app.get("/api/tasks/{task_id}", dependencies=[Depends(require_auth)])
def task_detail(task_id: str) -> dict[str, object]:
    try:
        return service.get(task_id)
    except MVPError as exc:
        raise failure(exc) from exc


@app.patch("/api/tasks/{task_id}/input", dependencies=[Depends(require_auth)])
def update_input(task_id: str, input: UpdateInput) -> dict[str, object]:
    try:
        return service.revise_input(task_id, input.text, input.expected_revision)
    except MVPError as exc:
        raise failure(exc) from exc


@app.get("/api/tasks/{task_id}/artifacts", dependencies=[Depends(require_auth)])
def task_artifacts(task_id: str) -> list[dict[str, object]]:
    try:
        return service.artifacts_for_task(task_id)
    except MVPError as exc:
        raise failure(exc) from exc


@app.get("/api/tasks/{task_id}/events", dependencies=[Depends(require_auth)])
def history(task_id: str, after: int = 0) -> list[dict[str, object]]:
    try:
        return service.events(task_id, after)
    except MVPError as exc:
        raise failure(exc) from exc


@app.get("/api/tasks/{task_id}/stream", dependencies=[Depends(require_auth)])
async def stream(task_id: str, request: Request, after: int = 0) -> StreamingResponse:
    try:
        service.get(task_id)
    except MVPError as exc:
        raise failure(exc) from exc

    raw_last_id = request.headers.get("last-event-id")
    if raw_last_id:
        try:
            after = max(after, int(raw_last_id))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid Last-Event-ID") from exc
    if after < 0:
        raise HTTPException(status_code=400, detail="invalid event cursor")

    async def generate() -> AsyncIterator[str]:
        cursor = after
        yield "retry: 2000\n\n"
        while not await request.is_disconnected():
            try:
                batch = service.events(task_id, cursor)
            except sqlite3.Error as exc:
                # Do not invent a persisted event or advance the replay cursor.
                # EventSource may reconnect using its last acknowledged event ID.
                logger.error("SSE event store read failed: %s", type(exc).__name__)
                yield 'event: stream_error\ndata: {"code":"EVENT_READ_FAILED","retryable":true}\n\n'
                return
            for event in batch:
                seq = int(event["sequence"])
                yield f"id: {seq}\nevent: activity\ndata: {json.dumps(event)}\n\n"
                cursor = seq
            await asyncio.sleep(0.5)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
