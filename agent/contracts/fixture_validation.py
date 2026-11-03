"""Fixture Validation stage contract."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from agent.contracts.common import ArtifactRef, ContractModel, StepResult


class FixtureOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNCERTAIN = "uncertain"


class FixtureResult(ContractModel):
    fixture_id: str = Field(min_length=1)
    oracle_ref: str = Field(min_length=1)
    observed_result: str = Field(min_length=1)
    expected_result: str = Field(min_length=1)
    outcome: FixtureOutcome = FixtureOutcome.UNCERTAIN
    evidence_refs: tuple[str, ...] = ()


class ChaosResult(ContractModel):
    chaos_id: str = Field(min_length=1)
    fault_type: str = Field(min_length=1)
    observed_behavior: str = Field(min_length=1)
    expected_behavior: str = Field(min_length=1)
    outcome: FixtureOutcome = FixtureOutcome.UNCERTAIN
    evidence_refs: tuple[str, ...] = ()


class FixtureValidationInput(ContractModel):
    frozen_spec_ref: ArtifactRef
    freeze_receipt_ref: str = Field(min_length=1)
    handoff_receipt_ref: str = Field(min_length=1)


class FixtureValidationRecord(ContractModel):
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    stage_revision: int = Field(ge=1)
    frozen_spec_ref: ArtifactRef
    fixture_results: tuple[FixtureResult, ...] = ()
    chaos_results: tuple[ChaosResult, ...] = ()
    step_results: tuple[StepResult, ...] = ()
