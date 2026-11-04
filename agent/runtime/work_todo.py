"""Host-owned generation, CAS progress tracking, and final work completion gate.

Reuses ArtifactStore + EventStore. To-do records observe actual work but never
approve effects, alter an admitted Build plan, or own stage transitions.
"""

from __future__ import annotations

from agent.contracts.common import ArtifactRef
from agent.contracts.work_todo import (
    TodoAction,
    TodoList,
    WorkBinding,
    WorkPlan,
    WorkStatus,
)
from agent.runtime.artifact_store import ArtifactStore, StaleRevisionError
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE
from agent.runtime.event_store import EventStore


class WorkTodoError(ValueError):
    """A work list or progress report violates the host's tracking contract."""


class WorkTodoManager:
    """Projection of assigned work, never a second task or authorization store."""

    def __init__(self, artifacts: ArtifactStore, events: EventStore) -> None:
        self._artifacts = artifacts
        self._events = events

    @staticmethod
    def _identity(binding: WorkBinding, prefix: str) -> str:
        return (
            f"{prefix}:{binding.task_id}:{binding.run_id}:{binding.stage}:"
            f"{binding.request_id}:{binding.request_revision}"
        )

    @staticmethod
    def _ref(artifact_id: str, revision: int, digest: str, contract: str) -> ArtifactRef:
        return ArtifactRef(
            artifact_id=artifact_id,
            artifact_revision=revision,
            artifact_digest=digest,
            contract_id=contract,
            contract_version="1.0",
            serializer_profile=SERIALIZER_PROFILE,
        )

    def _verified(self, ref: ArtifactRef, contract: str) -> bytes:
        if ref.contract_id != contract or ref.contract_version != "1.0":
            raise WorkTodoError(f"expected {contract} artifact reference")
        digest = self._artifacts.get_digest(ref.artifact_id, ref.artifact_revision)
        if digest != ref.artifact_digest:
            raise WorkTodoError(f"missing or changed work evidence: {ref.artifact_id}")
        return self._artifacts.get_verified(ref.artifact_id, ref.artifact_revision)

    def _check_input(self, ref: ArtifactRef) -> None:
        if self._artifacts.get_digest(ref.artifact_id, ref.artifact_revision) != ref.artifact_digest:
            raise WorkTodoError("unverified input request reference")
        self._artifacts.get_verified(ref.artifact_id, ref.artifact_revision)

    def persist_work_plan(self, plan: WorkPlan) -> ArtifactRef:
        """Accept a validated role-local plan; do not authorize its actions."""
        self._check_input(plan.input_request_ref)
        aid = self._identity(plan, "work-plan")
        digest = self._artifacts.put_immutable(plan, aid, 1, "work_plan", "1.0")
        return self._ref(aid, 1, digest, "work_plan")

    def start(
        self,
        binding: WorkBinding,
        *,
        action: str | None = None,
        expected_result: str | None = None,
        work_plan_ref: ArtifactRef | None = None,
    ) -> tuple[TodoList, ArtifactRef]:
        """Create one automatic action or derive a multi-action list from a stored plan.

        Duplicate starts with the same immutable source are idempotent, returning
        the latest revision; attempts to change the source fail closed.
        """
        self._check_input(binding.input_request_ref)
        if (work_plan_ref is None) == (action is None):
            raise WorkTodoError("provide either one action or a registered complex work plan")
        if work_plan_ref is None:
            if not action or not expected_result:
                raise WorkTodoError("single work needs its objective and expected result")
            initial = TodoList(
                **binding.model_dump(),
                generation="automatic_single",
                actions=(TodoAction(action_id="work-1", action=action, expected_result=expected_result),),
            )
        else:
            if expected_result is not None:
                raise WorkTodoError("complex work derives expected results only from the plan")
            plan = WorkPlan.model_validate_json(self._verified(work_plan_ref, "work_plan"))
            for field in WorkBinding.model_fields:
                if getattr(plan, field) != getattr(binding, field):
                    raise WorkTodoError("work plan is bound to a different request")
            initial = TodoList(
                **binding.model_dump(),
                generation="plan_derived",
                work_plan_ref=work_plan_ref,
                actions=tuple(TodoAction(**entry.model_dump()) for entry in plan.actions),
            )
        aid = self._identity(binding, "work-todo")
        was_new = self._artifacts.latest_revision(aid) == 0
        digest = self._artifacts.put_immutable(initial, aid, 1, "work_todo", "1.0")
        if was_new:
            self._events.append(binding.task_id, "work_todo_created", aid)
        revision = self._artifacts.latest_revision(aid)
        ref = self._ref(aid, revision, self._artifacts.get_digest(aid, revision) or digest, "work_todo")
        return self.read(ref), ref

    def read(self, ref: ArtifactRef) -> TodoList:
        return TodoList.model_validate_json(self._verified(ref, "work_todo"))

    def set_status(
        self,
        ref: ArtifactRef,
        action_id: str,
        status: WorkStatus,
        *,
        actual_result: str = "",
        evidence_refs: tuple[ArtifactRef, ...] = (),
    ) -> tuple[TodoList, ArtifactRef]:
        """CAS transition: pending -> running -> completed/failed/blocked."""
        status = WorkStatus(status)
        record = self.read(ref)
        if self._artifacts.latest_revision(ref.artifact_id) != ref.artifact_revision:
            raise StaleRevisionError("stale work-list revision")
        found = next((a for a in record.actions if a.action_id == action_id), None)
        if found is None:
            raise WorkTodoError("work action does not exist")
        if found.status is WorkStatus.PENDING and status is not WorkStatus.RUNNING:
            raise WorkTodoError("action must enter running before reporting completion")
        if found.status is WorkStatus.RUNNING and status not in {
            WorkStatus.COMPLETED,
            WorkStatus.FAILED,
            WorkStatus.BLOCKED,
        }:
            raise WorkTodoError("running action must finish with a terminal status")
        if found.status not in {WorkStatus.PENDING, WorkStatus.RUNNING}:
            raise WorkTodoError("terminal work action is immutable; create a new work request to retry")
        if status is WorkStatus.RUNNING and any(
            predecessor.status is not WorkStatus.COMPLETED
            for predecessor in record.actions
            if predecessor.action_id in found.depends_on
        ):
            raise WorkTodoError("action dependencies are not complete")
        if status is WorkStatus.COMPLETED and (not evidence_refs or not actual_result):
            raise WorkTodoError("completed action requires actual result and evidence")
        for evidence in evidence_refs:
            self._check_input(evidence)
        replacement = TodoAction.model_validate(
            {
                **found.model_dump(mode="json"),
                "status": status,
                "actual_result": actual_result,
                "evidence_refs": [r.model_dump(mode="json") for r in evidence_refs],
            }
        )
        updated = TodoList.model_validate(
            {
                **record.model_dump(mode="json"),
                "actions": [
                    replacement.model_dump(mode="json") if a.action_id == action_id else a.model_dump(mode="json")
                    for a in record.actions
                ],
            }
        )
        revision, digest = self._artifacts.put_cas(updated, ref.artifact_id, ref.artifact_revision, "work_todo", "1.0")
        new_ref = self._ref(ref.artifact_id, revision, digest, "work_todo")
        self._events.append(record.task_id, "work_todo_updated", f"{action_id}:{status.value}:rev{revision}")
        return updated, new_ref

    def require_complete(self, ref: ArtifactRef, *, task_id: str, run_id: str, stage: str) -> TodoList:
        """Fail closed if a stage attempts completion with missing, stale or open work."""
        record = self.read(ref)
        if (record.task_id, record.run_id, record.stage) != (task_id, run_id, stage):
            raise WorkTodoError("work list belongs to a different task, run, or stage")
        if self._artifacts.latest_revision(ref.artifact_id) != ref.artifact_revision:
            raise WorkTodoError("work list revision is stale")
        if any(item.status is not WorkStatus.COMPLETED for item in record.actions):
            raise WorkTodoError("stage has unfinished, blocked, or failed work")
        for item in record.actions:
            for evidence in item.evidence_refs:
                self._check_input(evidence)
        return record
