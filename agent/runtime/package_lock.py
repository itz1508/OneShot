"""Package Lock — bind all upstream artifacts before build admission."""

from __future__ import annotations

from agent.contracts.common import ArtifactRef
from agent.contracts.host import PackageLockReceipt, ReceiptRef
from agent.runtime.artifact_store import ArtifactStore
from agent.runtime.receipt_store import ReceiptStore


class PackageLockError(Exception):
    pass


class PackageLock:
    """Host-owned package lock.

    Binds Research, Audit, frozen spec, and fixture result digests.
    Rejects drift — any change in upstream artifacts invalidates the lock.
    """

    def __init__(self, artifact_store: ArtifactStore, receipt_store: ReceiptStore) -> None:
        self._store = artifact_store
        self._receipts = receipt_store

    def lock(
        self,
        lock_id: str,
        research_ref: ArtifactRef,
        audit_ref: ArtifactRef,
        frozen_spec_ref: ArtifactRef,
        fixture_result_ref: ArtifactRef | None = None,
        policy_ref: ArtifactRef | None = None,
        issuer_id: str = "host",
    ) -> PackageLockReceipt:
        """Create a package lock binding all upstream artifacts."""
        # Verify all artifacts exist
        for ref in [research_ref, audit_ref, frozen_spec_ref]:
            self._store.get_digest(ref.artifact_id, ref.artifact_revision)
        if fixture_result_ref:
            self._store.get_digest(fixture_result_ref.artifact_id, fixture_result_ref.artifact_revision)
        if policy_ref:
            self._store.get_digest(policy_ref.artifact_id, policy_ref.artifact_revision)

        # Issue lock receipt
        lock_receipt_id = f"lock-{lock_id}"
        subject = f"{research_ref.artifact_digest}:{audit_ref.artifact_digest}:{frozen_spec_ref.artifact_digest}"
        _, lock_receipt_digest = self._receipts.issue_verified(lock_receipt_id, issuer_id, subject)

        return PackageLockReceipt(
            lock_id=lock_id,
            research_ref=research_ref,
            audit_ref=audit_ref,
            frozen_spec_ref=frozen_spec_ref,
            fixture_result_ref=fixture_result_ref,
            policy_ref=policy_ref,
            receipt_ref=ReceiptRef(
                receipt_id=lock_receipt_id,
                receipt_digest=lock_receipt_digest,
                issuer_id=issuer_id,
            ),
        )
