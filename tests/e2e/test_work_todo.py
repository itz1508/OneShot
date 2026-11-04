"""Real host stores + workflow stages; no invented task success or mock state."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from agent.contracts.common import ArtifactRef
from agent.contracts.work_todo import PlannedAction, TodoList, WorkBinding, WorkPlan, WorkStatus
from agent.runtime.artifact_store import StaleRevisionError
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE
from agent.runtime.controller import HostController, Stage, TransitionError
from agent.runtime.work_todo import WorkTodoError


class WorkEvidence(BaseModel):
    value: str


def stored(controller: HostController, name: str, value: str) -> ArtifactRef:
    digest = controller.artifact_store.put_immutable(WorkEvidence(value=value), name, 1, "test_evidence", "1.0")
    return ArtifactRef(
        artifact_id=name,
        artifact_revision=1,
        artifact_digest=digest,
        contract_id="test_evidence",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )


def binding(controller: HostController, stage: str, label: str) -> WorkBinding:
    request = stored(controller, f"input-{label}", f"Assigned work: {label}")
    return WorkBinding(
        task_id="real-work",
        run_id="run-real",
        stage=stage,
        request_id=label,
        request_revision=1,
        input_request_ref=request,
    )


def run_action(controller: HostController, ref: ArtifactRef, action_id: str, result: str) -> ArtifactRef:
    _item, running = controller.work_todos.set_status(ref, action_id, WorkStatus.RUNNING)
    evidence = stored(controller, f"evidence-{action_id}", result)
    _item, done = controller.work_todos.set_status(
        running,
        action_id,
        WorkStatus.COMPLETED,
        actual_result=result,
        evidence_refs=(evidence,),
    )
    return done


def test_real_simple_to_complex_stage_handoff_and_restart(tmp_path) -> None:
    """Research collects actual evidence; Audit reads source and writes plan.md."""
    controller = HostController(tmp_path / "state")
    controller.init_task("real-work", "run-real")
    source = tmp_path / "source.py"
    source.write_text("def square(x):\n    return x * x\n", encoding="utf-8")

    research_scope = binding(controller, "research", "research-1")
    research_todos, r0 = controller.assign_work(
        research_scope,
        action="Read source.py and collect its definition",
        expected_result="Source fact with evidence",
    )
    assert len(research_todos.actions) == 1
    receipt = controller.issue_stage_receipt(Stage.RESEARCH, task_id="real-work", run_id="run-real")
    with pytest.raises(TransitionError, match="work list"):
        controller.advance_stage("real-work", "run-real", Stage.RESEARCH, receipt)
    source_fact = source.read_text(encoding="utf-8").strip()
    r1 = run_action(controller, r0, "work-1", source_fact)
    receipt = controller.issue_stage_receipt(Stage.RESEARCH, task_id="real-work", run_id="run-real")
    controller.advance_stage("real-work", "run-real", Stage.RESEARCH, receipt, todo_ref=r1)

    audit_scope = binding(controller, "audit_discovery", "audit-1")
    plan = WorkPlan(
        **audit_scope.model_dump(),
        actions=(
            PlannedAction(
                action_id="inspect",
                action="Inspect existing source",
                expected_result="Current behavior identified",
            ),
            PlannedAction(
                action_id="create-plan",
                action="Create plan.md with source-grounded findings",
                expected_result="plan.md written",
                depends_on=("inspect",),
            ),
        ),
    )
    plan_ref = controller.work_todos.persist_work_plan(plan)
    audit_todos, a0 = controller.assign_work(audit_scope, work_plan_ref=plan_ref)
    assert len(audit_todos.actions) == 2
    with pytest.raises(WorkTodoError, match="dependencies"):
        controller.work_todos.set_status(a0, "create-plan", WorkStatus.RUNNING)
    a1 = run_action(controller, a0, "inspect", source_fact)
    plan_path = tmp_path / "plan.md"
    plan_path.write_text(f"# Audit findings\n\n{source_fact}\n", encoding="utf-8")
    assert plan_path.exists()
    a2 = run_action(controller, a1, "create-plan", plan_path.read_text(encoding="utf-8"))

    restarted = HostController(tmp_path / "state")
    assert all(x.status is WorkStatus.COMPLETED for x in restarted.work_todos.read(a2).actions)
    audit_receipt = restarted.issue_stage_receipt(Stage.AUDIT_DISCOVERY, task_id="real-work", run_id="run-real")
    state = restarted.advance_stage("real-work", "run-real", Stage.AUDIT_DISCOVERY, audit_receipt, todo_ref=a2)
    assert state.current_stage is Stage.PLANNING
    events = restarted.event_store.list("real-work")
    assert sum(e["event_type"] == "work_todo_created" for e in events) == 2
    assert sum(e["event_type"] == "work_todo_updated" for e in events) == 6
    assert "square" in plan_path.read_text(encoding="utf-8")


def test_blocked_or_stale_work_cannot_complete_stage(tmp_path) -> None:
    controller = HostController(tmp_path)
    controller.init_task("real-work", "run-real")
    scope = binding(controller, "research", "research-1")
    _, first = controller.assign_work(scope, action="Gather evidence", expected_result="Evidence")
    receipt = controller.issue_stage_receipt(Stage.RESEARCH, task_id="real-work", run_id="run-real")
    _, running = controller.work_todos.set_status(first, "work-1", WorkStatus.RUNNING)
    with pytest.raises(StaleRevisionError):
        controller.work_todos.set_status(first, "work-1", WorkStatus.RUNNING)
    _, blocked = controller.work_todos.set_status(
        running, "work-1", WorkStatus.BLOCKED, actual_result="Source unavailable"
    )
    with pytest.raises(TransitionError, match="unfinished"):
        controller.advance_stage("real-work", "run-real", Stage.RESEARCH, receipt, todo_ref=blocked)
    with pytest.raises(TransitionError, match="stale"):
        controller.advance_stage("real-work", "run-real", Stage.RESEARCH, receipt, todo_ref=running)
    with pytest.raises(WorkTodoError, match="terminal"):
        controller.work_todos.set_status(blocked, "work-1", WorkStatus.RUNNING)


def test_work_plan_validation_and_replay_fail_closed(tmp_path) -> None:
    controller = HostController(tmp_path)
    scope = binding(controller, "research", "research-1")
    with pytest.raises(ValueError, match="cycle"):
        WorkPlan(
            **scope.model_dump(),
            actions=(
                PlannedAction(action_id="a", action="A", expected_result="a", depends_on=("b",)),
                PlannedAction(action_id="b", action="B", expected_result="b", depends_on=("a",)),
            ),
        )
    with pytest.raises(WorkTodoError, match="one action or"):
        controller.work_todos.start(scope)
    _, first = controller.work_todos.start(scope, action="Gather", expected_result="Evidence")
    controller.work_todos.set_status(first, "work-1", WorkStatus.RUNNING)
    again, ref = controller.work_todos.start(scope, action="Gather", expected_result="Evidence")
    assert again.actions[0].status is WorkStatus.RUNNING
    assert ref.artifact_revision == 2
    from agent.runtime.artifact_store import DuplicateArtifactError

    with pytest.raises(DuplicateArtifactError):
        controller.work_todos.start(scope, action="Changed objective", expected_result="Evidence")


def test_completed_todo_requires_actual_stored_evidence(tmp_path) -> None:
    controller = HostController(tmp_path)
    scope = binding(controller, "research", "research-1")
    _, ref = controller.work_todos.start(scope, action="Inspect", expected_result="Evidence")
    _, running = controller.work_todos.set_status(ref, "work-1", WorkStatus.RUNNING)
    with pytest.raises(WorkTodoError, match="requires actual result and evidence"):
        controller.work_todos.set_status(running, "work-1", WorkStatus.COMPLETED, actual_result="claimed")
    with pytest.raises(ValueError, match="completed actions"):
        TodoList.model_validate(
            {
                **controller.work_todos.read(running).model_dump(mode="json"),
                "actions": [
                    {
                        **controller.work_todos.read(running).actions[0].model_dump(mode="json"),
                        "status": "completed",
                        "actual_result": "claimed",
                        "evidence_refs": [],
                    }
                ],
            }
        )


def test_unassigned_work_cannot_bypass_host_stage_binding(tmp_path) -> None:
    controller = HostController(tmp_path)
    controller.init_task("real-work", "run-real")
    scope = binding(controller, "research", "research-1")
    _, unassigned = controller.work_todos.start(scope, action="Inspect", expected_result="Evidence")
    completed = run_action(controller, unassigned, "work-1", "source observed")
    observed = controller.work_todos.read(completed).actions[0].evidence_refs[0]
    receipt = controller.issue_stage_receipt(
        Stage.RESEARCH,
        task_id="real-work",
        run_id="run-real",
        artifact_id=observed.artifact_id,
        revision=observed.artifact_revision,
        artifact_digest=observed.artifact_digest,
    )
    with pytest.raises(TransitionError, match="host-assigned"):
        controller.advance_stage("real-work", "run-real", Stage.RESEARCH, receipt, todo_ref=completed)

    controller.assign_work(scope, action="Inspect", expected_result="Evidence")
    conflicting = binding(controller, "research", "research-2")
    with pytest.raises(TransitionError, match="already assigned"):
        controller.assign_work(conflicting, action="Different request", expected_result="Result")
