"""Actual file and model checks for Research handoff safety.

No mocked completion receipts: each invocation writes real temporary outputs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent.contracts.research_stage import ResearchRecord
from agent.workflows.research_runner import finalize_research
from agent.workflows.research_validation import load_research_contract, sha256


class _LocalTaskRecord:
    def __init__(self, metadata: dict):
        self.metadata = metadata


class _LocalTaskManager:
    """In-memory test adapter implementing the existing TaskManager API."""
    def __init__(self):
        self.tasks = {}

    def get_task(self, task_id):
        return self.tasks.get(task_id)

    def create_task(self, task_id, metadata):
        self.tasks[task_id] = _LocalTaskRecord(dict(metadata))
        return self.tasks[task_id]

    def set_task_metadata(self, task_id, metadata, *, if_revision):
        assert int(self.tasks[task_id].metadata.get("revision", 1)) == if_revision
        self.tasks[task_id].metadata = dict(metadata)


@pytest.fixture
def contract_path() -> Path:
    return Path(__file__).parents[1] / "agent/contracts/workflows/research.yaml"


def _record(original_request: str, **changes):
    fields = {
        "record_type": "research",
        "record_version": "1.0",
        "run_id": "run-1",
        "task_id": "task-1",
        "revision": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "request_digest": sha256(original_request.encode("utf-8")),
        "requirements": [{
            "requirement_id": "REQ-001",
            "original_wording": "Find supported behavior",
            "source_type": "original_request",
            "source_reference": "input-1",
            "research_question": "What does it support?",
            "evidence_needed": ["Official docs"],
            "finding_ids": ["FND-001"],
            "evidence_status": "supported",
        }],
        "findings": [{
            "finding_id": "FND-001",
            "statement": "Documented behavior",
            "requirement_ids": ["REQ-001"],
            "source_ids": ["SRC-001"],
            "evidence_status": "supported",
        }],
        "sources": [{
            "source_id": "SRC-001",
            "title": "Official reference",
            "source_type": "official_documentation",
            "url": "https://example.com/docs",
            "supported_claims": ["Documented behavior"],
            "requirement_ids": ["REQ-001"],
        }],
        "evidence": [{
            "evidence_id": "EVD-001",
            "reference": "https://example.com/docs",
            "observation": "Documentation describes the feature",
            "requirement_ids": ["REQ-001"],
        }],
        "todos": [{
            "todo_id": "TODO-001",
            "action": "Inspect docs",
            "expected_result": "Find official reference",
            "status": "completed",
            "evidence_ids": ["EVD-001"],
            "action_check": {
                "expected_result": "Find official reference",
                "status": "passed",
                "actual_result": "Official documentation inspected",
                "evidence_ids": ["EVD-001"],
            },
        }],
        "artifacts": [
            {"artifact_type": "request", "relative_path": "research_request.md", "revision": 1},
            {"artifact_type": "report", "relative_path": "final_report.md", "revision": 1},
            {"artifact_type": "record", "relative_path": "_research.json", "revision": 1},
        ],
    }
    fields.update(changes)
    return ResearchRecord.model_validate(fields)


def _run(
    tmp_path: Path, contract_path: Path, original: str, record=None, manager=None,
    report=("Research report with supported evidence [1].\n\n### Sources\n"
            "[1] Official reference: https://example.com/docs\n"), **kwargs,
):
    return finalize_research(
        record=record or _record(original),
        original_request=original,
        report_text=report,
        workspace=tmp_path,
        contract_path=contract_path,
        task_manager=manager or _LocalTaskManager(),
        **kwargs,
    )


def test_contract_has_13_actions_and_10_canonical_checks(contract_path):
    contract = load_research_contract(contract_path)
    assert len(contract["workflow"]) == 13
    assert len(contract["stage_validation"]["required_checks"]) == 10


def test_persists_actual_outputs_and_handoff(tmp_path, contract_path):
    manager = _LocalTaskManager()
    original = "One line\nsecond line\n\n"
    result = _run(tmp_path, contract_path, original, manager=manager)
    assert result.status == "passed", result.failure
    assert result.handoff_created
    stage = tmp_path / "task-1" / "research" / "revision-1"
    assert (stage / "research_request.md").read_bytes() == original.encode("utf-8")
    assert set(result.artifacts) == {"request", "report", "record"}
    assert result.artifacts["record"]["sha256"] == sha256((stage / "_research.json").read_bytes())
    persisted = manager.get_task("task-1").metadata["research_handoff"]
    assert persisted["receipt_ref"] == result.handoff_ref
    assert all(check.status == "passed" for check in result.checks)


def test_empty_research_rejected(tmp_path, contract_path):
    original = "hello"
    with pytest.raises(Exception):
        _record(original, requirements=[])
    with pytest.raises(Exception):
        _record(original, todos=[])


def test_missing_required_comparison_blocks_handoff(tmp_path, contract_path):
    result = _run(tmp_path, contract_path, "Compare A vs B", requested_comparisons=True)
    assert result.status == "failed"
    assert not result.handoff_created
    assert any(
        c.check_id == "check_requested_comparisons" and c.status == "failed"
        for c in result.checks
    )


def test_unresolved_requirement_is_covered_without_claiming_verified(tmp_path, contract_path):
    original = "Unknown support"
    record = _record(original, requirements=[{
        "requirement_id": "REQ-001",
        "original_wording": "Unknown support",
        "source_type": "original_request",
        "source_reference": "input-1",
        "research_question": "Supported?",
        "finding_ids": [],
        "evidence_status": "unresolved",
        "missing_evidence": ["Service is unavailable"],
        "investigation_needed": ["Obtain service API docs"],
    }], findings=[])
    result = _run(tmp_path, contract_path, original, record=record)
    assert result.status == "passed", result.failure


def test_pending_help_blocks_handoff(tmp_path, contract_path):
    original = "Independent check"
    record = _record(original, help_tasks=[{
        "help_task_id": "HELP-001",
        "objective": "Check compatibility",
        "requirement_ids": ["REQ-001"],
        "scope": "Official API support",
        "questions": ["Supported?"],
        "expected_result": "Source-backed assessment",
        "status": "running",
    }])
    result = _run(tmp_path, contract_path, original, record=record)
    assert result.status == "failed"
    assert not result.handoff_created


def test_failed_todo_cannot_finalize(tmp_path, contract_path):
    original = "Do research"
    record = _record(original, todos=[{
        "todo_id": "TODO-001", "action": "Search", "expected_result": "Find source",
        "status": "failed", "actual_error": "tool timeout", "recovery_reference": "checkpoint-1",
        "action_check": {
            "expected_result": "Find source", "actual_result": "Timeout", "status": "failed"
        },
    }])
    result = _run(tmp_path, contract_path, original, record=record)
    assert result.status == "failed"


def test_task_id_path_traversal_rejected(tmp_path, contract_path):
    with pytest.raises(Exception):
        _record("test", task_id="../../outside")


def test_prior_success_revision_is_immutable(tmp_path, contract_path):
    manager = _LocalTaskManager()
    original = "Original content"
    first = _run(tmp_path, contract_path, original, manager=manager)
    second = _run(tmp_path, contract_path, original, manager=manager)
    assert first.handoff_created
    assert second.status == "failed"
    assert not second.handoff_created


def test_invalid_record_on_disk_blocks_handoff(tmp_path, contract_path):
    original = "Research input"
    stage = tmp_path / "task-1" / "research" / "revision-1"
    stage.mkdir(parents=True)
    (stage / "_research.json").write_text('{"fake":"passed"}', encoding="utf-8")
    result = _run(tmp_path, contract_path, original)
    assert result.status == "failed"
    assert not result.handoff_created


def test_injected_fake_receipts_cannot_override_checks(tmp_path, contract_path):
    original = "Research input"
    rec = _record(original)
    assert not hasattr(rec, "stage_validation")
    assert not hasattr(rec, "validation_checks")
    result = _run(tmp_path, contract_path, original, record=rec, requested_recommendations=True)
    assert result.status == "failed"
    assert result.handoff_ref is None


def test_actual_task_manager_persists_receipt(tmp_path, contract_path):
    try:
        from tools.task_management import TaskManager
    except ImportError:
        pytest.skip("Full repository TaskManager is absent in isolated package")
    manager = TaskManager(storage_path=str(tmp_path / "tm.json"))
    original = "Research with real persistence"
    result = _run(tmp_path, contract_path, original, manager=manager)
    assert result.status == "passed", result.failure
    reloaded = TaskManager(storage_path=str(tmp_path / "tm.json"))
    receipt = reloaded.get_task("task-1").metadata["research_handoff"]["receipt_ref"]
    assert receipt == result.handoff_ref
