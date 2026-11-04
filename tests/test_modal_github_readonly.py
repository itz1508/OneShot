"""Regression tests for the optional Modal GitHub inspection boundary."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "deployment/modal/github_clone.py"


@pytest.fixture
def github_module(monkeypatch: pytest.MonkeyPatch):
    """Load the actual code without requiring the external Modal SDK in CI."""

    class FakeImage:
        @staticmethod
        def debian_slim(**kwargs):
            return FakeImage()

        def pip_install(self, *args):
            return self

        def apt_install(self, *args):
            return self

    class FakeApp:
        def __init__(self, name):
            self.name = name

        def function(self, **kwargs):
            return lambda function: function

        def local_entrypoint(self):
            return lambda function: function

    fake_modal = SimpleNamespace(
        App=FakeApp,
        Image=FakeImage,
        Secret=SimpleNamespace(from_name=lambda name: name),
    )
    monkeypatch.setitem(sys.modules, "modal", fake_modal)
    spec = importlib.util.spec_from_file_location("oneshot_modal_github_readonly", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_valid_repo_is_normalized(github_module):
    assert (
        github_module._validated_github_url("https://github.com/itz1508/OneShot", "feature/safe")
        == "https://github.com/itz1508/OneShot.git"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/example/repo",
        "https://evil.example/example/repo",
        "https://github.com.evil.example/example/repo",
        "https://user:password@github.com/example/repo",
        "https://github.com/example/repo?token=leak",
        "https://github.com/example/repo#fragment",
        "https://github.com/example/../repo",
        "https://github.com/example/repo/extra",
        "https://github.com/example/",
    ],
)
def test_rejects_untrusted_git_url(github_module, url):
    with pytest.raises(ValueError):
        github_module._validated_github_url(url, "main")


@pytest.mark.parametrize("branch", ["-c", "../outside", "feature//oops", "refs@{1}", "feature."])
def test_rejects_invalid_branch(github_module, branch):
    with pytest.raises(ValueError):
        github_module._validated_github_url("https://github.com/example/repo", branch)


def test_clone_keeps_token_out_of_command_and_cleans_up(github_module, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "canary-secret-value")
    scratch = []

    def fake_run(cmd, *, env, capture_output, text, timeout, check):
        assert "canary-secret-value" not in " ".join(cmd)
        assert env["GIT_TERMINAL_PROMPT"] == "0"
        assert env["GIT_CONFIG_NOSYSTEM"] == "1"
        assert env["GIT_ASKPASS"]
        askpass = Path(env["GIT_ASKPASS"])
        assert askpass.exists()
        assert "canary-secret-value" not in askpass.read_text()
        checkout = Path(cmd[-1])
        checkout.mkdir()
        (checkout / "README.md").write_text("example")
        scratch.append(checkout)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(github_module.subprocess, "run", fake_run)
    result = github_module.clone_repo("https://github.com/example/repo")
    assert result == ["README.md"]
    assert scratch and not scratch[0].exists()


def test_clone_error_does_not_echo_credentials(github_module, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "canary-secret-value")

    def failed_run(*args, **kwargs):
        return SimpleNamespace(returncode=128, stderr="canary-secret-value")

    monkeypatch.setattr(github_module.subprocess, "run", failed_run)
    with pytest.raises(RuntimeError, match="GitHub clone failed") as exc:
        github_module.clone_repo("https://github.com/example/repo")
    assert "canary-secret-value" not in str(exc.value)
