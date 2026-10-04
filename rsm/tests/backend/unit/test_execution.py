"""Execution state model (spec §10)."""

import pytest
from pydantic import ValidationError
from rsm.execution.model import (
    ExecutionState,
    ExecutionStatus,
    ExecutionTask,
    TaskStatus,
)


def test_default_state_not_started():
    es = ExecutionState(bucket_id="b1")
    assert es.state == ExecutionStatus.NOT_STARTED
    assert es.tasks == []


def test_tasks_json_round_trip():
    es = ExecutionState(
        bucket_id="b1",
        state=ExecutionStatus.IN_PROGRESS,
        tasks=[
            ExecutionTask(id="gate-1", status=TaskStatus.COMPLETE),
            ExecutionTask(id="gate-2", status=TaskStatus.PENDING, note="later"),
        ],
    )
    env = es.to_envelope()
    assert env["bucket_id"] == "b1"
    assert env["state"] == "IN_PROGRESS"
    assert env["tasks"][0]["status"] == "COMPLETE"


def test_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ExecutionState.model_validate({"bucket_id": "b", "extra": 1})
