"""Build stage contract — admitted operations and effects."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from agent.contracts.common import ArtifactRef, ContractModel, Sha256, StepResult
from agent.contracts.host import ReceiptRef


class BuildActionStatus(StrEnum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    EFFECT_UNCERTAIN = "effect_uncertain"


class BuildActionExecution(ContractModel):
    action_id: str = Field(min_length=1)
    status: BuildActionStatus = BuildActionStatus.PENDING
    operation_receipt_ref: str | None = None
    pre_image_digest: Sha256 | None = None
    post_image_digest: Sha256 | None = None
    error: str | None = None


class EffectObservation(ContractModel):
    observation_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    observed_path: str = Field(min_length=1)
    observed_digest: Sha256 | None = None
    observation_type: str = Field(min_length=1)
    description: str = ""


class BuildInput(ContractModel):
    lock_receipt_ref: ReceiptRef
    admission_receipt_ref: ReceiptRef


class BuildRecord(ContractModel):
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    stage_revision: int = Field(ge=1)
    lock_ref: ArtifactRef
    admission_ref: ArtifactRef
    action_executions: tuple[BuildActionExecution, ...] = ()
    effect_observations: tuple[EffectObservation, ...] = ()
    step_results: tuple[StepResult, ...] = ()
