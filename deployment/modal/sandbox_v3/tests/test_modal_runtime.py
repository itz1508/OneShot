"""Local fake transport tests; never presented as a real Modal execution."""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_contracts import make_request

from modal_build_sandbox.contracts import Cleanup, Outcome
from modal_build_sandbox.modal_runtime import ModalRuntime
from modal_build_sandbox.recovery import AttemptStore
from modal_build_sandbox.runner import StandaloneRunner, _run_worker


class FakeModalRuntime:
    def __init__(self, base: Path, *, error: str | None = None):
        self.base = base
        self.error = error
        self.created = []
        self.terminated = []

    def create(self, req, name):
        if self.error == "create":
            raise RuntimeError("fake scheduling error")
        sb = SimpleNamespace(object_id=f"sb-{name}", root=self.base / name)
        sb.root.mkdir(parents=True)
        self.created.append(sb)
        return sb

    def upload(self, sb, req):
        (sb.root / "input").mkdir()
        (sb.root / "output").mkdir()
        shutil.copyfile(req.source_snapshot_ref, sb.root / "input" / "source.tar")
        shutil.copyfile(req.candidate_bundle_ref, sb.root / "input" / "bundle.zip")

    def execute(self, sb, _timeout):
        if self.error == "execute":
            raise RuntimeError("fake uncertain execution")
        req = self.req.model_copy(
            update={
                "source_snapshot_ref": str(sb.root / "input" / "source.tar"),
                "candidate_bundle_ref": str(sb.root / "input" / "bundle.zip"),
            }
        )
        _run_worker(req, sb.root / "workspace", sb.root / "output", sb.object_id)
        return 0

    def download(self, sb, target):
        files = []
        for name in ("result.json", "after.tar", "evidence.zip"):
            dest = target / name
            shutil.copyfile(sb.root / "output" / name, dest)
            files.append(dest)
        return tuple(files)

    def terminate(self, sb):
        self.terminated.append(sb.object_id)


def test_local_fake_good_and_bad_attempts(tmp_path):
    fake = FakeModalRuntime(tmp_path / "fake")
    state = AttemptStore(tmp_path / "attempts.sqlite")
    runner = StandaloneRunner(fake, state, tmp_path / "exports")
    bad = make_request(tmp_path / "bad", attempt="attempt-1", replacement="    return value.strip()\n")
    fake.req = bad
    result_bad = runner.execute(bad)
    assert result_bad.execution_status == Outcome.FAILED
    assert result_bad.cleanup_state == Cleanup.CONFIRMED
    assert state.get("op-1", "attempt-1")["state"] == "TERMINATION_RECORDED"

    good = make_request(tmp_path / "good", attempt="attempt-2")
    fake.req = good
    result_good = runner.execute(good)
    assert result_good.execution_status == Outcome.COMPLETED
    assert result_good.cleanup_state == Cleanup.CONFIRMED
    assert result_good.output_tree_digest
    assert [c.path for c in result_good.changed_paths] == ["app.py"]
    assert len(fake.created) == len(fake.terminated) == 2


def test_execution_loss_keeps_uncertainty(tmp_path):
    fake = FakeModalRuntime(tmp_path / "fake", error="execute")
    req = make_request(tmp_path / "source", attempt="attempt-1")
    fake.req = req
    store = AttemptStore(tmp_path / "state.sqlite")
    with pytest.raises(RuntimeError, match="uncertain"):
        StandaloneRunner(fake, store, tmp_path / "outputs").execute(req)
    assert store.get(req.operation_id, req.attempt_id)["state"] == "UNCERTAIN"
    assert fake.terminated


def test_scheduling_failure_is_not_success(tmp_path):
    fake = FakeModalRuntime(tmp_path / "fake", error="create")
    req = make_request(tmp_path / "source", attempt="attempt-1")
    fake.req = req
    store = AttemptStore(tmp_path / "state.sqlite")
    with pytest.raises(RuntimeError, match="scheduling"):
        StandaloneRunner(fake, store, tmp_path / "outputs").execute(req)
    assert store.get(req.operation_id, req.attempt_id)["state"] == "UNCERTAIN"


def test_modal_runtime_requires_configured_app_and_sdk():
    with pytest.raises(ValueError):
        ModalRuntime("bad/url")
    assert ModalRuntime("oneshot-build-sandbox", create_app=False).create_app is False


def test_local_fake_rejects_unauthorized_execution_effect(tmp_path):
    fake = FakeModalRuntime(tmp_path / "fake")
    state = AttemptStore(tmp_path / "attempts.sqlite")
    replacement = (
        "    from pathlib import Path\n"
        "    Path('unauthorized.py').write_text('side effect')\n"
        "    return value.strip().lower()\n"
    )
    req = make_request(tmp_path / "request", attempt="attempt-side-effect", replacement=replacement)
    fake.req = req
    runner = StandaloneRunner(fake, state, tmp_path / "exports")
    result = runner.execute(req)
    assert result.execution_status == Outcome.BLOCKED
    assert result.diagnostic_status == "not_valid"
    assert {x.path for x in result.changed_paths} == {"app.py", "unauthorized.py"}
    assert result.cleanup_state == Cleanup.CONFIRMED


def test_modal_create_does_not_inject_secrets_or_network(monkeypatch, tmp_path):
    import sys
    from types import ModuleType

    modal = ModuleType("modal")
    captured = {}

    class App:
        @staticmethod
        def lookup(name, **kwargs):
            captured["app"] = (name, kwargs)
            return object()

    class Image:
        @staticmethod
        def from_id(image_id):
            captured["image"] = image_id
            return object()

    class Sandbox:
        @staticmethod
        def create(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return SimpleNamespace(object_id="sb-test")

    modal.App, modal.Image, modal.Sandbox = App, Image, Sandbox
    monkeypatch.setitem(sys.modules, "modal", modal)
    req = make_request(tmp_path)
    sb = ModalRuntime("existing-modal-app", create_app=False).create(req, "task-attempt")
    assert sb.object_id == "sb-test"
    assert captured["app"] == ("existing-modal-app", {"create_if_missing": False})
    assert captured["image"] == "im-immutable-fixture"
    kw = captured["kwargs"]
    assert kw["block_network"] is True
    assert kw["secrets"] is None and kw["env"] == {}
    assert kw["volumes"] == {} and kw["network_file_systems"] == {}
    assert not kw["include_oidc_identity_token"] and not kw["pty"]
    assert "ports" not in kw and not kw.get("gpu")
