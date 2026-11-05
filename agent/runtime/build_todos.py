"""Deterministic frozen-Plan to TaskTodo compilation. No effects or admission."""

from __future__ import annotations

from agent.contracts.common import ArtifactRef
from agent.contracts.planning import (
    BuildAction,
    BuildSpecification,
    CreateAction,
    ModifyAction,
    MoveAction,
    RemoveAction,
)
from agent.contracts.task_todo import Build, TaskTodo, paths_overlap
from agent.contracts.tool_registry import safe_relative_path


def _paths(action: BuildAction) -> tuple[str, ...]:
    if isinstance(action, CreateAction):
        return (safe_relative_path(action.target_path),)
    if isinstance(action, MoveAction):
        return (safe_relative_path(action.source_path), safe_relative_path(action.target_path))
    if isinstance(action, (ModifyAction, RemoveAction)):
        return (safe_relative_path(action.source_path),)
    raise ValueError("unsupported action")


def _preimages(action: BuildAction) -> dict[str, str | None]:
    paths = _paths(action)
    if isinstance(action, CreateAction):
        return {paths[0]: None}
    if isinstance(action, MoveAction):
        return {paths[0]: action.expected_source_digest, paths[1]: None}
    return {paths[0]: action.expected_source_digest}


def compile_build(spec: BuildSpecification, frozen_plan_ref: ArtifactRef) -> Build:
    """Pure compiler. Only the host can use the result after verifying admission."""
    if frozen_plan_ref.contract_id not in ("build_specification", "candidate_specification", "planning_record"):
        raise ValueError("unrecognized frozen Plan reference")
    if len({action.action_id for action in spec.actions}) != len(spec.actions):
        raise ValueError("duplicate source action")
    todos = tuple(
        TaskTodo(
            todo_id=action.action_id,
            todo_revision=1,
            title=f"{action.action_kind}: {action.action_id}",
            objective=spec.objective,
            source_action_ids=(action.action_id,),
            dependency_todo_ids=action.depends_on,
            authorized_paths=_paths(action),
            expected_preimages=_preimages(action),
            instructions=action.preconditions + action.validation_steps,
            verification=action.verification_tools,
            expected_result=action.expected_result,
            recovery_requirements=(action.recovery_requirement,),
        )
        for action in spec.actions
    )
    remaining = {todo.todo_id: todo for todo in todos}
    all_ids = set(remaining)
    for todo in todos:
        if todo.todo_id in todo.dependency_todo_ids:
            raise ValueError("self dependency")
        if not set(todo.dependency_todo_ids).issubset(all_ids):
            raise ValueError("unknown dependency")
    waves: list[tuple[str, ...]] = []
    complete: set[str] = set()
    while remaining:
        ready = [todo for todo in remaining.values() if set(todo.dependency_todo_ids).issubset(complete)]
        if not ready:
            raise ValueError("cyclic TaskTodo dependencies")
        paths: set[str] = set()
        batch: list[str] = []
        for todo in ready:
            if any(paths_overlap(path, occupied) for path in todo.authorized_paths for occupied in paths):
                continue
            paths.update(todo.authorized_paths)
            batch.append(todo.todo_id)
        if not batch:
            raise ValueError("unschedulable TaskTodo")
        waves.append(tuple(batch))
        complete.update(batch)
        for todo_id in batch:
            del remaining[todo_id]
    return Build(
        build_id=f"build:{spec.spec_id}:{frozen_plan_ref.artifact_digest}",
        frozen_plan_ref=frozen_plan_ref,
        todos=todos,
        waves=tuple(waves),
    )
