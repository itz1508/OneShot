"""Boundary tests for reusable workflow instructions and existing result contracts.

These are contract/store tests, not a simulated Agent, template catalog, or
claim of end-to-end ChatGPT-host invocation.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from build import BuildPolicy, BuildRejected, run_build
from output.main import OutputRejected, validate_output
from task import TaskRejected, TaskStore


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "output" / "schema"
TEMPLATES = ROOT / "templates"


def test_three_templates_reference_only_their_existing_result_contracts() -> None:
    """A template is guidance, not a fourth output schema or hidden selector."""
    assert {path.name for path in TEMPLATES.glob("*.md")} == {
        "research.md", "plan.md", "build.md"
    }
    from workflow_templates import list_templates
    assert set(list_templates()) == {"research", "plan", "build"}
    for stage in ("research", "plan", "build"):
        contents = (TEMPLATES / f"{stage}.md").read_text(encoding="utf-8")
        assert f"output/schema/{stage}.json" in contents
        assert "No automatic next stage" in contents or "no automatic next stage" in contents
        schema = json.loads((SCHEMAS / f"{stage}.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)


def test_research_only_persists_grounded_findings_without_next_stage(tmp_path: Path) -> None:
    db = tmp_path / "state.sqlite"
    store = TaskStore(db, scope="thread-A")
    task = store.create_task(request_id="req-research", objective="Review one accepted source")
    source_bytes = b"retention=7\n"
    digest = hashlib.sha256(source_bytes).hexdigest()
    research = {
        "type": "research", "id": "r-1", "request_id": "req-research",
        "findings": [{
            "statement": "The source contains the exact bytes retention=7 followed by LF",
            "source_refs": [f"fixture:policy:{digest}:bytes=0-12"],
        }],
        "limitations": ["This finding does not establish broader retention policy"],
    }
    assert validate_output(research) == research
    revision = store.save_host_result(task_id=task["id"], expected_revision=0, value=research)
    assert revision["revision"] == 1
    store.finish_task(task_id=task["id"], expected_revision=1, result_type="research", result_id="r-1")
    reopened = TaskStore(db, scope="thread-A")
    assert reopened.get_final(task["id"]) == research
    assert [row["kind"] for row in reopened.events(task["id"])] == [
        "created", "result_recorded", "finalized"
    ]
    with pytest.raises(TaskRejected, match="not found"):
        reopened.get_result(task["id"], "plan", "p-1")


def test_plan_from_existing_context_does_not_require_research(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "tasks.sqlite", scope="thread-B")
    task = store.create_task(request_id="req-plan", objective="Prepare a read-only plan")
    plan = {
        "type": "plan", "id": "p-1", "request_id": "req-plan",
        "actions": [{"description": "Document the already accepted interface requirements"}],
        "limitations": ["Operator grant and an executable target are not established"],
    }
    assert validate_output(plan) == plan
    store.save_host_result(task_id=task["id"], expected_revision=0, value=plan)
    store.finish_task(task_id=task["id"], expected_revision=1, result_type="plan", result_id="p-1")
    assert store.get_final(task["id"]) == plan
    assert [event["kind"] for event in store.events(task["id"])] == [
        "created", "result_recorded", "finalized"
    ]


def test_research_plan_link_preserves_evidence_but_is_not_semantic_proof(tmp_path: Path) -> None:
    db = tmp_path / "state.sqlite"
    store = TaskStore(db, scope="thread-C")
    task = store.create_task(request_id="req-linked", objective="Plan from cited observation")
    evidence = {
        "type": "research", "id": "r-grounded", "request_id": "req-linked",
        "findings": [{"statement": "Source includes VALUE=3", "source_refs": ["source-A:bytes=0-7"]}],
    }
    plan = {
        "type": "plan", "id": "p-grounded", "request_id": "req-linked",
        "research_id": "r-grounded", "actions": [
            {"description": "Propose review of the recorded VALUE=3 evidence"}
        ],
    }
    step = store.save_host_result(task_id=task["id"], expected_revision=0, value=evidence)
    store.save_host_result(task_id=task["id"], expected_revision=step["revision"], value=plan)
    reopened = TaskStore(db, scope="thread-C")
    assert reopened.get_result(task["id"], "research", "r-grounded") == evidence
    assert reopened.get_result(task["id"], "plan", "p-grounded") == plan
    assert reopened.get_task(task["id"])["final_type"] is None
    # A link and matching wording do NOT prove a genuine semantic evaluation.


def test_typed_research_validation_values_are_storable_and_plan_can_reference_them(tmp_path: Path) -> None:
    """Optional typed handoffs survive SQLite; semantic linkage remains host-owned."""
    store = TaskStore(tmp_path / "typed.sqlite", scope="thread-E")
    task = store.create_task(request_id="req-typed", objective="Use independently known fixture")
    research = {
        "type": "research", "id": "r-grounded", "request_id": "req-typed",
        "findings": [{"statement": "Source value is 3", "source_refs": ["source:A:bytes:0-7"]}],
        "validation_values": [{
            "id": "value-1", "criterion": "Source must contain VALUE=3",
            "expected": "VALUE=3", "source_refs": ["source:A:bytes:0-7"],
        }],
    }
    plan = {
        "type": "plan", "id": "p-grounded", "request_id": "req-typed",
        "research_id": "r-grounded", "actions": [{"description": "Check existing expected bytes"}],
        "validation_value_refs": ["value-1"],
    }
    assert validate_output(research) == research
    assert validate_output(plan) == plan
    step = store.save_host_result(task_id=task["id"], expected_revision=0, value=research)
    store.save_host_result(task_id=task["id"], expected_revision=step["revision"], value=plan)
    reopened = TaskStore(tmp_path / "typed.sqlite", scope="thread-E")
    assert reopened.get_result(task["id"], "research", "r-grounded")["validation_values"] == research["validation_values"]
    assert reopened.get_result(task["id"], "plan", "p-grounded")["validation_value_refs"] == ["value-1"]


def test_invalid_validation_fields_do_not_pass_schema() -> None:
    research = {
        "type": "research", "id": "r", "request_id": "req",
        "findings": [], "validation_values": [{"id": "value-1", "expected": "guess"}],
    }
    plan = {
        "type": "plan", "id": "p", "request_id": "req",
        "actions": [], "validation_value_refs": ["missing-research"],
    }
    for invalid in (research, plan):
        with pytest.raises(OutputRejected):
            validate_output(invalid)


def test_plan_does_not_grant_build_and_no_artifact_is_written(tmp_path: Path) -> None:
    db = tmp_path / "state.sqlite"
    store = TaskStore(db, scope="thread-D")
    task = store.create_task(request_id="req-build", objective="Verify grant boundary")
    plan = {
        "type": "plan", "id": "p-approved", "request_id": "req-build",
        "actions": [{"description": "Produce reviewed evidence", "target": "report.txt"}],
    }
    store.save_host_result(task_id=task["id"], expected_revision=0, value=plan)
    workspace = tmp_path / "build"
    workspace.mkdir()
    with pytest.raises(BuildRejected, match="grant"):
        run_build(
            store=store, policy=BuildPolicy(workspace, frozenset()),
            task_id=task["id"], expected_revision=1, plan_id="p-approved",
            writes=[{"name": "report.txt", "content": "fixed expected output\n"}],
        )
    assert not (workspace / "artifacts" / "report.txt").exists()
    assert store.get_task(task["id"])["revision"] == 1
    assert [event["kind"] for event in store.events(task["id"])] == [
        "created", "result_recorded"
    ]


def test_research_validation_ids_must_be_unambiguous_and_plan_refs_exist(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "validation.sqlite", scope="thread-validation")
    task = store.create_task(request_id="req-values", objective="Independently verified references")
    evidence = {
        "type": "research", "id": "r-values", "request_id": "req-values",
        "findings": [{"statement": "Known fixture", "source_refs": ["fixture:hash:abc"]}],
        "validation_values": [
            {"id": "check-1", "criterion": "Expect known fixture", "expected": "value-1", "source_refs": ["fixture:hash:abc"]},
            {"id": "check-1", "criterion": "Different expectation", "expected": "value-2", "source_refs": ["fixture:hash:def"]},
        ],
    }
    with pytest.raises(TaskRejected, match="validation value"):
        store.save_host_result(task_id=task["id"], expected_revision=0, value=evidence)
    assert store.get_task(task["id"])["revision"] == 0
    assert [event["kind"] for event in store.events(task["id"])] == ["created"]
    evidence["validation_values"].pop()
    rev = store.save_host_result(task_id=task["id"], expected_revision=0, value=evidence)
    bad_plan = {
        "type": "plan", "id": "p-values", "request_id": "req-values", "research_id": "r-values",
        "actions": [{"description": "Use recorded value"}],
        "validation_value_refs": ["missing-id"],
    }
    with pytest.raises(TaskRejected, match="validation value"):
        store.save_host_result(task_id=task["id"], expected_revision=rev["revision"], value=bad_plan)
    assert store.get_task(task["id"])["revision"] == rev["revision"]
    assert [event["kind"] for event in store.events(task["id"])] == ["created", "result_recorded"]
    bad_plan["validation_value_refs"] = ["check-1"]
    store.save_host_result(task_id=task["id"], expected_revision=rev["revision"], value=bad_plan)
    assert store.get_result(task["id"], "plan", "p-values")["validation_value_refs"] == ["check-1"]
