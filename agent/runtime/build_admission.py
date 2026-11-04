"""Independent, host-owned admission gate for a frozen Build and its tools."""

from __future__ import annotations

from agent.contracts.host import BuildAdmissionReceipt, PackageLockReceipt, ReceiptRef, admission_receipt_subject
from agent.contracts.planning import BuildSpecification, CandidateSpecification, PlanningRecord
from agent.contracts.validation.structural import tool_invocation_gaps
from agent.runtime.artifact_store import ArtifactStore
from agent.runtime.canonical_serialization import digest_raw
from agent.runtime.receipt_store import ReceiptStore
from agent.runtime.tool_registry import load_pinned_tool_registry


class BuildAdmissionError(Exception):
    pass


def _load_frozen_spec(store: ArtifactStore, lock: PackageLockReceipt) -> BuildSpecification:
    """Load the exact spec bytes referenced by the host-issued Package Lock."""
    ref = lock.frozen_spec_ref
    try:
        raw = store.get_verified(ref.artifact_id, ref.artifact_revision)
    except Exception as exc:
        raise BuildAdmissionError("frozen specification unavailable") from exc
    if digest_raw(raw) != ref.artifact_digest:
        raise BuildAdmissionError("frozen specification digest mismatch")
    for model in (BuildSpecification, CandidateSpecification, PlanningRecord):
        try:
            parsed = model.model_validate_json(raw)
        except ValueError:
            continue
        if isinstance(parsed, BuildSpecification):
            return parsed
        if isinstance(parsed, CandidateSpecification):
            return parsed.build_spec
        return parsed.candidate.build_spec
    raise BuildAdmissionError("frozen artifact does not contain a BuildSpecification")


class BuildAdmission:
    """Admit only actions from an exact Package Lock, never planner-invented argv."""

    def __init__(self, receipt_store: ReceiptStore, artifact_store: ArtifactStore | None = None) -> None:
        self._receipts = receipt_store
        self._artifacts = artifact_store

    def admit(
        self,
        admission_id: str,
        lock_receipt_ref: ReceiptRef,
        authorized_action_ids: tuple[str, ...],
        lock_subject: str,
        recovery_readiness_ref: str | None = None,
        issuer_id: str = "host",
        *,
        build_spec: BuildSpecification | None = None,
        package_lock: PackageLockReceipt | None = None,
    ) -> BuildAdmissionReceipt:
        """Derive tool authorization from admitted actions and a pinned registry.

        Legacy no-tool admissions remain valid; any executable invocation
        requires exact frozen artifacts, an inspected registry, and matching
        Package Lock subject before the host can issue an admission receipt.
        """
        if not authorized_action_ids or len(set(authorized_action_ids)) != len(authorized_action_ids):
            raise BuildAdmissionError("nonempty unique authorized actions required")
        if lock_receipt_ref.issuer_id != "host":
            raise BuildAdmissionError("untrusted lock issuer")
        if issuer_id != "host":
            raise BuildAdmissionError("only host may issue admission receipts")

        registry_ref = package_lock.tool_registry_ref if package_lock is not None else None
        if package_lock is not None:
            if package_lock.receipt_ref != lock_receipt_ref:
                raise BuildAdmissionError("package lock receipt mismatch")
            expected = (
                f"{package_lock.research_ref.artifact_digest}:"
                f"{package_lock.audit_ref.artifact_digest}:"
                f"{package_lock.frozen_spec_ref.artifact_digest}"
            )
            if registry_ref:
                expected += f":{registry_ref.artifact_digest}"
            if expected != lock_subject:
                raise BuildAdmissionError("package lock subject does not match upstream artifacts")
        if not self._receipts.verify(lock_receipt_ref.receipt_id, lock_receipt_ref.receipt_digest, lock_subject):
            raise BuildAdmissionError("invalid lock receipt")

        authorized_tools: tuple[str, ...] = ()
        if build_spec is not None or package_lock is not None:
            if self._artifacts is None or package_lock is None or build_spec is None:
                raise BuildAdmissionError("verified Package Lock required for frozen BuildSpecification")
            frozen = _load_frozen_spec(self._artifacts, package_lock)
            if frozen != build_spec:
                raise BuildAdmissionError("frozen BuildSpecification mismatch")
            action_map = {action.action_id: action for action in build_spec.actions}
            if any(action_id not in action_map for action_id in authorized_action_ids):
                raise BuildAdmissionError("admission contains unknown action ids")
            actions = tuple(action_map[action_id] for action_id in authorized_action_ids)
            invocations = tuple(inv for action in actions for inv in action.verification_tools)
            if invocations:
                if registry_ref is None:
                    raise BuildAdmissionError("frozen tool registry required")
                try:
                    snapshot = load_pinned_tool_registry(self._artifacts, registry_ref)
                    scoped = build_spec.model_copy(update={"actions": actions})
                    errors = tool_invocation_gaps(scoped, snapshot)
                except (ValueError, LookupError) as exc:
                    raise BuildAdmissionError(f"tool validation failed: {type(exc).__name__}") from exc
                if errors:
                    raise BuildAdmissionError("tool validation failed: " + "; ".join(errors))
                authorized_tools = tuple(sorted({inv.tool_id for inv in invocations}))

        receipt_id = f"admission-{admission_id}"
        subject = admission_receipt_subject(lock_receipt_ref, authorized_action_ids, authorized_tools, registry_ref)
        _, receipt_digest = self._receipts.issue_verified(receipt_id, issuer_id, subject)
        return BuildAdmissionReceipt(
            admission_id=admission_id,
            lock_receipt_ref=lock_receipt_ref,
            authorized_action_ids=authorized_action_ids,
            authorized_tool_ids=authorized_tools,
            tool_registry_ref=registry_ref,
            recovery_readiness_ref=recovery_readiness_ref,
            receipt_ref=ReceiptRef(
                receipt_id=receipt_id,
                receipt_digest=receipt_digest,
                issuer_id=issuer_id,
            ),
        )
