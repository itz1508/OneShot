"""Strict standalone request, candidate, and execution record contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHA256 = str


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Outcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class Diagnostic(StrEnum):
    VALID = "valid"
    NOT_VALID = "not_valid"
    UNCERTAINTY = "uncertainty"


class Cleanup(StrEnum):
    CONFIRMED = "confirmed"
    FAILED = "failed"
    NOT_CREATED = "not_created"
    UNCERTAIN = "uncertain"


def _sha(v: str) -> str:
    if len(v) != 64 or any(c not in "0123456789abcdef" for c in v):
        raise ValueError("must be a lowercase sha256")
    return v


class CommandSpec(Strict):
    command_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    argv: tuple[str, ...] = Field(min_length=2, max_length=20)
    working_directory: str = "."
    timeout_seconds: int = Field(default=120, ge=1, le=120)
    expected_exit_codes: tuple[int, ...] = (0,)
    purpose: Literal["baseline", "focused", "broader"]
    expected_error: str | None = None

    @model_validator(mode="after")
    def check(self) -> CommandSpec:
        if not all(isinstance(s, str) and s and len(s) < 2048 and "\x00" not in s for s in self.argv):
            raise ValueError("invalid argv")
        if not self.expected_exit_codes or len(set(self.expected_exit_codes)) != len(self.expected_exit_codes):
            raise ValueError("exit codes missing/duplicated")
        if self.expected_error is not None and (not self.expected_error or len(self.expected_error) > 512):
            raise ValueError("invalid expected error oracle")
        return self


class SandboxLimits(Strict):
    lifetime_seconds: int = Field(default=600, ge=1, le=600)
    idle_seconds: int = Field(default=120, ge=1, le=120)
    cpu_request: float = Field(default=1, gt=0, le=2)
    cpu_limit: float = Field(default=2, gt=0, le=2)
    ram_request_mib: int = Field(default=1024, ge=128, le=2048)
    ram_limit_mib: int = Field(default=2048, ge=128, le=2048)
    max_commands: int = Field(default=12, ge=1, le=12)
    max_changed_paths: int = Field(default=50, ge=1, le=50)
    max_patch_bytes: int = Field(default=5 * 1024 * 1024, ge=1, le=5 * 1024 * 1024)
    max_archive_bytes: int = Field(default=50 * 1024 * 1024, ge=1, le=50 * 1024 * 1024)
    max_extracted_bytes: int = Field(default=250 * 1024 * 1024, ge=1, le=250 * 1024 * 1024)
    max_output_bytes: int = Field(default=1024 * 1024, ge=1, le=1024 * 1024)
    max_evidence_bytes: int = Field(default=20 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)

    @model_validator(mode="after")
    def check(self) -> SandboxLimits:
        if self.cpu_request > self.cpu_limit or self.ram_request_mib > self.ram_limit_mib:
            raise ValueError("resource request exceeds limit")
        return self


class CandidateManifest(Strict):
    contract_version: Literal["1.0"] = "1.0"
    operation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,120}$")
    attempt_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,120}$")
    work_item_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,120}$")
    task_revision: str = Field(pattern=r"^[A-Za-z0-9_-]{1,120}$")
    source_snapshot_sha256: SHA256
    declared_paths: tuple[str, ...] = Field(min_length=1)
    patch_sha256: SHA256
    patch_bytes: int = Field(ge=1, le=5 * 1024 * 1024)

    _valid_source = field_validator("source_snapshot_sha256", "patch_sha256")(_sha)


class SandboxExecutionRequest(Strict):
    contract_version: Literal["1.0"] = "1.0"
    operation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,120}$")
    attempt_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,120}$")
    work_item_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,120}$")
    task_revision: str = Field(pattern=r"^[A-Za-z0-9_-]{1,120}$")
    source_snapshot_ref: str = Field(min_length=1)
    source_snapshot_sha256: SHA256
    expected_source_tree_digest: SHA256
    image_id: str = Field(min_length=1, max_length=200)
    sandbox_profile_id: str = Field(min_length=1, max_length=200)
    sandbox_profile_digest: SHA256
    primary_authorized_path: str = Field(min_length=1)
    authorized_paths: tuple[str, ...] = Field(min_length=1, max_length=50)
    expected_preimages: dict[str, SHA256 | None]
    candidate_bundle_ref: str = Field(min_length=1)
    candidate_bundle_sha256: SHA256
    baseline_expectation: Literal["expected_success", "expected_failure", "not_required"]
    baseline_checks: tuple[CommandSpec, ...] = ()
    focused_checks: tuple[CommandSpec, ...] = Field(min_length=1)
    broader_checks: tuple[CommandSpec, ...] = ()
    command_plan_sha256: SHA256
    limits: SandboxLimits = Field(default_factory=SandboxLimits)
    network_blocked: Literal[True] = True

    _valid_hashes = field_validator(
        "source_snapshot_sha256",
        "expected_source_tree_digest",
        "sandbox_profile_digest",
        "candidate_bundle_sha256",
        "command_plan_sha256",
    )(_sha)

    @model_validator(mode="after")
    def validate_shape(self) -> SandboxExecutionRequest:
        from .policy import normalize_path

        ps = [normalize_path(p) for p in self.authorized_paths]
        if len(ps) != len(set(p.casefold() for p in ps)):
            raise ValueError("duplicate path aliases")
        if set(ps) != set(self.expected_preimages):
            raise ValueError("incomplete expected_preimages")
        if normalize_path(self.primary_authorized_path) not in ps:
            raise ValueError("primary path is not authorized")
        if any(v is not None and _sha(v) != v for v in self.expected_preimages.values()):
            raise ValueError("invalid preimage")
        checks = self.baseline_checks + self.focused_checks + self.broader_checks
        if len(checks) > self.limits.max_commands or len(set(c.command_id for c in checks)) != len(checks):
            raise ValueError("command count/identity conflict")
        if any(
            c.purpose != label
            for label, arr in (
                ("baseline", self.baseline_checks),
                ("focused", self.focused_checks),
                ("broader", self.broader_checks),
            )
            for c in arr
        ):
            raise ValueError("command purpose mismatch")
        if self.baseline_expectation == "not_required" and self.baseline_checks:
            raise ValueError("baseline must be absent")
        if self.baseline_expectation != "not_required" and not self.baseline_checks:
            raise ValueError("baseline oracle missing")
        if self.baseline_expectation == "expected_failure" and not all(c.expected_error for c in self.baseline_checks):
            raise ValueError("expected failure needs an explicit oracle")
        return self


class SandboxCommandResult(Strict):
    command_id: str
    argv_digest: SHA256
    working_directory: str
    started_at: str
    ended_at: str
    exit_code: int | None
    timed_out: bool = False
    stdout_sha256: SHA256
    stderr_sha256: SHA256
    stdout_size: int = Field(ge=0)
    stderr_size: int = Field(ge=0)
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""


class ChangedPath(Strict):
    path: str
    operation: Literal["create", "modify", "delete", "mode"]
    before_sha256: SHA256 | None = None
    after_sha256: SHA256 | None = None
    before_mode: int | None = None
    after_mode: int | None = None


class SandboxExecutionResult(Strict):
    contract_version: Literal["1.0"] = "1.0"
    operation_id: str
    attempt_id: str
    work_item_id: str
    sandbox_id: str
    image_id: str
    sandbox_profile_id: str
    sandbox_profile_digest: SHA256
    input_archive_sha256: SHA256
    input_tree_digest: SHA256
    candidate_bundle_sha256: SHA256
    command_plan_sha256: SHA256
    baseline_results: tuple[SandboxCommandResult, ...] = ()
    focused_results: tuple[SandboxCommandResult, ...] = ()
    broader_results: tuple[SandboxCommandResult, ...] = ()
    changed_paths: tuple[ChangedPath, ...] = ()
    output_tree_digest: SHA256 | None = None
    execution_status: Outcome
    diagnostic_status: Diagnostic
    effect_reconciliation: str
    cleanup_state: Cleanup = Cleanup.UNCERTAIN
    evidence_bundle_ref: str | None = None
    evidence_bundle_sha256: SHA256 | None = None
    after_archive_ref: str | None = None
    after_archive_sha256: SHA256 | None = None
    detail: str = ""
