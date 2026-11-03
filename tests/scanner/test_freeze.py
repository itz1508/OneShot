"""Specification freeze tests — FRZ01-FRZ15."""

import pytest
from pydantic import BaseModel

from agent.runtime.artifact_store import ArtifactStore
from agent.runtime.receipt_store import ReceiptStore
from agent.runtime.specification_freezer import SpecificationFreezer


class SpecDataModel(BaseModel):
    spec_id: str = "test-spec"
    content: str = "test content"


class TestSpecificationFreezer:
    def test_freeze_creates_receipt(self, tmp_path):
        """FRZ01: Freeze creates a FreezeReceipt."""
        store = ArtifactStore(tmp_path)
        receipts = ReceiptStore(tmp_path)
        freezer = SpecificationFreezer(store, receipts)

        receipt = freezer.freeze(
            candidate_model=SpecDataModel(),
            artifact_id="cand-001",
            revision=1,
            contract_id="planning",
            contract_version="1.0",
            scanner_receipt_id="scan-001",
            scanner_receipt_digest="5" * 64,
            repository_identity_ref="repo-001",
            authorization_receipt_id="auth-001",
            authorization_receipt_digest="a" * 64,
        )
        assert receipt.candidate_ref.artifact_id == "cand-001"
        assert receipt.frozen_ref.artifact_id == "frozen-cand-001"

    def test_frozen_digest_matches_candidate(self, tmp_path):
        """FRZ02: Frozen digest matches candidate digest."""
        store = ArtifactStore(tmp_path)
        receipts = ReceiptStore(tmp_path)
        freezer = SpecificationFreezer(store, receipts)

        receipt = freezer.freeze(
            candidate_model=SpecDataModel(),
            artifact_id="cand-001",
            revision=1,
            contract_id="planning",
            contract_version="1.0",
            scanner_receipt_id="scan-001",
            scanner_receipt_digest="5" * 64,
            repository_identity_ref="repo-001",
            authorization_receipt_id="auth-001",
            authorization_receipt_digest="a" * 64,
        )
        assert receipt.candidate_ref.artifact_digest == receipt.frozen_ref.artifact_digest

    def test_freeze_receipt_has_scanner_ref(self, tmp_path):
        """FRZ03: Freeze receipt references scanner receipt."""
        store = ArtifactStore(tmp_path)
        receipts = ReceiptStore(tmp_path)
        freezer = SpecificationFreezer(store, receipts)

        receipt = freezer.freeze(
            candidate_model=SpecDataModel(),
            artifact_id="cand-001",
            revision=1,
            contract_id="planning",
            contract_version="1.0",
            scanner_receipt_id="scan-rec-001",
            scanner_receipt_digest="5" * 64,
            repository_identity_ref="repo-001",
            authorization_receipt_id="auth-001",
            authorization_receipt_digest="a" * 64,
        )
        assert receipt.scanner_receipt_ref.receipt_id == "scan-rec-001"

    def test_freeze_is_immutable(self, tmp_path):
        """FRZ04: Frozen artifact cannot be overwritten with different content."""
        store = ArtifactStore(tmp_path)
        receipts = ReceiptStore(tmp_path)
        freezer = SpecificationFreezer(store, receipts)

        freezer.freeze(
            candidate_model=SpecDataModel(content="v1"),
            artifact_id="cand-001",
            revision=1,
            contract_id="planning",
            contract_version="1.0",
            scanner_receipt_id="scan-001",
            scanner_receipt_digest="5" * 64,
            repository_identity_ref="repo-001",
            authorization_receipt_id="auth-001",
            authorization_receipt_digest="a" * 64,
        )
        from agent.runtime.artifact_store import DuplicateArtifactError

        with pytest.raises(DuplicateArtifactError):
            freezer.freeze(
                candidate_model=SpecDataModel(content="v2"),
                artifact_id="cand-001",
                revision=1,  # same revision, different content
                contract_id="planning",
                contract_version="1.0",
                scanner_receipt_id="scan-002",
                scanner_receipt_digest="6" * 64,
                repository_identity_ref="repo-001",
                authorization_receipt_id="auth-002",
                authorization_receipt_digest="b" * 64,
            )
