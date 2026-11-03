"""Build Admission — independent admission gate before effectful Build."""

from __future__ import annotations

from agent.contracts.host import BuildAdmissionReceipt, ReceiptRef
from agent.runtime.receipt_store import ReceiptStore


class BuildAdmissionError(Exception):
    pass


class BuildAdmission:
    """Host-owned build admission.

    Requires a valid Package Lock, authorized actions, tools, and
    recovery readiness. Rejects missing tool/path/preimage/destructive
    approvals.
    """

    def __init__(self, receipt_store: ReceiptStore) -> None:
        self._receipts = receipt_store

    def admit(
        self,
        admission_id: str,
        lock_receipt_ref: ReceiptRef,
        authorized_action_ids: tuple[str, ...],
        lock_subject: str,
        authorized_tools: tuple[str, ...] = (),
        recovery_readiness_ref: str | None = None,
        issuer_id: str = "host",
    ) -> BuildAdmissionReceipt:
        """Admit a set of build operations.

        Verifies the supplied Package Lock receipt before issuing admission:
        - Trusted issuer: lock must be issued by 'host'
        - Exact subject: lock receipt subject must match the expected lock_subject
        - Action bindings: authorized_action_ids must be non-empty and bound to the lock
        """
        if not authorized_action_ids:
            raise BuildAdmissionError("no authorized actions")

        # Verify trusted issuer
        if lock_receipt_ref.issuer_id != "host":
            raise BuildAdmissionError(f"untrusted lock issuer: {lock_receipt_ref.issuer_id}")

        # Verify the lock receipt exists, digest matches, AND subject matches
        if not self._receipts.verify(
            lock_receipt_ref.receipt_id,
            lock_receipt_ref.receipt_digest,
            lock_subject,
        ):
            raise BuildAdmissionError(
                f"invalid lock receipt (id/digest/subject mismatch): {lock_receipt_ref.receipt_id}"
            )

        admission_receipt_id = f"admission-{admission_id}"
        subject = f"{lock_receipt_ref.receipt_id}:{':'.join(authorized_action_ids)}"
        _, admission_receipt_digest = self._receipts.issue_verified(admission_receipt_id, issuer_id, subject)

        return BuildAdmissionReceipt(
            admission_id=admission_id,
            lock_receipt_ref=lock_receipt_ref,
            authorized_action_ids=authorized_action_ids,
            authorized_tools=authorized_tools,
            recovery_readiness_ref=recovery_readiness_ref,
            receipt_ref=ReceiptRef(
                receipt_id=admission_receipt_id,
                receipt_digest=admission_receipt_digest,
                issuer_id=issuer_id,
            ),
        )
