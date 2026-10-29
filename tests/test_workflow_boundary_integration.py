"""Local integration: template input -> SQLite -> bounded artifact readback.

No model, ChatGPT host, or MCP SDK is simulated or claimed as verified.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from build import BuildPolicy, run_build
from task import TaskStore
from workflow_templates import load_template, validate_quality_input


def _quality(stage: str, **extra: str) -> dict:
    return {
        "template_id": stage,
        "task_id": "t-local",
        "request_id": "req-local",
        "original_request": "Create a report containing the exact independently supplied fixture",
        "context_refs": ["fixture:known-file:line1"],
        "accepted_decision_refs": [],
        "unknowns": [],
        "readiness": "ready",
        **extra,
    }


def test_local_research_plan_build_boundary_uses_same_records_and_independent_output(tmp_path: Path) -> None:
    expected_bytes = b"fixture VALUE=3\n"
    expected_hash = hashlib.sha256(expected_bytes).hexdigest()
    source = tmp_path / "known.txt"
    source.write_bytes(expected_bytes)
    assert source.read_bytes() == expected_bytes
    store = TaskStore(tmp_path / "tasks.sqlite", scope="trusted-local")
    task = store.create_task(request_id="req-local", objective="Known fixture boundary")

    for stage in ("research", "plan", "build"):
        assert load_template(stage)["instructions"]

    assert validate_quality_input("research", _quality("research"))["readiness"] == "ready"
    research = {
        "type": "research", "id": "research-1", "request_id": "req-local",
        "findings": [{"statement": "Known source contains fixture VALUE=3", "source_refs": [f"fixture:known-file:sha256:{expected_hash}"]}],
        "validation_values": [{
            "id": "fixture-byte-value", "criterion": "Artifact matches independently supplied source",
            "expected": expected_bytes.decode(), "source_refs": [f"fixture:known-file:sha256:{expected_hash}"],
        }],
    }
    revision = store.save_host_result(task_id=task["id"], expected_revision=0, value=research)

    assert validate_quality_input("plan", _quality("plan", research_id="research-1"))["readiness"] == "ready"
    plan = {
        "type": "plan", "id": "plan-1", "request_id": "req-local", "research_id": "research-1",
        "actions": [{"description": "Create a byte-identical fixture report", "target": "report.txt"}],
        "validation_value_refs": ["fixture-byte-value"],
    }
    revision = store.save_host_result(task_id=task["id"], expected_revision=revision["revision"], value=plan)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    assert validate_quality_input("build", _quality(
        "build", plan_id="plan-1", approval_ref="operator:exact-task-plan-grant"
    ))["readiness"] == "ready"
    result = run_build(
        store=store, policy=BuildPolicy(workspace, frozenset({f"{task['id']}:plan-1"})),
        task_id=task["id"], expected_revision=revision["revision"], plan_id="plan-1",
        writes=[{"name": "report.txt", "content": expected_bytes.decode()}],
    )
    assert result["execution"]["outcome"] == "succeeded"
    assert result["verification"]["outcome"] == "valid"
    assert result["verification"]["evidence_refs"] == [f"sha256:{expected_hash}"]
    assert result["cleanup"]["outcome"] == "completed"
    assert (workspace / "artifacts" / "report.txt").read_bytes() == source.read_bytes()
    assert not (workspace / "build_tmp" / result["id"]).exists()
    reopened = TaskStore(tmp_path / "tasks.sqlite", scope="trusted-local")
    assert reopened.get_result(task["id"], "build", result["id"]) == result
    assert reopened.get_result(task["id"], "plan", "plan-1")["validation_value_refs"] == ["fixture-byte-value"]
    assert reopened.get_result(task["id"], "research", "research-1")["validation_values"] == research["validation_values"]
