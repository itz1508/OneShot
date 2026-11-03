"""OneShot build contracts extracted from the former models.py monolith.

Keep stage fields and validators compatible; YAML record templates remain intact.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .shared import Checkpoint, RecordStatus, OutcomeStatus, _is_filled

class BuildPlanInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    record_ref: str | None = None
    record_id: str | None = None
    record_revision: int | None = None
    artifact_manifest_ref: str | None = None
    accepted_milestone_ids: list[str] = Field(default_factory=list)
    accepted_criterion_ids: list[str] = Field(default_factory=list)


class CommandReceipt(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    command: str
    cwd: str
    exit_code: int
    stdout_ref: str | None = None
    stderr_ref: str | None = None
    receipt_ref: str | None = None
    at: str | None = None


class MilestoneResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    status: Literal["passed", "failed", "blocked", "not_run"] = "not_run"
    changed_files: list[str] = Field(default_factory=list)
    command_receipts: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)


class BuildExecution(BaseModel):
    model_config = ConfigDict(extra="allow")

    workspace_snapshot_ref: str | None = None
    environment_ref: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    milestone_results: list[MilestoneResult] = Field(default_factory=list)
    changes: list[Any] = Field(default_factory=list)
    command_receipts: list[CommandReceipt] = Field(default_factory=list)
    artifact_manifest_ref: str | None = None
    cleanup: list[Any] = Field(default_factory=list)


class ImplementationValidation(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Literal["not_run", "failed", "passed", "blocked"] = "not_run"
    checks: list[Any] = Field(default_factory=list)
    regressions: list[Any] = Field(default_factory=list)


class E2ECase(BaseModel):
    model_config = ConfigDict(extra="allow")

    fixture_ref: str | None = None
    expected_ref: str | None = None
    observed_ref: str | None = None
    receipt_ref: str | None = None
    status: Literal["passed", "failed", "blocked", "not_run"] = "not_run"


class ChaosCase(BaseModel):
    model_config = ConfigDict(extra="allow")

    chaos_ref: str | None = None
    injected_fault: str | None = None
    expected_recovery: str | None = None
    observed_ref: str | None = None
    receipt_ref: str | None = None
    status: Literal["passed", "failed", "blocked", "not_run"] = "not_run"


class IndependentResultCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    criterion_id: str | None = None
    expected_ref: str | None = None
    observed_ref: str | None = None
    receipt_ref: str | None = None
    status: Literal["passed", "failed", "blocked", "not_run"] = "not_run"


class PostBuildE2E(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: Literal["not_run", "failed", "passed", "blocked"] = "not_run"
    real_entrypoint_ref: str | None = None
    environment_ref: str | None = None
    cases: list[E2ECase] = Field(default_factory=list)
    chaos_cases: list[ChaosCase] = Field(default_factory=list)
    independent_result_checks: list[IndependentResultCheck] = Field(default_factory=list)
    coverage_gaps: list[Any] = Field(default_factory=list)


class IssuesAndCorrections(BaseModel):
    model_config = ConfigDict(extra="allow")

    findings: list[Any] = Field(default_factory=list)
    gap_fix_receipt_refs: list[str] = Field(default_factory=list)
    revalidation_receipt_refs: list[str] = Field(default_factory=list)
    blockers: list[Any] = Field(default_factory=list)


class Outcome(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: OutcomeStatus = OutcomeStatus.NOT_VERIFIED
    user_visible_result_ref: str | None = None
    criterion_results: list[Any] = Field(default_factory=list)
    remaining_limitations: list[Any] = Field(default_factory=list)
    summary: str | None = None


class ManifestBinding(BaseModel):
    """G07 — immutable binding of a Build attempt to the records,
    detectors, fixtures, and receipts it was authorised against.

    Required at COMPLETE Build status; omitted (or empty) at DRAFT /
    IN_PROGRESS. `validate_pipeline` cross-checks `plan_revision` and
    `research_revision` against the sibling records' current revisions,
    so a Build attempt pinned to a stale Plan or stale Research is
    rejected before it can be reported VERIFIED.
    """

    model_config = ConfigDict(extra="allow")

    task_id: str
    research_revision: int = Field(ge=1)
    plan_revision: int = Field(ge=1)
    scanner_identity: str
    detector_identities: dict[str, str] = Field(default_factory=dict)
    fixture_oracle_sha: str
    oracle_revision: int = Field(ge=1)
    build_receipt_sha: str

    @field_validator("task_id", "scanner_identity", "fixture_oracle_sha", "build_receipt_sha")
    @classmethod
    def not_placeholder(cls, v):
        if not _is_filled(v):
            raise ValueError("manifest field must not be empty or a placeholder")
        # G07 reopen (reviewer finding on 9d2ce25): reject the specific
        # placeholder literals the previous build_plan fallback emitted,
        # so a stored manifest cannot carry them even if a legacy caller
        # tries to resurrect them.
        if v in {"unknown", "no_oracle_module"}:
            raise ValueError(
                f"manifest placeholder literal {v!r} is not an acceptable "
                "identity. Compute the real sha-256 before binding."
            )
        return v

    @field_validator("detector_identities")
    @classmethod
    def detector_identities_no_empty(cls, v):
        # G07 reopen (reviewer finding): detector_identities would
        # previously accept an empty string per detector (satisfying the
        # non-empty-field check at the dict level while leaving the
        # entry itself unbound). Every value must be a non-empty, non-
        # placeholder sha so each detector is pinned.
        if not isinstance(v, dict):
            raise ValueError("detector_identities must be a dict")
        if not v:
            raise ValueError(
                "detector_identities must bind at least one detector"
            )
        for tool_ref, ident in v.items():
            if not _is_filled(ident):
                raise ValueError(
                    f"detector_identities[{tool_ref!r}] must be a non-empty sha"
                )
            if ident in {"unknown", "no_oracle_module"}:
                raise ValueError(
                    f"detector_identities[{tool_ref!r}] placeholder literal "
                    f"{ident!r} is not an acceptable identity"
                )
        return v


class BuildRecord(BaseModel):
    """Pydantic model for the Build contract record."""

    model_config = ConfigDict(extra="allow")

    kind: Literal["build"] = "build"
    task_id: str
    record_id: str
    revision: int = Field(ge=1)
    status: RecordStatus = RecordStatus.DRAFT
    updated_at: str | None = None

    plan_input: BuildPlanInput
    execution: BuildExecution
    implementation_validation: ImplementationValidation
    post_build_e2e: PostBuildE2E
    issues_and_corrections: IssuesAndCorrections
    outcome: Outcome
    manifest_binding: ManifestBinding | None = None

    progress_log: list[Any] = Field(default_factory=list)
    decision_log: list[Any] = Field(default_factory=list)
    checkpoint: Checkpoint = Field(default_factory=Checkpoint)
    handoff: dict[str, Any] = Field(default_factory=lambda: {"to": "complete", "ready": False})

    @field_validator("task_id", "record_id")
    @classmethod
    def not_placeholder(cls, v):
        if not _is_filled(v):
            raise ValueError("must not be empty or a placeholder")
        return v

    @model_validator(mode="after")
    def check_completion(self) -> BuildRecord:
        ready = self.handoff.get("ready")
        if self.status == RecordStatus.COMPLETE or ready is True:
            if not (ready is True and self.status == RecordStatus.COMPLETE):
                raise ValueError("complete status and handoff.ready must agree")
            if not self.progress_log:
                raise ValueError("no progress log")
            if not self.decision_log:
                raise ValueError("no decision log")
            if not self.updated_at:
                raise ValueError("missing UTC updated_at")
            # Build-specific completion checks (mirror check_contracts L291, L301, L307, L342)
            if not self.execution.command_receipts:
                raise ValueError("no executed command receipts")
            if self.implementation_validation.status != "passed":
                raise ValueError("implementation validation not passed")
            if self.post_build_e2e.status != "passed":
                raise ValueError("post-Build E2E not passed")
            if self.outcome.status != OutcomeStatus.VERIFIED:
                raise ValueError("outcome not verified")
            # G07 — a verified Build must carry a complete manifest.
            if self.manifest_binding is None:
                raise ValueError("missing manifest_binding on complete build")
        return self


