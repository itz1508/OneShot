"""Build-scoped TaskTodo records; distinct from stage-local WorkTodo tracking."""

from __future__ import annotations

from pydantic import Field, model_validator

from agent.contracts.common import ArtifactRef, ContractModel, DiagnosticStatus, Sha256, StepStatus
from agent.contracts.tool_registry import ToolInvocation, safe_relative_path


def paths_overlap(left: str, right: str) -> bool:
    """A file path also conflicts with any descendant path in the same namespace."""
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


class TaskTodo(ContractModel):
    todo_id: str = Field(min_length=1)
    todo_revision: int = Field(ge=1)
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    source_action_ids: tuple[str, ...] = Field(min_length=1)
    dependency_todo_ids: tuple[str, ...] = ()
    authorized_paths: tuple[str, ...] = Field(min_length=1)
    expected_preimages: dict[str, Sha256 | None]
    instructions: tuple[str, ...] = Field(min_length=1)
    verification: tuple[ToolInvocation, ...] = ()
    expected_result: str = Field(min_length=1)
    recovery_requirements: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_paths(self) -> TaskTodo:
        canonical = tuple(safe_relative_path(path) for path in self.authorized_paths)
        if canonical != self.authorized_paths or len(set(canonical)) != len(canonical):
            raise ValueError("invalid or duplicated todo paths")
        if set(self.expected_preimages) != set(self.authorized_paths):
            raise ValueError("preimage keys must exactly cover authorized paths")
        if len(set(self.source_action_ids)) != len(self.source_action_ids):
            raise ValueError("duplicate action identity")
        if len(set(self.dependency_todo_ids)) != len(self.dependency_todo_ids):
            raise ValueError("duplicate dependency")
        return self


class Build(ContractModel):
    build_id: str = Field(min_length=1)
    frozen_plan_ref: ArtifactRef
    todos: tuple[TaskTodo, ...] = Field(min_length=1)
    waves: tuple[tuple[str, ...], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_schedule(self) -> Build:
        lookup = {todo.todo_id: todo for todo in self.todos}
        if len(lookup) != len(self.todos):
            raise ValueError("duplicate todo ID")
        action_ids = [action_id for todo in self.todos for action_id in todo.source_action_ids]
        if len(set(action_ids)) != len(action_ids):
            raise ValueError("source Build action assigned to multiple TaskTodo records")
        scheduled: set[str] = set()
        for wave in self.waves:
            if not wave or len(set(wave)) != len(wave):
                raise ValueError("invalid wave")
            paths: set[str] = set()
            for todo_id in wave:
                todo = lookup.get(todo_id)
                if todo is None or todo_id in scheduled:
                    raise ValueError("unknown or repeated todo")
                if not set(todo.dependency_todo_ids).issubset(scheduled):
                    raise ValueError("dependency not complete before wave")
                if any(paths_overlap(path, occupied) for path in todo.authorized_paths for occupied in paths):
                    raise ValueError("overlapping wave paths")
                paths.update(todo.authorized_paths)
            scheduled.update(wave)
        if scheduled != set(lookup):
            raise ValueError("unscheduled todo")
        return self


class TodoExecution(ContractModel):
    build_id: str = Field(min_length=1)
    todo_id: str = Field(min_length=1)
    todo_revision: int = Field(ge=1)
    attempt_id: str = Field(min_length=1)
    execution_status: StepStatus
    diagnostic_status: DiagnosticStatus
    evidence_refs: tuple[ArtifactRef, ...] = ()
