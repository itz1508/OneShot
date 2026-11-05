import pytest
from test_contracts import make_request

from modal_build_sandbox.policy import check_commands, normalize_path


@pytest.mark.parametrize(
    "p",
    [
        "../passwd",
        "/tmp/a",
        "C:/x",
        "a\\b",
        ".git/config",
        ".env",
        "x//y",
        "x/./y",
        "x/../y",
        "x/.ssh/id",
        "a\x00b",
        "node_modules/a",
        "x/.env.secret",
    ],
)
def test_unsafe_paths(p):
    with pytest.raises(ValueError):
        normalize_path(p)


def test_allow_normal_paths():
    assert normalize_path("src/foo.py") == "src/foo.py"


def test_reject_corrupt_command_plan(tmp_path):
    req = make_request(tmp_path)
    with pytest.raises(ValueError, match="command plan"):
        check_commands(req.model_copy(update={"command_plan_sha256": "f" * 64}))


def test_reject_model_chosen_shell_command(tmp_path):
    req = make_request(tmp_path)
    malicious = req.focused_checks[0].model_copy(update={"argv": ("sh", "-c", "echo out")})
    from modal_build_sandbox.policy import commands_digest

    changed = req.model_copy(update={"focused_checks": (malicious,)})
    changed = changed.model_copy(update={"command_plan_sha256": commands_digest(changed)})
    with pytest.raises(ValueError, match="unadmitted command"):
        check_commands(changed)
