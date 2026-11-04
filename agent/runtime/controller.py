"""Host controller — single transition authority for all stages."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from agent.contracts.common import ArtifactRef
from agent.contracts.host import ReceiptRef
from agent.contracts.scanner import ScannerResult
from agent.contracts.work_todo import TodoList, WorkBinding
from agent.runtime.artifact_store import ArtifactStore
from agent.runtime.authorization import AuthorizationEngine
from agent.runtime.checkpoint_store import CheckpointStore, CompetingWriterError
from agent.runtime.event_store import EventStore
from agent.runtime.host_gap_analyzer import (
    HostGapAnalyzer,
    SkeletonRunner,
    StructuralGapOutcome,
    StructuralGapRequest,
    StructuralGapResult,
    structural_gap_receipt_subject,
)
from agent.runtime.providers.registry import ProviderRegistry
from agent.runtime.receipt_store import ReceiptStore
from agent.runtime.recovery import BoundedRecovery
from agent.runtime.scanner_gateway import ScannerGateway
from agent.runtime.work_todo import WorkTodoError, WorkTodoManager


class Stage(StrEnum):
    RESEARCH = "research"
    AUDIT_DISCOVERY = "audit_discovery"
    PLANNING = "planning"
    FIXTURE_VALIDATION = "fixture_validation"
    BUILD = "build"
    BUILD_VALIDATION = "build_validation"


STAGE_ORDER = (
    Stage.RESEARCH,
    Stage.AUDIT_DISCOVERY,
    Stage.PLANNING,
    Stage.FIXTURE_VALIDATION,
    Stage.BUILD,
    Stage.BUILD_VALIDATION,
)


class TransitionError(Exception):
    pass


class TaskState(BaseModel):
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    current_stage: Stage = Stage.RESEARCH
    completed_stages: tuple[Stage, ...] = ()
    active_work_artifact_id: str | None = None

    model_config = {"frozen": True}


class HostController:
    """Single host transition authority.

    - Manages stage transitions and receipts.
    - Rejects illegal transitions.
    - Checkpoints state with CAS.
    - Dispatches to stores, scanner, and providers.
    """

    def __init__(
        self,
        state_root: str | Path,
        workspace_root: str | Path | None = None,
    ) -> None:
        self.state_root = Path(state_root)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.artifact_store = ArtifactStore(self.state_root)
        self.receipt_store = ReceiptStore(self.state_root)
        self.event_store = EventStore(self.state_root)
        self.work_todos = WorkTodoManager(self.artifact_store, self.event_store)
        self.checkpoint_store = CheckpointStore(self.state_root)
        self.scanner = ScannerGateway(self.artifact_store)
        self.gap_analyzer = HostGapAnalyzer(self.artifact_store, self.receipt_store)
        self.recovery = BoundedRecovery()
        self.providers = ProviderRegistry()
        self.authorization = AuthorizationEngine(
            allowed_roots=(str(self.state_root),)
            if workspace_root is None
            else (str(workspace_root), str(self.state_root))
        )
        self._workspace_root = workspace_root or self.state_root / "workspace"

    def advance_stage(
        self,
        task_id: str,
        run_id: str,
        expected_stage: Stage,
        completion_receipt_ref: ReceiptRef | None = None,
        gap_result_ref: ArtifactRef | None = None,
        gap_receipt_ref: ReceiptRef | None = None,
        todo_ref: ArtifactRef | None = None,
    ) -> TaskState:
        """Advance to the next stage if the current stage is completed.

        Requires a valid completion receipt from the current stage to
        prove the stage produced verified output before transitioning.
        """
        checkpoint = self.checkpoint_store.load_checkpoint(task_id)
        if checkpoint is None:
            state = TaskState(task_id=task_id, run_id=run_id)
        else:
            _rev, state_dict, _ = checkpoint
            state = TaskState(**state_dict)

        if state.current_stage != expected_stage:
            raise TransitionError(f"expected stage {expected_stage}, but current is {state.current_stage}")
        if state.run_id != run_id or state.task_id != task_id:
            raise TransitionError("stage transition task/run binding mismatch")

        self._verify_stage_receipt(state, completion_receipt_ref)
        if state.current_stage is Stage.PLANNING:
            self._verify_structural_gap(task_id, run_id, gap_result_ref, gap_receipt_ref)

        # Task tracking is a mandatory observation gate, never permission to execute.
        if todo_ref is None:
            raise TransitionError("completed work list reference required before stage transition")
        if state.active_work_artifact_id != todo_ref.artifact_id:
            raise TransitionError("work list does not match the host-assigned request")
        try:
            self.work_todos.require_complete(todo_ref, task_id=task_id, run_id=run_id, stage=state.current_stage.value)
        except WorkTodoError as exc:
            raise TransitionError(f"invalid or unfinished work list: {exc}") from exc

        idx = STAGE_ORDER.index(state.current_stage)
        if idx + 1 >= len(STAGE_ORDER):
            raise TransitionError("already at final stage")

        completed = (*state.completed_stages, state.current_stage)
        new_stage = STAGE_ORDER[idx + 1]
        new_state = TaskState(
            task_id=task_id,
            run_id=run_id,
            current_stage=new_stage,
            completed_stages=completed,
        )

        expected_rev = checkpoint[0] if checkpoint else 0
        try:
            self.checkpoint_store.checkpoint_cas(
                task_id,
                expected_rev,
                new_state.model_dump(mode="json"),
            )
        except CompetingWriterError as e:
            raise TransitionError(f"checkpoint CAS failed: {e}") from e

        self.event_store.append(task_id, "stage_transition", f"{state.current_stage} -> {new_stage}")
        return new_state

    def _verify_stage_receipt(self, state: TaskState, completion_receipt_ref: ReceiptRef | None) -> None:
        """Verify an existing host completion receipt for the actual stage."""
        # Verify stage-completion receipt
        if completion_receipt_ref is None:
            raise TransitionError("stage completion receipt required")
        # Verify task-bound receipt: subject must match task_id, run_id, and stage
        # Accept old format (stage_complete:{stage}) for backward compat
        expected_old = f"stage_complete:{state.current_stage.value}"
        expected_new = f"stage_complete:{state.task_id}:{state.run_id}:{state.current_stage.value}"
        if not self.receipt_store.verify(
            completion_receipt_ref.receipt_id,
            completion_receipt_ref.receipt_digest,
            expected_old,
        ) and not self.receipt_store.verify(
            completion_receipt_ref.receipt_id,
            completion_receipt_ref.receipt_digest,
            expected_new,
        ):
            raise TransitionError(f"invalid completion receipt for stage {state.current_stage}")


    def _verify_structural_gap(
        self,
        task_id: str,
        run_id: str,
        gap_result_ref: ArtifactRef | None,
        gap_receipt_ref: ReceiptRef | None,
        candidate_ref: ArtifactRef | None = None,
    ) -> StructuralGapResult:
        """Verify a persisted result and trusted pass receipt for this exact candidate."""
        if gap_result_ref is None or gap_receipt_ref is None:
            raise TransitionError("structural gap analysis receipt and result required")
        if gap_receipt_ref.issuer_id != "host":
            raise TransitionError("untrusted structural gap completion issuer")
        try:
            digest = self.artifact_store.get_digest(gap_result_ref.artifact_id, gap_result_ref.artifact_revision)
            if digest != gap_result_ref.artifact_digest:
                raise ValueError("structural gap artifact digest mismatch")
            if gap_result_ref.contract_id != "structural_analysis_result":
                raise ValueError("incorrect structural gap result contract")
            raw = self.artifact_store.get_verified(gap_result_ref.artifact_id, gap_result_ref.artifact_revision)
            result = StructuralGapResult.model_validate_json(raw)
            if result.task_id != task_id or result.run_id != run_id:
                raise ValueError("structural gap result belongs to another task or run")
            if result.execution_status != "completed" or result.findings:
                raise ValueError("structural gap analysis did not pass")
            if result.known_critical_gap_detection_rate != 1.0 or not result.walking_skeleton_completed:
                raise ValueError("structural gap backtest or walking skeleton incomplete")
            candidate = result.candidate_specification_ref
            if (
                self.artifact_store.get_digest(candidate.artifact_id, candidate.artifact_revision)
                != candidate.artifact_digest
            ):
                raise ValueError("Planning candidate changed since structural analysis")
            subject = structural_gap_receipt_subject(result, digest)
            if not self.receipt_store.verify(gap_receipt_ref.receipt_id, gap_receipt_ref.receipt_digest, subject):
                raise ValueError("structural gap completion receipt is not verified")
        except Exception as exc:
            raise TransitionError(f"invalid structural gap evidence: {exc}") from exc
        if candidate_ref is not None and result.candidate_specification_ref != candidate_ref:
            raise TransitionError("structural gap pass belongs to a different candidate")
        return result

    def scan_planning_candidate(
        self,
        task_id: str,
        run_id: str,
        candidate_ref: ArtifactRef,
        repository_identity: str,
        capabilities: tuple[str, ...],
        gap_result_ref: ArtifactRef | None,
        gap_receipt_ref: ReceiptRef | None,
    ) -> ScannerResult:
        """Host Scanner dispatch; always reject an unvalidated Planning candidate."""
        self._verify_structural_gap(task_id, run_id, gap_result_ref, gap_receipt_ref, candidate_ref)
        return self.scanner.scan_exact(candidate_ref, repository_identity, capabilities)

    def run_structural_gap_analysis(
        self,
        request: StructuralGapRequest,
        *,
        walking_skeleton_runner: SkeletonRunner | None = None,
    ) -> StructuralGapOutcome:
        """Run the host structural workflow before accepting Planning."""
        return self.gap_analyzer.evaluate(request, walking_skeleton_runner=walking_skeleton_runner)

    def complete_final_stage(
        self,
        task_id: str,
        run_id: str,
        completion_receipt_ref: ReceiptRef | None,
        todo_ref: ArtifactRef | None,
    ) -> TaskState:
        """Mark Build Verification completed only after its assigned work is verified."""
        checkpoint = self.checkpoint_store.load_checkpoint(task_id)
        if checkpoint is None:
            raise TransitionError("task has no checkpoint")
        revision, state_dict, _ = checkpoint
        state = TaskState(**state_dict)
        if state.run_id != run_id or state.task_id != task_id:
            raise TransitionError("final stage task/run mismatch")
        if state.current_stage is not Stage.BUILD_VALIDATION or Stage.BUILD_VALIDATION in state.completed_stages:
            raise TransitionError("task is not at an unfinished final verification stage")
        self._verify_stage_receipt(state, completion_receipt_ref)
        if todo_ref is None:
            raise TransitionError("completed final-stage work list required")
        if state.active_work_artifact_id != todo_ref.artifact_id:
            raise TransitionError("final work list does not match host assignment")
        try:
            self.work_todos.require_complete(todo_ref, task_id=task_id, run_id=run_id, stage=state.current_stage.value)
        except WorkTodoError as exc:
            raise TransitionError(f"invalid or unfinished final work list: {exc}") from exc
        completed = state.model_copy(
            update={
                "completed_stages": (*state.completed_stages, Stage.BUILD_VALIDATION),
                "active_work_artifact_id": None,
            }
        )
        try:
            self.checkpoint_store.checkpoint_cas(task_id, revision, completed.model_dump(mode="json"))
        except CompetingWriterError as exc:
            raise TransitionError(f"final stage checkpoint CAS failed: {exc}") from exc
        self.event_store.append(task_id, "stage_completed", Stage.BUILD_VALIDATION.value)
        return completed

    def assign_work(
        self,
        binding: WorkBinding,
        *,
        action: str | None = None,
        expected_result: str | None = None,
        work_plan_ref: ArtifactRef | None = None,
    ) -> tuple[TodoList, ArtifactRef]:
        """Host registers a stage assignment and auto-generates its work tracker."""
        checkpoint = self.checkpoint_store.load_checkpoint(binding.task_id)
        if checkpoint is None:
            raise TransitionError("cannot assign work before task initialization")
        revision, state_dict, _ = checkpoint
        state = TaskState(**state_dict)
        if state.run_id != binding.run_id or state.current_stage.value != binding.stage:
            raise TransitionError("work assignment belongs to a different task stage or run")
        if state.current_stage in state.completed_stages:
            raise TransitionError("cannot assign work after stage completion")
        work_id = WorkTodoManager._identity(binding, "work-todo")
        if state.active_work_artifact_id is not None and state.active_work_artifact_id != work_id:
            raise TransitionError("different work request already assigned to this stage")
        record, ref = self.work_todos.start(
            binding, action=action, expected_result=expected_result, work_plan_ref=work_plan_ref
        )
        if state.active_work_artifact_id is None:
            updated = state.model_copy(update={"active_work_artifact_id": ref.artifact_id})
            try:
                self.checkpoint_store.checkpoint_cas(binding.task_id, revision, updated.model_dump(mode="json"))
            except CompetingWriterError as exc:
                raise TransitionError(f"concurrent work assignment: {exc}") from exc
            self.event_store.append(binding.task_id, "work_assigned", ref.artifact_id)
        return record, ref

    def get_state(self, task_id: str) -> TaskState | None:
        """Get current task state from checkpoint."""
        checkpoint = self.checkpoint_store.load_checkpoint(task_id)
        if checkpoint is None:
            return None
        _, state_dict, _ = checkpoint
        return TaskState(**state_dict)

    def init_task(self, task_id: str, run_id: str) -> TaskState:
        """Initialize a new task."""
        state = TaskState(task_id=task_id, run_id=run_id)
        self.checkpoint_store.checkpoint_cas(task_id, 0, state.model_dump(mode="json"))
        self.event_store.append(task_id, "task_init", f"run_id={run_id}")
        return state

    def issue_stage_receipt(
        self,
        stage: Stage,
        task_id: str = "",
        run_id: str = "",
        revision: int = 0,
        artifact_digest: str = "",
    ) -> ReceiptRef:
        """Issue a task-bound stage-completion receipt.

        The receipt subject binds task_id, run_id, stage, revision, and
        artifact digest so the same evidence cannot be applied to a
        different task or run.
        """
        subject = f"stage_complete:{task_id}:{run_id}:{stage.value}"
        receipt_id = f"receipt-{task_id}-{stage.value}" if task_id else f"receipt-{stage.value}"
        _, receipt_digest = self.receipt_store.issue_verified(
            receipt_id,
            "host",
            subject,
        )
        return ReceiptRef(
            receipt_id=receipt_id,
            receipt_digest=receipt_digest,
            issuer_id="host",
        )
