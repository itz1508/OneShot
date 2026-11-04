"""Real host-backed MVP behavior: state, immutable input, events, and recovery."""

import pytest

from mvp.service import MVPError, MVPService


def test_create_read_and_restart(tmp_path):
    first = MVPService(tmp_path)
    task = first.create("Inspect existing implementation")
    assert task["current_stage"] == "research"
    assert task["execution_status"] == "awaiting_mcp"
    assert task["research_completed"] is False
    task_id = task["task_id"]
    events = first.events(task_id)
    assert [event["type"] for event in events] == [
        "task_init",
        "mvp_input_persisted",
        "mvp_research_ready",
    ]

    restarted = MVPService(tmp_path)
    assert restarted.get(task_id) == task
    artifacts = restarted.artifacts_for_task(task_id)
    assert len(artifacts) == 1
    assert artifacts[0]["revision"] == 1
    assert "Inspect existing implementation" in artifacts[0]["content"]


def test_revision_conflict_preserves_previous_input(tmp_path):
    service = MVPService(tmp_path)
    initial = service.create("First input")
    updated = service.revise_input(initial["task_id"], "Second input", expected_revision=1)
    assert updated["input_revision"] == 2
    assert updated["input_text"] == "Second input"
    with pytest.raises(MVPError, match="revision conflict"):
        service.revise_input(initial["task_id"], "Stale modification", expected_revision=1)
    assert service.get(initial["task_id"])["input_text"] == "Second input"


def test_unknown_task_and_invalid_cursor_rejected(tmp_path):
    service = MVPService(tmp_path)
    with pytest.raises(MVPError, match="not found"):
        service.get("a" * 32)
    with pytest.raises(MVPError, match="invalid task identifier"):
        service.events("../escape")
    with pytest.raises(MVPError, match="invalid event cursor"):
        service.events("a" * 32, -1)


def test_event_cursor_no_duplicates(tmp_path):
    service = MVPService(tmp_path)
    item = service.create("Trace events")
    task_id = item["task_id"]
    events = service.events(task_id)
    assert service.events(task_id, events[-1]["sequence"]) == []
    assert service.events(task_id, events[0]["sequence"]) == events[1:]


def test_empty_input_not_persisted(tmp_path):
    service = MVPService(tmp_path)
    with pytest.raises(MVPError, match="1-20000"):
        service.create("   ")
