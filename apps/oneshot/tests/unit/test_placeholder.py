"""Placeholder test so the oneshot app's pytest run exits cleanly."""

from oneshot.__main__ import main


def test_placeholder_entrypoint(capsys):
    assert main() == 0
    assert "oneshot" in capsys.readouterr().out
