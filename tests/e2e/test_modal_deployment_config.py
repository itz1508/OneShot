"""Modal deployment contract checks without external credentials or CLI."""

from __future__ import annotations

import asyncio
import runpy
import sys
import types
from pathlib import Path
from typing import Any

import pytest
from fastapi import Request


def _load_modal(monkeypatch: Any, *, secret: str = "", private: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    calls: dict[str, Any] = {"dirs": [], "secrets": [], "events": [], "commits": 0}

    class FakeImage:
        @staticmethod
        def debian_slim(**kwargs: Any) -> FakeImage:
            assert kwargs["python_version"] == "3.11"
            return FakeImage()

        def uv_sync(self, **kwargs: Any) -> FakeImage:
            calls["uv_sync"] = kwargs
            return self

        def env(self, vars: dict[str, str]) -> FakeImage:
            calls["env"] = vars
            return self

        def workdir(self, directory: str) -> FakeImage:
            calls["workdir"] = directory
            return self

        def add_local_dir(self, src: str, **kwargs: Any) -> FakeImage:
            calls["dirs"].append((src, kwargs["remote_path"]))
            return self

    class FakeVolume:
        def commit(self) -> None:
            if calls.get("commit_failure"):
                raise RuntimeError("Commit unavailable")
            calls["commits"] += 1

        @staticmethod
        def from_name(name: str, **kwargs: Any) -> FakeVolume:
            calls["volume"] = (name, kwargs)
            return FakeVolume()

    class FakeSecret:
        @staticmethod
        def from_name(name: str) -> str:
            calls["secrets"].append(name)
            return name

    class FakeApp:
        def __init__(self, name: str) -> None:
            calls["app"] = name

        def function(self, **kwargs: Any) -> Any:
            calls["function"] = kwargs

            def wrap(func: Any) -> Any:
                calls["events"].append("function")
                return func

            return wrap

    def concurrent(*, max_inputs: int) -> Any:
        calls["max_inputs"] = max_inputs

        def wrap(func: Any) -> Any:
            calls["events"].append("concurrent")
            return func

        return wrap

    def asgi_app(*, requires_proxy_auth: bool = False) -> Any:
        calls["proxy_auth"] = requires_proxy_auth

        def wrap(func: Any) -> Any:
            calls["events"].append("asgi")
            return func

        return wrap

    fake_modal = types.ModuleType("modal")
    fake_modal.Image = FakeImage  # type: ignore[attr-defined]
    fake_modal.Volume = FakeVolume  # type: ignore[attr-defined]
    fake_modal.Secret = FakeSecret  # type: ignore[attr-defined]
    fake_modal.App = FakeApp  # type: ignore[attr-defined]
    fake_modal.concurrent = concurrent  # type: ignore[attr-defined]
    fake_modal.asgi_app = asgi_app  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "modal", fake_modal)
    monkeypatch.setenv("ONESHOT_MODAL_APP_NAME", "existing-oneshot-app")
    monkeypatch.setenv("ONESHOT_MODAL_VOLUME_NAME", "existing-oneshot-volume")
    monkeypatch.setenv("ONESHOT_MODAL_PRIVATE_MODE", "true" if private else "false")
    if secret:
        monkeypatch.setenv("ONESHOT_MODAL_MODEL_SECRET", secret)
    else:
        monkeypatch.delenv("ONESHOT_MODAL_MODEL_SECRET", raising=False)

    root = Path(__file__).resolve().parents[2]
    module = runpy.run_path(str(root / "modal_app.py"))
    return calls, module


