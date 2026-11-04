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
    expected_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert all(finding.evidence_digest == expected_digest for finding in result.findings)


def test_empty_scope_is_not_verified(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_dummy.py").write_text("def test_ok(): assert True\n")
    result = scan(tmp_path)
    assert result.disposition == "not_e2e_verified"
    assert len(result.executed_capabilities) == 11


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


def test_audit_request_and_finding_ids_are_deterministic(tmp_path: Path) -> None:
    (tmp_path / "agent").mkdir()
    (tmp_path / "agent" / "__init__.py").write_text("")
    (tmp_path / "agent" / "broken.py").write_text("import agent.nonexistent\n")
    first = scan(tmp_path, capabilities=("contracts",), request="Audit broken imports")
    second = scan(tmp_path, capabilities=("contracts",), request="Audit broken imports")
    assert first.to_dict() == second.to_dict()
    assert first.request == "Audit broken imports"
    assert first.to_dict()["findings"][0]["finding_id"].startswith("AUD-")


def test_host_receipt_missing_artifact_identity_detected(tmp_path: Path) -> None:
    controller = tmp_path / "agent" / "runtime"
    controller.mkdir(parents=True)
    (controller / "controller.py").write_text(
        'def issue_stage_receipt(self, stage, task_id="", run_id="", revision=0, artifact_digest=""):\n'
        '    subject = f"stage_complete:{task_id}:{run_id}:{stage}"\n'
        "    return subject\n"
    )
    result = scan(tmp_path, capabilities=("state",))
    assert [item.code for item in result.findings] == ["RECEIPT_SUBJECT_UNBOUND"]
    assert "artifact_digest" in result.findings[0].message
    assert result.findings[0].status == "verified_observation"


def test_missing_frontend_lockfile_detected(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text('{"dependencies":{"react":"19.0.0"}}')
    result = scan(tmp_path, capabilities=("dependencies",))
    assert [item.code for item in result.findings] == ["FRONTEND_LOCKFILE_MISSING"]
    (web / "package-lock.json").write_text("{}")
    assert not scan(tmp_path, capabilities=("dependencies",)).findings


def test_frontend_missing_research_wiring_and_wrong_artifact_editor(tmp_path: Path) -> None:
    api = tmp_path / "mvp"
    ui = tmp_path / "web" / "src"
    api.mkdir()
    ui.mkdir(parents=True)
    (api / "api.py").write_text('@app.post("/api/tasks/{task_id}/research")\ndef research(): pass\n')
    (ui / "main.jsx").write_text("setActiveFile(file)\nsetEditText(task?.input_text || '')\nMCP integration pending\n")
    result = scan(tmp_path, capabilities=("frontend",))
    assert {item.code for item in result.findings} == {
        "RESEARCH_ACTION_UNWIRED",
        "ARTIFACT_EDITOR_INPUT_ALIAS",
        "STATIC_MCP_WARNING",
    }


def test_dynamic_frontend_api_prefix_is_not_mistaken_for_missing_route(tmp_path: Path) -> None:
    api = tmp_path / "mvp"
    ui = tmp_path / "web" / "src"
    api.mkdir()
    ui.mkdir(parents=True)
    (api / "api.py").write_text('@app.get("/api/tasks/{task_id}/events")\ndef events(): pass\n')
    (ui / "main.jsx").write_text("fetch('/api/tasks/' + taskId + '/events')\n")
    result = scan(tmp_path, capabilities=("wiring",))
    assert not result.findings


def test_unrecognized_static_api_route_reports_candidate(tmp_path: Path) -> None:
    api = tmp_path / "mvp"
    ui = tmp_path / "web" / "src"
    api.mkdir()
    ui.mkdir(parents=True)
    (api / "api.py").write_text('@app.get("/api/health")\ndef health(): pass\n')
    (ui / "main.jsx").write_text("fetch('/api/does-not-exist')\n")
    result = scan(tmp_path, capabilities=("wiring",))
    assert [finding.code for finding in result.findings] == ["API_ROUTE_REVIEW"]
    assert result.findings[0].status == "candidate"


def test_mvp_import_targets_are_checked(tmp_path: Path) -> None:
    (tmp_path / "mvp").mkdir()
    (tmp_path / "mvp" / "__init__.py").write_text("")
    (tmp_path / "mvp" / "service.py").write_text("import mvp.missing\n")
    result = scan(tmp_path, capabilities=("contracts",))
    assert [item.code for item in result.findings] == ["INTERNAL_IMPORT_MISSING"]


def test_unimplemented_function_is_reported_as_candidate(tmp_path: Path) -> None:
    (tmp_path / "service.py").write_text("def unfinished():\n    raise NotImplementedError()\n")
    result = scan(tmp_path, capabilities=("completeness",))
    assert [item.code for item in result.findings] == ["NOT_IMPLEMENTED_STUB"]
    assert result.findings[0].status == "candidate"


def test_audit_mode_unwired_reported_without_new_workflow(tmp_path: Path) -> None:
    ui = tmp_path / "web" / "src"
    ui.mkdir(parents=True)
    (ui / "main.jsx").write_text("const name = 'Research, Audit, Planning'\n")
    host = tmp_path / "mvp"
    host.mkdir()
    (host / "research_host.py").write_text("def research(): pass\n")
    result = scan(tmp_path, capabilities=("integration",))
    assert {finding.code for finding in result.findings} == {
        "AUDIT_SELECTOR_NOT_EXPOSED",
        "AUDIT_HOST_INVOCATION_UNWIRED",
    }


def test_in_process_lock_and_reconciliation_are_not_assumed_e2e(tmp_path: Path) -> None:
    host = tmp_path / "mvp"
    host.mkdir()
    (host / "service.py").write_text("self._active_guard = Lock()\n_active_requests: set[str]\n")
    (host / "research_host.py").write_text("'reconcile host state before retry'\n")
    result = scan(tmp_path, capabilities=("recovery",))
    assert {finding.code for finding in result.findings} == {
        "IN_PROCESS_ADMISSION_ONLY",
        "RECOVERY_RECONCILIATION_REQUIRED",
    }
    assert result.disposition == "findings_open"
