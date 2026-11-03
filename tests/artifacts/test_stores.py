"""Artifact and receipt store tests — ART01-ART12."""

import pytest
from pydantic import BaseModel

from agent.runtime.artifact_store import (
    ArtifactNotFoundError,
    ArtifactStore,
    DuplicateArtifactError,
)
from agent.runtime.checkpoint_store import (
    CheckpointStore,
    CompetingWriterError,
)
from agent.runtime.event_store import EventStore
from agent.runtime.receipt_store import ReceiptStore


class ArtifactDataModel(BaseModel):
    name: str
    value: int


class ArtifactDataModelStore:
    def test_put_and_get(self, tmp_path):
        """ART01: Store and retrieve an artifact."""
        store = ArtifactStore(tmp_path)
        model = ArtifactDataModel(name="test", value=42)
        store.put_immutable(model, "art-001", 1, "test", "1.0")
        retrieved = store.get_verified("art-001", 1)
        assert b'"name":"test"' in retrieved or b'"name": "test"' in retrieved

    def test_idempotent_put(self, tmp_path):
        """ART02: Same content same revision is idempotent."""
        store = ArtifactStore(tmp_path)
        model = ArtifactDataModel(name="test", value=42)
        d1 = store.put_immutable(model, "art-001", 1, "test", "1.0")
        d2 = store.put_immutable(model, "art-001", 1, "test", "1.0")
        assert d1 == d2

    def test_different_content_same_rev_rejected(self, tmp_path):
        """ART03: Different content same revision rejected."""
        store = ArtifactStore(tmp_path)
        store.put_immutable(ArtifactDataModel(name="a", value=1), "art-001", 1, "test", "1.0")
        with pytest.raises(DuplicateArtifactError):
            store.put_immutable(ArtifactDataModel(name="b", value=2), "art-001", 1, "test", "1.0")

    def test_not_found(self, tmp_path):
        """ART04: Missing artifact raises."""
        store = ArtifactStore(tmp_path)
        with pytest.raises(ArtifactNotFoundError):
            store.get_verified("missing", 1)

    def test_revision_tracking(self, tmp_path):
        """ART05: Multiple revisions tracked."""
        store = ArtifactStore(tmp_path)
        store.put_immutable(ArtifactDataModel(name="v1", value=1), "art-001", 1, "test", "1.0")
        store.put_immutable(ArtifactDataModel(name="v2", value=2), "art-001", 2, "test", "1.0")
        assert store.latest_revision("art-001") == 2

    def test_digest_retrieval(self, tmp_path):
        """ART06: Get digest without content."""
        store = ArtifactStore(tmp_path)
        model = ArtifactDataModel(name="test", value=42)
        digest = store.put_immutable(model, "art-001", 1, "test", "1.0")
        assert store.get_digest("art-001", 1) == digest


class TestReceiptStore:
    def test_issue_and_verify(self, tmp_path):
        """ART07: Issue and verify a receipt."""
        store = ReceiptStore(tmp_path)
        _rid, rdigest = store.issue_verified("rec-001", "host", "abc123")
        assert store.verify("rec-001", rdigest, "abc123") is True

    def test_wrong_subject_rejected(self, tmp_path):
        """ART08: Wrong subject digest rejected."""
        store = ReceiptStore(tmp_path)
        _, rdigest = store.issue_verified("rec-001", "host", "abc123")
        assert store.verify("rec-001", rdigest, "wrong") is False

    def test_wrong_digest_rejected(self, tmp_path):
        """ART09: Wrong receipt digest rejected."""
        store = ReceiptStore(tmp_path)
        store.issue_verified("rec-001", "host", "abc123")
        assert store.verify("rec-001", "wrong", "abc123") is False


class TestEventStore:
    def test_append_and_list(self, tmp_path):
        """ART10: Events appended and listed in order."""
        store = EventStore(tmp_path)
        store.append("task-001", "init", "started")
        store.append("task-001", "transition", "stage1->stage2")
        events = store.list("task-001")
        assert len(events) == 2
        assert events[0]["seq"] < events[1]["seq"]


class TestCheckpointStore:
    def test_cas_success(self, tmp_path):
        """ART11: CAS checkpoint succeeds."""
        store = CheckpointStore(tmp_path)
        rev, digest = store.checkpoint_cas("task-001", 0, {"stage": "research"})
        assert rev == 1
        assert len(digest) == 64

    def test_cas_competing_writer(self, tmp_path):
        """ART12: CAS detects competing writer."""
        store = CheckpointStore(tmp_path)
        store.checkpoint_cas("task-001", 0, {"stage": "research"})
        with pytest.raises(CompetingWriterError):
            store.checkpoint_cas("task-001", 0, {"stage": "audit"})  # wrong expected prev

    def test_load_checkpoint(self, tmp_path):
        """Load latest checkpoint."""
        store = CheckpointStore(tmp_path)
        store.checkpoint_cas("task-001", 0, {"stage": "research"})
        result = store.load_checkpoint("task-001")
        assert result is not None
        rev, state, _ = result
        assert rev == 1
        assert state["stage"] == "research"
