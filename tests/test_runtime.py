"""Test runtime basics: artifact store idempotency, checkpoint CAS."""

from datetime import UTC, datetime

import pytest

from agent.contracts.host import Checkpoint
from agent.contracts.research import Requirement, ResearchRecord
from agent.runtime.artifact_store import ArtifactStore, DuplicateArtifactError
from agent.runtime.checkpoint_store import InMemoryCheckpointStore, StaleCheckpointError

HEX = "a" * 64


def test_artifact_store_idempotent(tmp_path):
    """Storing the same artifact twice with same content is idempotent."""
    store = ArtifactStore(tmp_path / "state")
    record = ResearchRecord(
        task_id="task",
        run_id="run",
        stage_revision=1,
        requirements=(
            Requirement(
                requirement_id="REQ-001",
                source_reference="user",
                original_wording="x",
                statement="x",
            ),
        ),
    )
    digest1 = store.put_immutable(record, "research", 1, "research", "1.0")
    digest2 = store.put_immutable(record, "research", 1, "research", "1.0")
    assert digest1 == digest2


def test_artifact_store_rejects_duplicate_different_content(tmp_path):
    """Storing different content under same artifact_id+revision raises."""
    store = ArtifactStore(tmp_path / "state")
    record1 = ResearchRecord(
        task_id="task",
        run_id="run",
        stage_revision=1,
        requirements=(
            Requirement(
                requirement_id="REQ-001",
                source_reference="user",
                original_wording="x",
                statement="x",
            ),
        ),
    )
    record2 = ResearchRecord(
        task_id="task",
        run_id="run",
        stage_revision=1,
        requirements=(
            Requirement(
                requirement_id="REQ-002",
                source_reference="user",
                original_wording="y",
                statement="y",
            ),
        ),
    )
    store.put_immutable(record1, "research", 1, "research", "1.0")
    with pytest.raises(DuplicateArtifactError):
        store.put_immutable(record2, "research", 1, "research", "1.0")


def make_checkpoint(revision: int, expected: int) -> Checkpoint:
    return Checkpoint(
        checkpoint_id="cp",
        checkpoint_revision=revision,
        expected_previous_revision=expected,
        checkpoint_digest=HEX,
        task_id="task",
        run_id="run",
        stage="planning",
        phase="intake",
        stage_revision=1,
        resume_point="next",
        created_at=datetime.now(UTC),
    )


def test_checkpoint_compare_and_swap_rejects_stale_writer():
    store = InMemoryCheckpointStore()
    store.compare_and_swap(make_checkpoint(1, 0))
    with pytest.raises(StaleCheckpointError):
        store.compare_and_swap(make_checkpoint(2, 0))
    store.compare_and_swap(make_checkpoint(2, 1))
    assert store.get("cp").checkpoint_revision == 2
