"""MCP Research first slice: success, forged responses, and host transition gates."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from agent.contracts.research import Requirement, ResearchRecord
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE, digest_model
from agent.runtime.providers.base import ProviderError, ProviderRequest
from mvp.mcp_research import MCPResearchAdapter, _tool_json, register_mcp_research
from mvp.research_host import execute_research
from mvp.service import MVPError, MVPService


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
        "artifact_id": f"research-{task_id}-{run_id}",
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
    assert registry.default_provider == "echo"
    with pytest.raises(ProviderError, match="already registered"):
        register_mcp_research(registry)


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
    assert any(file["name"] == "_research.json" for file in service.artifacts_for_task(task_id))
    assert len([evt for evt in service.events(task_id) if evt["type"] == "stage_transition"]) == 1
    with pytest.raises(MVPError, match="not active"):
        execute_research(service, task_id)


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
    with pytest.raises(ProviderError, match="reported an error"):
        _tool_json(SimpleNamespace(is_error=True, content=[]))
    with pytest.raises(ProviderError, match="one JSON text"):
        _tool_json(SimpleNamespace(is_error=False, content=[SimpleNamespace(type="image")]))
