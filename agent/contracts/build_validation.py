"""Build Validation stage contract — independent E2E verification."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from agent.contracts.common import ArtifactRef, ContractModel, StepResult


class CriterionResult(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    BLOCKED = "blocked"
    NOT_RUN = "not_run"


class ObservedCriterionResult(ContractModel):
    criterion_id: str = Field(min_length=1)
    observed_result: str = Field(min_length=1)
    outcome: CriterionResult = CriterionResult.NOT_RUN
    evidence_refs: tuple[str, ...] = ()
    independent_observation: str = Field(min_length=1)


class E2EResult(ContractModel):
    e2e_id: str = Field(min_length=1)
    entrypoint: str = Field(min_length=1)
    exit_code: int
    stdout_digest: str = ""
    stderr_digest: str = ""
    duration_ms: int = 0
    outcome: CriterionResult = CriterionResult.NOT_RUN


class BuildValidationInput(ContractModel):
    build_record_ref: ArtifactRef
    build_receipt_ref: str = Field(min_length=1)


class BuildValidationRecord(ContractModel):
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    stage_revision: int = Field(ge=1)
    build_ref: ArtifactRef
    criterion_results: tuple[ObservedCriterionResult, ...] = ()
    e2e_results: tuple[E2EResult, ...] = ()
    step_results: tuple[StepResult, ...] = ()
