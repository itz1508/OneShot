"""Trusted host evidence types — never role-issuable.

Receipts, effects, locks, and admission schemas that only the host
runtime may create and verify.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field

from agent.contracts.common import ArtifactRef, ContractModel, OperationState, Sha256


class HostDispatchEnvelope(ContractModel):
    """Host-allocated, persisted agent assignment bound to an exact input."""

    task_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    stage: str = Field(min_length=1)
    role: str = Field(min_length=1)
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    request_revision: int = Field(ge=1)
    respond_to: str = Field(min_length=1)
    requester_role: str = Field(min_length=1)
    input_request_ref: ArtifactRef
    information_needed: str = Field(min_length=1)


class HostDispatchResult(ContractModel):
    """Host-received result; every identity must match the stored assignment."""

    task_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    stage: str = Field(min_length=1)
    role: str = Field(min_length=1)
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    request_revision: int = Field(ge=1)
    respond_to: str = Field(min_length=1)
    output_ref: ArtifactRef


class ReceiptRef(ContractModel):
    """Reference to a host-issued receipt."""

    receipt_id: str = Field(min_length=1)
    receipt_digest: Sha256
    issuer_id: str = Field(min_length=1)


class TechnicalCheckReceipt(ContractModel):
    """Receipt for a technical check (e.g. Scanner, compatibility probe)."""

    check_id: str = Field(min_length=1)
    method: str = Field(min_length=1)
    environment_ref: str = Field(min_length=1)
    tool_identity: str = Field(min_length=1)
    output_digest: Sha256
    output_artifact_ref: ArtifactRef
    receipt_ref: ReceiptRef


class FreezeReceipt(ContractModel):
    """Receipt for a host-frozen specification."""

    candidate_ref: ArtifactRef
    frozen_ref: ArtifactRef
    scanner_receipt_ref: ReceiptRef
    repository_identity_ref: str = Field(min_length=1)
    authorization_receipt_ref: ReceiptRef


class FixtureValidationHandoffReceipt(ContractModel):
    """Receipt authorizing fixture validation from frozen spec."""

    frozen_spec_ref: ArtifactRef
    fixture_spec_ref: ArtifactRef
    authorization_ref: ReceiptRef
    handoff_ref: ReceiptRef


class PackageLockReceipt(ContractModel):
    """Receipt locking all upstream artifacts before build admission."""

    lock_id: str = Field(min_length=1)
    research_ref: ArtifactRef
    audit_ref: ArtifactRef
    frozen_spec_ref: ArtifactRef
    fixture_result_ref: ArtifactRef | None = None
    policy_ref: ArtifactRef | None = None
    tool_registry_ref: ArtifactRef | None = None
    receipt_ref: ReceiptRef


class BuildAdmissionReceipt(ContractModel):
    """Receipt admitting specific build operations."""

    admission_id: str = Field(min_length=1)
    lock_receipt_ref: ReceiptRef
    authorized_action_ids: tuple[str, ...] = Field(min_length=1)
    authorized_tool_ids: tuple[str, ...] = ()
    tool_registry_ref: ArtifactRef | None = None
    recovery_readiness_ref: str | None = None
    receipt_ref: ReceiptRef


def admission_receipt_subject(
    lock_receipt_ref: ReceiptRef,
    authorized_action_ids: tuple[str, ...],
    authorized_tool_ids: tuple[str, ...] = (),
    tool_registry_ref: ArtifactRef | None = None,
) -> str:
    """One canonical host-bound receipt subject for issue AND verification."""
    return (
        f"{lock_receipt_ref.receipt_id}:{lock_receipt_ref.receipt_digest}:"
        f"{':'.join(authorized_action_ids)}:{':'.join(authorized_tool_ids)}:"
        f"{tool_registry_ref.artifact_digest if tool_registry_ref else 'no-tools'}"
    )


def stage_receipt_subject(
    task_id: str,
    run_id: str,
    stage: str,
    artifact_revision: int,
    artifact_digest: str,
) -> str:
    """One canonical host-bound stage-completion subject for issue AND verification.

    Binds task, run, stage, and the exact verified work artifact
    revision and digest. Issue and verify must use this helper so a
    receipt cannot be replayed across tasks, runs, stages, revisions,
    or mismatched artifacts.
    """
    return f"stage_complete:{task_id}:{run_id}:{stage}:{artifact_revision}:{artifact_digest}"


def stage_receipt_id(
    task_id: str,
    run_id: str,
    stage: str,
    artifact_revision: int,
    artifact_digest: str,
) -> str:
    """One canonical host-bound stage-completion receipt id."""
    return f"receipt-{task_id}-{run_id}-{stage}-{artifact_revision}-{artifact_digest}"


class AuthorizationReceipt(ContractModel):
    """Receipt for an authorized tool/action dispatch."""

    authorization_id: str = Field(min_length=1)
    principal: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    subject_ref: str = Field(min_length=1)
    receipt_ref: ReceiptRef


class OperationReceipt(ContractModel):
    """Receipt for a physical operation effect."""

    operation_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    effect_kind: str = Field(min_length=1)
    pre_image_digest: Sha256 | None = None
    post_image_digest: Sha256 | None = None
    receipt_ref: ReceiptRef


class CheckpointRef(ContractModel):
    """Reference to a checkpoint revision."""

    task_id: str = Field(min_length=1)
    checkpoint_revision: int = Field(ge=1)
    checkpoint_digest: Sha256


class AuthorizationDecision(StrEnum):
    """Host authorization outcome."""

    ALLOW = "allow"
    DENY = "deny"


class EffectScope(StrEnum):
    """Classification of operation effects."""

    NONE = "none"
    FILESYSTEM = "filesystem"
    EXTERNAL_SYSTEM = "external_system"


class RetrySemantics(StrEnum):
    """Retry classification for operations."""

    EFFECT_FREE = "effect_free"
    IDEMPOTENT = "idempotent"
    NON_IDEMPOTENT = "non_idempotent"
    DESTRUCTIVE = "destructive"


class OperationIntent(ContractModel):
    """Typed intent for a physical operation."""

    effect_scope: EffectScope = EffectScope.FILESYSTEM
    retry_semantics: RetrySemantics
    destructive: bool = False
    idempotency_key: str | None = None
    expected_pre_image: Sha256 | None = None
    expected_post_image: Sha256 | None = None


class OperationRecord(ContractModel):
    """Unified operation record with lifecycle state."""

    operation_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    idempotency_key: str | None = None
    effect_scope: EffectScope = EffectScope.FILESYSTEM
    retry_semantics: RetrySemantics = RetrySemantics.NON_IDEMPOTENT
    destructive: bool = False
    expected_preimage: Sha256 | None = None
    expected_postcondition: str = ""
    authorization_receipt_ref: str | None = None
    tool_identity: str = Field(min_length=1)
    input_digest: Sha256
    state: OperationState = OperationState.NOT_RUN


class Checkpoint(ContractModel):
    """Full checkpoint model with artifact, delegation, and operation refs."""

    checkpoint_id: str = Field(min_length=1)
    checkpoint_revision: int = Field(ge=1)
    expected_previous_revision: int = Field(ge=0, default=0)
    checkpoint_digest: Sha256
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    phase: str = Field(min_length=1)
    stage_revision: int = Field(ge=1)
    repository_identity_ref: str | None = None
    artifact_refs: tuple[ArtifactRef, ...] = ()
    delegation_refs: tuple[str, ...] = ()
    provider_session_refs: tuple[str, ...] = ()
    completed_operation_ids: tuple[str, ...] = ()
    uncertain_operation_refs: tuple[str, ...] = ()
    resume_point: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
