"""Static deployment-configuration smoke test; no Modal account or CLI required."""

from __future__ import annotations

import runpy
import sys
import types
from pathlib import Path
from typing import Any


def test_modal_image_includes_mvp_and_runtime_assets(monkeypatch: Any) -> None:
    calls: dict[str, Any] = {"dirs": [], "secrets": []}

    class FakeImage:
        @staticmethod
        def debian_slim(**kwargs: Any) -> FakeImage:
            assert kwargs["python_version"] == "3.11"
            return FakeImage()

        def uv_sync(self, **kwargs: Any) -> FakeImage:
            calls["uv_sync"] = kwargs
            return self

        def add_local_dir(self, src: str, **kwargs: Any) -> FakeImage:
            calls["dirs"].append((src, kwargs["remote_path"]))
            return self

    class FakeVolume:
        @staticmethod
        def from_name(name: str, **kwargs: Any) -> str:
            calls["volume"] = (name, kwargs)
            return "fake-volume"

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
            return lambda func: func

    fake_modal = types.ModuleType("modal")
    fake_modal.Image = FakeImage  # type: ignore[attr-defined]
    fake_modal.Volume = FakeVolume  # type: ignore[attr-defined]
    fake_modal.Secret = FakeSecret  # type: ignore[attr-defined]
    fake_modal.App = FakeApp  # type: ignore[attr-defined]
    fake_modal.asgi_app = lambda: lambda func: func  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "modal", fake_modal)
    monkeypatch.setenv("ONESHOT_MODAL_APP_NAME", "existing-oneshot-app")
    monkeypatch.setenv("ONESHOT_MODAL_VOLUME_NAME", "existing-oneshot-volume")
    monkeypatch.setenv("ONESHOT_MODAL_MODEL_SECRET", "existing-model-secret")
    root = Path(__file__).resolve().parents[2]
    module = runpy.run_path(str(root / "modal_app.py"))

    assert calls["app"] == "existing-oneshot-app"
    assert calls["volume"] == ("existing-oneshot-volume", {"create_if_missing": True})
    assert calls["uv_sync"] == {"extras": ["meta", "mvp"], "groups": []}
    assert set(calls["dirs"]) == {
        ("agent", "/root/agent"),
        ("mvp", "/root/mvp"),
        ("api_fundamentals", "/root/api_fundamentals"),
        (".agents", "/root/.agents"),
        ("settings", "/root/settings"),
        ("web/public", "/root/web/public"),
    }
    assert calls["secrets"] == ["existing-model-secret"]
    assert calls["function"]["max_containers"] == 1
    assert calls["function"]["volumes"] == {"/data": "fake-volume"}
    assert calls["function"]["secrets"] == ["existing-model-secret"]
    assert callable(module["web"])
