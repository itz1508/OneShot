"""Shared, immutable work-tracking records; never grant effect authorization.

Single work automatically becomes one action. Complex work derives actionable
items from a separately persisted, request-bound agent work plan.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from agent.contracts.common import ArtifactRef, ContractModel

StageId = Literal["research", "audit_discovery", "planning", "fixture_validation", "build", "build_validation"]


class WorkStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class WorkBinding(ContractModel):
    task_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    stage: StageId
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    request_revision: int = Field(ge=1)
    input_request_ref: ArtifactRef


class PlannedAction(ContractModel):
    action_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    action: str = Field(min_length=1)
    expected_result: str = Field(min_length=1)
    depends_on: tuple[str, ...] = ()


class WorkPlan(WorkBinding):
    """Role-local action decomposition; not a Planner BuildSpecification."""

    actions: tuple[PlannedAction, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_plan(self) -> WorkPlan:
        _check_action_graph(self.actions)
        return self


class TodoAction(PlannedAction):
    status: WorkStatus = WorkStatus.PENDING
    actual_result: str = ""
    evidence_refs: tuple[ArtifactRef, ...] = ()

    @model_validator(mode="after")
    def check_status_evidence(self) -> TodoAction:
        if self.status is WorkStatus.COMPLETED and (not self.actual_result or not self.evidence_refs):
            raise ValueError("completed actions require actual result and persisted evidence")
        if self.status in {WorkStatus.FAILED, WorkStatus.BLOCKED} and not self.actual_result:
            raise ValueError("failed or blocked actions require an actual reason")
        if self.status in {WorkStatus.PENDING, WorkStatus.RUNNING} and (self.actual_result or self.evidence_refs):
            raise ValueError("uncompleted actions cannot claim results or evidence")
        return self


class TodoList(WorkBinding):
    """Immutable revision of one role's work; stored by host ArtifactStore CAS."""

    generation: Literal["automatic_single", "plan_derived"]
    work_plan_ref: ArtifactRef | None = None
    actions: tuple[TodoAction, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def check_generation(self) -> TodoList:
        _check_action_graph(self.actions)
        if self.generation == "automatic_single":
            if self.work_plan_ref is not None or len(self.actions) != 1:
                raise ValueError("single-work generation requires exactly one action and no plan")
        elif self.work_plan_ref is None or len(self.actions) < 2:
            raise ValueError("complex work requires a stored plan and at least two actions")
        return self


def _check_action_graph(actions: tuple[PlannedAction, ...] | tuple[TodoAction, ...]) -> None:
    """Reject missing, duplicate, and cyclic dependencies before work starts."""
    by_id = {item.action_id: item for item in actions}
    if len(by_id) != len(actions):
        raise ValueError("duplicate work action ID")
    for item in actions:
        if len(set(item.depends_on)) != len(item.depends_on):
            raise ValueError(f"duplicate dependency for {item.action_id}")
        if set(item.depends_on) - by_id.keys():
            raise ValueError(f"unknown work dependency for {item.action_id}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(action_id: str) -> None:
        if action_id in visiting:
            raise ValueError("work action dependency cycle")
        if action_id in visited:
            return
        visiting.add(action_id)
        for dependency in by_id[action_id].depends_on:
            visit(dependency)
        visiting.remove(action_id)
        visited.add(action_id)

    for action in actions:
        visit(action.action_id)
