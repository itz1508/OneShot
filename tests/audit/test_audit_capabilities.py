"""Read-only Audit capability regression fixtures."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from agent.audit.core import scan


def test_static_findings_are_not_e2e_success(tmp_path: Path) -> None:
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent" / "__init__.py").write_text("")
    source = tmp_path / "agent" / "work.py"
    source.write_text("import agent.missing\n# TODO: implement\n")
    result = scan(tmp_path, capabilities=("contracts", "completeness"))
    assert result.disposition == "findings_open"
    assert {finding.code for finding in result.findings} == {"INTERNAL_IMPORT_MISSING", "UNRESOLVED_COMMENT"}
    assert all(finding.evidence_digest == hashlib.sha256(source.read_bytes()).hexdigest() for finding in result.findings)


def test_empty_scope_is_not_verified(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_dummy.py").write_text("def test_ok(): assert True\n")
    result = scan(tmp_path)
    assert result.disposition == "not_e2e_verified"
    assert len(result.executed_capabilities) == 6


def test_escape_scope_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes repository"):
        scan(tmp_path, "..")


def test_unknown_capability_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown audit"):
        scan(tmp_path, capabilities=("nonexistent",))


def test_security_candidate_is_not_proven_exploit(tmp_path: Path) -> None:
    file = tmp_path / "task.py"
    file.write_text("import subprocess\nsubprocess.run('echo ok', shell=True)\n")
    result = scan(tmp_path, capabilities=("security",))
    assert {x.code for x in result.findings} == {"COMMAND_EXECUTION_REVIEW", "SHELL_TRUE_REVIEW"}
    assert all(x.status == "candidate" for x in result.findings)
