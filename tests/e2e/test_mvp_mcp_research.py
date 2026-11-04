"""MCP Research first slice: success, forged responses, and host transition gates."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.contracts.research import Requirement, ResearchRecord
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE, digest_model
from agent.runtime.providers.base import ProviderError, ProviderRequest
from mvp.mcp_research import (
    MCPResearchAdapter,
    _tool_json,
    mcp_child_environment,
    register_mcp_research,
    research_artifact_id,
)
from mvp.research_host import execute_research
from mvp.service import MVPError, MVPService


@pytest.fixture(autouse=True)
def configured_stub_transport(monkeypatch):
    monkeypatch.setenv("ONESHOT_MCP_COMMAND", "test-mcp-server")
    monkeypatch.setenv("ONESHOT_MCP_ARGS_JSON", "[]")
    monkeypatch.delenv("ONESHOT_MCP_URL", raising=False)


def response(task_id: str, *, wrong_digest: bool = False) -> dict:
    run_id = f"run-{task_id}"
    record = ResearchRecord(
        task_id=task_id,
        run_id=run_id,
        stage_revision=1,
        requirements=(
            Requirement(
                requirement_id="REQ-001",
                source_reference="submitted-request",
                original_wording="Investigate the repository",
                statement="Investigate the repository before implementation",
            ),
        ),
    )
    return {
        "stage": "research",
        "run_id": run_id,
        "task_id": task_id,
        "status": "completed",
        "artifact_id": research_artifact_id(task_id, run_id),
        "artifact_revision": 1,
        "artifact_digest": "f" * 64 if wrong_digest else digest_model(record),
        "artifact": record.model_dump(mode="json"),
        "contract_id": "research_record",
        "contract_version": "1.0",
        "serializer_profile": SERIALIZER_PROFILE,
        "finish_reason": "stop",
        "usage": {"total_tokens": 4},
        "provider": "oneshot-mcp",
        "model": "test-mcp",
    }


def request(task_id: str) -> ProviderRequest:
    return ProviderRequest(
        run_id=f"run-{task_id}",
        prompt=json.dumps({"task_id": task_id, "stage_payload": {"question": "inspect"}}),
    )


def test_adapter_registers_class_without_shadowing_echo():
    from agent.runtime.providers.registry import ProviderRegistry

    registry = ProviderRegistry()
    register_mcp_research(registry)
    assert registry.create("mcp_research").declared_capabilities().strict_tool_schemas
    assert registry.default_provider == "meta"
    with pytest.raises(ProviderError, match="already registered"):
        register_mcp_research(registry)


def test_adapter_preserves_configured_server_model(monkeypatch):
    task_id = "a" * 32

    async def invoke(_arguments):
        result = response(task_id)
        result["provider"] = "another-provider"
        result["model"] = "another-model"
        return result

    monkeypatch.setattr("mvp.mcp_research._invoke_tool", invoke)
    result = MCPResearchAdapter().generate(request(task_id))
    assert result.provider == "another-provider"
    assert result.model == "another-model"


def test_mcp_child_environment_excludes_unrelated_host_secrets(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "server-credential")
    monkeypatch.setenv("UNRELATED_HOST_SECRET", "must-not-pass")
    child_env = mcp_child_environment()
    assert child_env["MODEL_API_KEY"] == "server-credential"
    assert child_env["MCP_SERVER_MODE"] == "oneshot"
    assert "UNRELATED_HOST_SECRET" not in child_env


def test_real_host_persistence_and_stage_advance(tmp_path, monkeypatch):
    service = MVPService(tmp_path)
    task = service.create("Investigate the repository")
    task_id = task["task_id"]

    async def invoke(arguments):
        assert json.loads(arguments["prompt"])["task_id"] == task_id
        assert arguments["run_id"] == task["run_id"]
        return response(task_id)

    monkeypatch.setattr("mvp.mcp_research._invoke_tool", invoke)
    outcome = execute_research(service, task_id)
    assert outcome["status"] == "completed"
    assert outcome["current_stage"] == "audit_discovery"
    ref = outcome["artifact_ref"]
    assert service.artifacts.get_digest(ref["artifact_id"], 1) == ref["artifact_digest"]
    assert service.host.get_state(task_id).current_stage.value == "audit_discovery"
    assert service.get(task_id)["execution_status"] == "research_completed"
    assert service.get(task_id)["research_completed"] is True
    assert any(file["name"] == "_research.json" for file in service.artifacts_for_task(task_id))
    assert len([evt for evt in service.events(task_id) if evt["type"] == "stage_transition"]) == 1
    with pytest.raises(MVPError, match="not active"):
        execute_research(service, task_id)


def test_connected_stdio_mcp_research_and_host_transition(tmp_path, monkeypatch):
    """Exercise real MCP negotiation and tool call, followed by host persistence."""
    server = Path(__file__).parents[1] / "fixtures" / "mcp_research_server.py"
    monkeypatch.setenv("ONESHOT_MCP_COMMAND", sys.executable)
    monkeypatch.setenv("ONESHOT_MCP_ARGS_JSON", json.dumps([str(server)]))
    service = MVPService(tmp_path)
    task = service.create("Investigate the repository")

    result = execute_research(service, task["task_id"])

    assert result["status"] == "completed"
    assert result["current_stage"] == "audit_discovery"
    reference = result["artifact_ref"]
    assert service.artifacts.get_digest(reference["artifact_id"], 1) == reference["artifact_digest"]
    assert sum(event["type"] == "stage_transition" for event in service.events(task["task_id"])) == 1


def test_digest_forgery_never_advances(tmp_path, monkeypatch):
    service = MVPService(tmp_path)
    task_id = service.create("Inspect files")["task_id"]

    async def invoke(_arguments):
        return response(task_id, wrong_digest=True)

    monkeypatch.setattr("mvp.mcp_research._invoke_tool", invoke)
    with pytest.raises(MVPError, match="blocked"):
        execute_research(service, task_id)
    assert service.host.get_state(task_id).current_stage.value == "research"
    assert all(file["name"] != "_research.json" for file in service.artifacts_for_task(task_id))
    assert not any(event["type"] == "stage_transition" for event in service.events(task_id))


def test_mismatched_response_identity_rejected(monkeypatch):
    task_id = "a" * 32

    async def invoke(_arguments):
        reply = response(task_id)
        reply["run_id"] = "run-wrong"
        return reply

    monkeypatch.setattr("mvp.mcp_research._invoke_tool", invoke)
    with pytest.raises(ProviderError, match="identity mismatch"):
        MCPResearchAdapter().generate(request(task_id))


def test_unstructured_prompt_fails_without_call(monkeypatch):
    async def never(_arguments):
        raise AssertionError("should not run")

    monkeypatch.setattr("mvp.mcp_research._invoke_tool", never)
    with pytest.raises(ProviderError, match="invalid host"):
        MCPResearchAdapter().generate(ProviderRequest(run_id="run-a", prompt="plain language"))


def test_error_result_and_nontext_result_fail_closed():
    with pytest.raises(ProviderError, match="MCP Research tool failed: ONESHOT_UPSTREAM_ERROR"):
        _tool_json(
            SimpleNamespace(is_error=True, content=[], structured_content={"error_class": "ONESHOT_UPSTREAM_ERROR"})
        )
    with pytest.raises(ProviderError, match="one JSON text"):
        _tool_json(SimpleNamespace(is_error=False, content=[SimpleNamespace(type="image")], structured_content={}))


def test_http_research_endpoint_advances_only_after_host_receipts(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    import mvp.api

    service = MVPService(tmp_path)
    monkeypatch.setattr(mvp.api, "service", service)
    client = TestClient(mvp.api.app)
    created = client.post("/api/tasks", json={"prompt": "Research actual sources"})
    assert created.status_code == 201
    task_id = created.json()["task_id"]

    async def invoke(arguments):
        return response(json.loads(arguments["prompt"])["task_id"])

    monkeypatch.setattr("mvp.mcp_research._invoke_tool", invoke)
    executed = client.post(f"/api/tasks/{task_id}/research")
    assert executed.status_code == 200
    assert executed.json()["current_stage"] == "audit_discovery"
    stored = client.get(f"/api/tasks/{task_id}/artifacts").json()
    assert any(artifact["name"] == "_research.json" for artifact in stored)
    assert client.get(f"/api/tasks/{task_id}").json()["execution_status"] == "research_completed"


def test_http_forged_digest_is_502_and_stage_remains_open(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    import mvp.api

    service = MVPService(tmp_path)
    monkeypatch.setattr(mvp.api, "service", service)
    client = TestClient(mvp.api.app)
    task_id = client.post("/api/tasks", json={"prompt": "Research sources"}).json()["task_id"]

    async def invoke(_arguments):
        return response(task_id, wrong_digest=True)

    monkeypatch.setattr("mvp.mcp_research._invoke_tool", invoke)
    failed = client.post(f"/api/tasks/{task_id}/research")
    assert failed.status_code == 502
    assert client.get(f"/api/tasks/{task_id}").json()["current_stage"] == "research"
    assert all(file["name"] != "_research.json" for file in client.get(f"/api/tasks/{task_id}/artifacts").json())


def test_research_binds_latest_input_and_locks_later_changes(tmp_path, monkeypatch):
    service = MVPService(tmp_path)
    task_id = service.create("Initial request")["task_id"]
    service.revise_input(task_id, "Revised request", expected_revision=1)

    async def invoke(arguments):
        payload = json.loads(arguments["prompt"])
        assert payload["stage_payload"]["input_text"] == "Revised request"
        assert payload["stage_payload"]["input_digest"] == service.get(task_id)["input_digest"]
        return response(task_id)

    monkeypatch.setattr("mvp.mcp_research._invoke_tool", invoke)
    execute_research(service, task_id)
    with pytest.raises(MVPError, match="input locked"):
        service.revise_input(task_id, "Stale after Research", expected_revision=2)
    assert service.get(task_id)["input_text"] == "Revised request"


def test_canonical_research_artifact_identity():
    task_id = "a" * 32
    assert research_artifact_id(task_id, f"run-{task_id}") == "research-199ca5cc042c693d37482322e81e54e9"


def test_missing_transport_does_not_assign_work(tmp_path, monkeypatch):
    monkeypatch.delenv("ONESHOT_MCP_COMMAND")
    service = MVPService(tmp_path)
    task_id = service.create("Inspect sources")["task_id"]
    with pytest.raises(MVPError, match="Research transport unavailable"):
        execute_research(service, task_id)
    assert service.host.get_state(task_id).active_work_artifact_id is None


def test_mcp_text_and_structured_content_must_agree():
    valid = response("a" * 32)
    message = SimpleNamespace(type="text", text=json.dumps(valid))
    assert _tool_json(SimpleNamespace(is_error=False, content=[message], structured_content=valid)) == valid
    corrupted = dict(valid)
    corrupted["artifact_digest"] = "b" * 64
    with pytest.raises(ProviderError, match="mismatch"):
        _tool_json(SimpleNamespace(is_error=False, content=[message], structured_content=corrupted))
    with pytest.raises(ProviderError, match="mismatch"):
        _tool_json(SimpleNamespace(is_error=False, content=[message], structured_content=None))


def test_concurrent_research_invocation_rejected_without_duplicate_upstream_call(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    service = MVPService(tmp_path)
    task_id = service.create("Investigate the repository")["task_id"]
    entered = Event()
    release = Event()
    calls = []

    async def invoke(arguments):
        calls.append(arguments["run_id"])
        entered.set()
        assert release.wait(timeout=10)
        return response(task_id)

    monkeypatch.setattr("mvp.mcp_research._invoke_tool", invoke)
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = pool.submit(execute_research, service, task_id)
        try:
            assert entered.wait(timeout=10)
            with pytest.raises(MVPError, match="execution conflict"):
                execute_research(service, task_id)
        finally:
            release.set()
        assert result.result(timeout=10)["status"] == "completed"
    assert calls == [f"run-{task_id}"]
    assert [e["type"] for e in service.events(task_id)].count("stage_transition") == 1


def test_edit_rejected_during_research_and_not_persisted(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    service = MVPService(tmp_path)
    task_id = service.create("Inspect sources")["task_id"]
    entered = Event()
    release = Event()

    async def invoke(_arguments):
        entered.set()
        assert release.wait(timeout=10)
        return response(task_id)

    monkeypatch.setattr("mvp.mcp_research._invoke_tool", invoke)
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = pool.submit(execute_research, service, task_id)
        try:
            assert entered.wait(timeout=10)
            with pytest.raises(MVPError, match="execution conflict"):
                service.revise_input(task_id, "Should not be allowed", expected_revision=1)
        finally:
            release.set()
        result.result(timeout=10)
    assert service.get(task_id)["input_revision"] == 1


def test_recovery_event_reports_inner_failure_class(tmp_path, monkeypatch):
    from agent.contracts.work_todo import WorkStatus

    service = MVPService(tmp_path)
    task_id = service.create("Inspect sources")["task_id"]
    original = service.host.work_todos.set_status

    def status_with_failed_recovery(ref, action_id, status, **kwargs):
        if status is WorkStatus.FAILED:
            raise RuntimeError("simulated recovery fault")
        return original(ref, action_id, status, **kwargs)

    async def invoke(_arguments):
        return response(task_id, wrong_digest=True)

    monkeypatch.setattr(service.host.work_todos, "set_status", status_with_failed_recovery)
    monkeypatch.setattr("mvp.mcp_research._invoke_tool", invoke)
    with pytest.raises(MVPError, match="Research execution blocked"):
        execute_research(service, task_id)
    recovery = [e for e in service.events(task_id) if e["type"] == "mcp_research_recovery_required"]
    assert len(recovery) == 1
    assert "RuntimeError" in recovery[0]["message"]
    assert service.host.get_state(task_id).current_stage.value == "research"


def test_host_evidence_paths_are_forwarded_to_real_mcp_request(tmp_path, monkeypatch):
    import json as _json

    service = MVPService(tmp_path)
    task_id = service.create("Inspect repository source")["task_id"]
    monkeypatch.setenv(
        "ONESHOT_RESEARCH_WORKSPACE_PATHS_JSON", _json.dumps(["README.md", "agent/contracts/research.py"])
    )
    monkeypatch.setenv("MCP_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MCP_TRUSTED_ANCESTRY", "true")
    captured = []

    async def invoke(arguments):
        captured.append(_json.loads(arguments["prompt"])["stage_payload"]["evidence_sources"])
        return response(task_id)

    monkeypatch.setattr("mvp.mcp_research._invoke_tool", invoke)
    assert execute_research(service, task_id)["status"] == "completed"
    assert captured == [{"workspace_paths": ["README.md", "agent/contracts/research.py"], "snapshots": []}]


@pytest.mark.parametrize(
    "bad",
    [
        '["../secret"]',
        '["/etc/passwd"]',
        '["dir//ambiguous.txt"]',
        '["dir/./ambiguous.txt"]',
        '["dir\\\\escape.txt"]',
        '["README.md", "README.md"]',
        '{"workspace_paths": ["README.md"]}',
        '["' + ("x" * 4097) + '"]',
        '["README.md"',
    ],
)
def test_invalid_host_evidence_paths_fail_before_work_assignment(tmp_path, monkeypatch, bad):
    service = MVPService(tmp_path)
    task_id = service.create("Inspect repository source")["task_id"]
    monkeypatch.setenv("ONESHOT_RESEARCH_WORKSPACE_PATHS_JSON", bad)
    monkeypatch.setenv("MCP_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("MCP_TRUSTED_ANCESTRY", "true")
    with pytest.raises(MVPError):
        execute_research(service, task_id)
    assert service.host.get_state(task_id).current_stage.value == "research"
    assert service.host.get_state(task_id).active_work_artifact_id is None


def test_host_evidence_requires_trusted_workspace_root(tmp_path, monkeypatch):
    service = MVPService(tmp_path)
    task_id = service.create("Inspect evidence")["task_id"]
    monkeypatch.setenv("ONESHOT_RESEARCH_WORKSPACE_PATHS_JSON", '["README.md"]')
    monkeypatch.delenv("MCP_TRUSTED_ANCESTRY", raising=False)
    monkeypatch.setenv("MCP_WORKSPACE_ROOT", str(tmp_path))
    with pytest.raises(MVPError, match="MCP_TRUSTED_ANCESTRY"):
        execute_research(service, task_id)
    assert service.host.get_state(task_id).active_work_artifact_id is None


def test_live_research_host_dispatch_and_return_persisted(tmp_path, monkeypatch):
    """The existing host must allocate, verify, and persist the Research return route."""
    from agent.contracts.host import HostDispatchEnvelope, HostDispatchResult

    service = MVPService(tmp_path)
    task = service.create("Inspect authorized repository evidence")
    task_id = task["task_id"]

    async def invoke(arguments):
        route = json.loads(arguments["prompt"])["stage_payload"]["routing"]
        assert route["respond_to"] == "workflow_entry"
        assert route["authorized_role"] == "researcher"
        assert route["request_id"] == f"research-{task_id}"
        return response(task_id)

    monkeypatch.setattr("mvp.mcp_research._invoke_tool", invoke)
    outcome = execute_research(service, task_id)
    assert outcome["current_stage"] == "audit_discovery"
    envelope = HostDispatchEnvelope.model_validate_json(
        service.artifacts.get_verified(f"agent-dispatch:research-{task_id}", 1)
    )
    returned = HostDispatchResult.model_validate_json(
        service.artifacts.get_verified(f"agent-dispatch-result:research-{task_id}", 1)
    )
    assert (envelope.task_id, envelope.run_id, envelope.request_revision) == (task_id, task["run_id"], 1)
    assert envelope.role == "researcher"
    assert returned.respond_to == envelope.respond_to == "workflow_entry"
    assert returned.output_ref.artifact_digest == outcome["artifact_ref"]["artifact_digest"]
    events = [event["type"] for event in service.events(task_id)]
    assert "agent_dispatch_prepared" in events
    assert "agent_result_received" in events


def test_dispatch_rejects_wrong_workflow_role_before_upstream_call(tmp_path, monkeypatch):
    from agent.contracts.common import ArtifactRef
    from agent.runtime.canonical_serialization import SERIALIZER_PROFILE
    from agent.runtime.controller import TransitionError

    service = MVPService(tmp_path)
    task = service.create("Inspect authorized repository evidence")
    _, revision, digest = service.read_input(task["task_id"])
    input_ref = ArtifactRef(
        artifact_id=f"mvp-input:{task['task_id']}",
        artifact_revision=revision,
        artifact_digest=digest,
        contract_id="mvp_task_input",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )
    with pytest.raises(TransitionError, match="incorrect agent role"):
        service.host.prepare_agent_dispatch(task["task_id"], input_ref, "Inspect sources", requested_role="planner")
    assert service.host.get_state(task["task_id"]).active_work_artifact_id is None
    assert service.artifacts.latest_revision(f"agent-dispatch:research-{task['task_id']}") == 0


def test_cli_run_executes_existing_host_research(tmp_path, monkeypatch, capsys):
    """CLI run executes a real registered Research provider, not only task initialization."""
    from agent.cli import cmd_run

    service = MVPService(tmp_path)
    task = service.create("Investigate repository evidence")
    task_id = task["task_id"]

    async def invoke(arguments):
        assert json.loads(arguments["prompt"])["task_id"] == task_id
        return response(task_id)

    monkeypatch.setattr("mvp.mcp_research._invoke_tool", invoke)
    assert cmd_run(task_id, state_root=str(tmp_path)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "completed"
    assert result["current_stage"] == "audit_discovery"
    assert service.host.get_state(task_id).current_stage.value == "audit_discovery"
    assert service.artifacts.latest_revision(f"agent-dispatch-result:research-{task_id}") == 1


def test_cli_run_unknown_task_fails_without_creating_fake_work(tmp_path, capsys):
    from agent.cli import cmd_run

    task_id = "a" * 32
    assert cmd_run(task_id, state_root=str(tmp_path)) == 1
    assert "not found" in capsys.readouterr().err
    assert MVPService(tmp_path).host.get_state(task_id) is None


def test_cli_run_blocks_missing_upstream_provider(tmp_path, monkeypatch, capsys):
    from agent.cli import cmd_run

    service = MVPService(tmp_path)
    task_id = service.create("Inspect repository")["task_id"]

    async def unavailable(_arguments):
        raise ProviderError("provider not configured")

    monkeypatch.setattr("mvp.mcp_research._invoke_tool", unavailable)
    assert cmd_run(task_id, state_root=str(tmp_path)) == 1
    assert "Research blocked" in capsys.readouterr().err
    assert service.host.get_state(task_id).current_stage.value == "research"
