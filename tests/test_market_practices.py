"""Test market-practice alignment: default-deny, guardrails, event chain, checkpoint recovery."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agent.contracts.guardrails import GuardrailDecision, GuardrailRequest, GuardrailResult
from agent.contracts.host import Checkpoint
from agent.contracts.observability import EventStatus, ExecutionEvent
from agent.runtime.authorization import AuthorizationError, PathAuthorizer, RolePolicy
from agent.runtime.durable_checkpoint_store import SQLiteCheckpointStore
from agent.runtime.event_store import AppendOnlyEventStore
from agent.runtime.guardrails import GuardrailBlocked, run_blocking_guardrails

HEX = "a" * 64


def test_default_deny_and_protected_surface(tmp_path: Path):
    repo = tmp_path / "repo"
    out = tmp_path / "out"
    repo.mkdir()
    out.mkdir()
    auth = PathAuthorizer(
        RolePolicy(
            role="planner",
            allowed_tools=frozenset({"artifact_write"}),
            read_roots=(repo,),
            write_roots=(out,),
            scan_roots=(repo,),
        )
    )
    auth.authorize_tool("artifact_write")
    with pytest.raises(AuthorizationError):
        auth.authorize_tool("Bash")
    with pytest.raises(AuthorizationError):
        auth.authorize_write(repo / "app.py")
    assert auth.authorize_write(out / "planning.json") == (out / "planning.json").resolve()


def test_blocking_guardrail_stops_before_execution():
    request = GuardrailRequest(
        request_id="g",
        task_id="t",
        role="planner",
        boundary="tool",
        subject_digest=HEX,
        policy_version="1",
    )

    def deny(_):
        return GuardrailResult(
            request_id="g",
            decision=GuardrailDecision.DENY,
            policy_version="1",
            check_ids=("policy",),
            reason="denied",
            receipt_ref="r",
        )

    with pytest.raises(GuardrailBlocked):
        run_blocking_guardrails(request, [deny])


def test_event_store_is_hash_chained():
    store = AppendOnlyEventStore()
    event1 = ExecutionEvent(
        event_id="e1",
        task_id="t",
        run_id="r",
        stage="planning",
        phase="intake",
        status=EventStatus.STARTED,
        started_at=datetime.now(UTC),
    )
    digest = store.append(event1)
    event2 = ExecutionEvent(
        event_id="e2",
        previous_event_digest=digest,
        task_id="t",
        run_id="r",
        stage="planning",
        phase="intake",
        status=EventStatus.COMPLETED,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    store.append(event2)
    with pytest.raises(ValueError):
        store.append(event2.model_copy(update={"event_id": "e3", "previous_event_digest": HEX}))


def test_sqlite_checkpoint_survives_reopen(tmp_path: Path):
    path = tmp_path / "checkpoints.db"
    store = SQLiteCheckpointStore(path)
    checkpoint = Checkpoint(
        checkpoint_id="cp",
        checkpoint_revision=1,
        expected_previous_revision=0,
        checkpoint_digest=HEX,
        task_id="t",
        run_id="r",
        stage="planning",
        phase="intake",
        stage_revision=1,
        resume_point="next",
        created_at=datetime.now(UTC),
    )
    store.compare_and_swap(checkpoint)
    reopened = SQLiteCheckpointStore(path)
    assert reopened.get("cp") == checkpoint
