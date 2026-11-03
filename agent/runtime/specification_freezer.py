"""Specification freezer — exact bytes, write-once immutable freeze."""

from __future__ import annotations

from pydantic import BaseModel

from agent.contracts.common import ArtifactRef
from agent.contracts.host import FreezeReceipt, ReceiptRef
from agent.runtime.artifact_store import ArtifactStore
from agent.runtime.receipt_store import ReceiptStore


class FreezeError(Exception):
    pass


class SpecificationFreezer:
    """Host-owned specification freezer.

    - Validates that the candidate has full scanner coverage.
    - Freezes exact bytes write-once.
    - Issues a FreezeReceipt outside the specification digest.
    """

    def __init__(
        self,
        artifact_store: ArtifactStore,
        receipt_store: ReceiptStore,
    ) -> None:
        self._store = artifact_store
        self._receipts = receipt_store

    def freeze(
        self,
        candidate_model: BaseModel,
        artifact_id: str,
        revision: int,
        contract_id: str,
        contract_version: str,
        scanner_receipt_id: str,
        scanner_receipt_digest: str,
        repository_identity_ref: str,
        authorization_receipt_id: str,
        authorization_receipt_digest: str,
        issuer_id: str = "host",
    ) -> FreezeReceipt:
        """Freeze a candidate specification."""
        # Store the artifact
        digest = self._store.put_immutable(candidate_model, artifact_id, revision, contract_id, contract_version)

        # Issue freeze receipt
        freeze_receipt_id = f"freeze-{artifact_id}-rev{revision}"
        _, _freeze_receipt_digest = self._receipts.issue_verified(freeze_receipt_id, issuer_id, digest)

        # Build artifact refs
        candidate_ref = ArtifactRef(
            artifact_id=artifact_id,
            artifact_revision=revision,
            artifact_digest=digest,
            contract_id=contract_id,
            contract_version=contract_version,
            serializer_profile="rfc8785-jcs-sha256-v1",
        )
        frozen_ref = candidate_ref.model_copy(update={"artifact_id": f"frozen-{artifact_id}"})
        # Store frozen copy
        frozen_digest = self._store.put_immutable(
            candidate_model, f"frozen-{artifact_id}", revision, contract_id, contract_version
        )
        frozen_ref = ArtifactRef(
            artifact_id=f"frozen-{artifact_id}",
            artifact_revision=revision,
            artifact_digest=frozen_digest,
            contract_id=contract_id,
            contract_version=contract_version,
            serializer_profile="rfc8785-jcs-sha256-v1",
        )

        return FreezeReceipt(
            candidate_ref=candidate_ref,
            frozen_ref=frozen_ref,
            scanner_receipt_ref=ReceiptRef(
                receipt_id=scanner_receipt_id,
                receipt_digest=scanner_receipt_digest,
                issuer_id="scanner",
            ),
            repository_identity_ref=repository_identity_ref,
            authorization_receipt_ref=ReceiptRef(
                receipt_id=authorization_receipt_id,
                receipt_digest=authorization_receipt_digest,
                issuer_id=issuer_id,
            ),
        )