def test_public_modal_image_and_concurrency_contract(monkeypatch: Any) -> None:
    calls, module = _load_modal(monkeypatch)
    source = "/root/oneshot-source"

    assert calls["app"] == "existing-oneshot-app"
    assert calls["volume"] == ("existing-oneshot-volume", {"create_if_missing": True})
    assert calls["uv_sync"] == {"extras": ["meta", "mvp"], "groups": []}
    assert calls["env"] == {"PYTHONPATH": source, "ONESHOT_STATE_ROOT": "/data"}
    assert calls["workdir"] == source
    assert set(calls["dirs"]) == {
        ("agent", f"{source}/agent"),
        ("mvp", f"{source}/mvp"),
        ("api_fundamentals", f"{source}/api_fundamentals"),
        (".agents", f"{source}/.agents"),
        ("settings", f"{source}/settings"),
        ("web", f"{source}/web"),
    }
    assert calls["events"] == ["asgi", "concurrent", "function"]
    assert calls["max_inputs"] == 20
    assert calls["secrets"] == []
    assert calls["proxy_auth"] is False
    assert calls["function"]["max_containers"] == 1
    assert list(calls["function"]["volumes"]) == ["/data"]
    assert callable(calls["function"]["volumes"]["/data"].commit)
    assert calls["function"]["secrets"] == []
    assert callable(module["web"])


def test_model_secret_requires_private_modal_proxy_auth(monkeypatch: Any) -> None:
    with pytest.raises(ValueError, match="model credentials require"):
        _load_modal(monkeypatch, secret="existing-model-secret")

    calls, _ = _load_modal(monkeypatch, secret="existing-model-secret", private=True)
    assert calls["secrets"] == ["existing-model-secret"]
    assert calls["function"]["secrets"] == ["existing-model-secret"]
    assert calls["proxy_auth"] is True


def test_audit_root_set_before_api_import_and_mutations_committed(monkeypatch: Any) -> None:
    calls, module = _load_modal(monkeypatch)

    class FakeHTTPApp:
        middleware_func: Any = None

        def middleware(self, kind: str) -> Any:
            assert kind == "http"

            def register(func: Any) -> Any:
                self.middleware_func = func
                return func

            return register

    backend = FakeHTTPApp()
    fake_api = types.ModuleType("mvp.api")
    fake_api.app = backend  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mvp.api", fake_api)
    monkeypatch.setenv("MCP_TRUSTED_ANCESTRY", "false")
    monkeypatch.setenv("MCP_WORKSPACE_ROOT", "/tmp/untrusted")
    monkeypatch.setenv("ONESHOT_STATE_ROOT", "/tmp/old-state")
    monkeypatch.setenv("ONESHOT_RESEARCH_DISABLED", "false")

    assert module["web"]() is backend
    import os

    assert os.environ["MCP_TRUSTED_ANCESTRY"] == "true"
    assert os.environ["ONESHOT_RESEARCH_DISABLED"] == "true"
    assert os.environ["MCP_WORKSPACE_ROOT"] == "/root/oneshot-source"
    assert os.environ["ONESHOT_STATE_ROOT"] == "/data"

    async def call_next(_request: Request) -> object:
        return object()

    async def check(method: str) -> None:
        request = Request({"type": "http", "method": method, "path": "/", "headers": []})
        assert await backend.middleware_func(request, call_next) is not None

    asyncio.run(check("GET"))
    assert calls["commits"] == 0
    asyncio.run(check("POST"))
    asyncio.run(check("PATCH"))
    assert calls["commits"] == 2

    # Only write requests take the lock, and the commit occurs before the
    # response. Concurrent requests must not overlap mutations.
    active = 0
    peak = 0

    async def slow_write(_request: Request) -> object:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return object()

    async def parallel_writes() -> None:
        requests = [Request({"type": "http", "method": "POST", "path": "/api/tasks", "headers": []}) for _ in range(4)]
        await asyncio.gather(*(backend.middleware_func(req, slow_write) for req in requests))

    asyncio.run(parallel_writes())
    assert peak == 1
    assert calls["commits"] == 6

    # A model-backed endpoint is not reachable in the public Audit demo.
    async def research_blocked() -> object:
        request = Request({"type": "http", "method": "POST", "path": "/api/tasks/deadbeef/research", "headers": []})
        return await backend.middleware_func(request, call_next)

    blocked = asyncio.run(research_blocked())
    assert blocked.status_code == 403
    assert calls["commits"] == 6

    # Commit failures must never be misreported as successful writes.
    calls["commit_failure"] = True
    with pytest.raises(RuntimeError, match="Commit unavailable"):
        asyncio.run(check("POST"))
