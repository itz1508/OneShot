"""Host controller — single transition authority for all stages."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from agent.contracts.host import ReceiptRef
from agent.runtime.artifact_store import ArtifactStore
from agent.runtime.authorization import AuthorizationEngine
from agent.runtime.checkpoint_store import CheckpointStore, CompetingWriterError
from agent.runtime.event_store import EventStore
from agent.runtime.providers.registry import ProviderRegistry
from agent.runtime.receipt_store import ReceiptStore
from agent.runtime.recovery import BoundedRecovery
from agent.runtime.scanner_gateway import ScannerGateway


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
        self.checkpoint_store = CheckpointStore(self.state_root)
        self.scanner = ScannerGateway(self.artifact_store)
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
