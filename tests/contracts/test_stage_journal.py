"""Actual SQLite append, replay, identity, and JSONL projection tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest

from agent.contracts.stage_log import StageLogEvent
from agent.runtime.stage_journal import StageJournalError, StageJournalService


def event(event_id: str = "one", stage: str = "search", **changes):
    return StageLogEvent(
        event_id=event_id,
        sequence=1,
        workspace_id="w",
        task_id="t",
        run_id="r",
        stage=stage,
        event="started",
        status="running",
        summary="Started",
        created_at=datetime(2026, 11, 3, tzinfo=UTC),
        **changes,
    )


def test_per_run_order_and_idempotency(tmp_path):
    service = StageJournalService(tmp_path / "runtime", tmp_path / "events.db")
    assert service.append(event()).sequence == 1
    assert service.append(event("two", "audit")).sequence == 2
    assert service.append(event()).sequence == 1
    assert len(service.load(workspace_id="w", task_id="t", run_id="r", stage="search")) == 1
    assert len((tmp_path / "runtime/w/t/r/search.log").read_text().splitlines()) == 1
    assert len((tmp_path / "runtime/w/t/r/audit.log").read_text().splitlines()) == 1


def test_rebuild_after_lost_projection(tmp_path):
    service = StageJournalService(tmp_path / "runtime", tmp_path / "events.db")
    service.append(event())
    log = tmp_path / "runtime/w/t/r/search.log"
    log.unlink()
    restarted = StageJournalService(tmp_path / "runtime", tmp_path / "events.db")
    restarted.rebuild("w", "t", "r")
    assert '"event_id":"one"' in log.read_text()


def test_conflicting_replay_rejected(tmp_path):
    service = StageJournalService(tmp_path / "runtime", tmp_path / "events.db")
    service.append(event())
    with pytest.raises(StageJournalError, match="conflicting"):
        service.append(event("one", "build"))


def test_identity_and_symlink_defense(tmp_path):
    service = StageJournalService(tmp_path / "runtime", tmp_path / "events.db")
    with pytest.raises(StageJournalError, match="invalid"):
        service.rebuild("../other", "t", "r")
    (tmp_path / "runtime/w").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(StageJournalError, match="symlink"):
        service.rebuild("w", "t", "r")


def test_memory_requires_promotion(tmp_path):
    service = StageJournalService(tmp_path / "runtime", tmp_path / "events.db")
    with pytest.raises(StageJournalError, match="verified host memory"):
        service.append(event("memo", "mem"))
    assert service.load(workspace_id="w", task_id="t", run_id="r", stage="mem") == ()


def test_parallel_appends_reconstruct_same_order_as_sqlite(tmp_path):
    service = StageJournalService(tmp_path / "runtime", tmp_path / "events.db")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda index: service.append(event(f"event-{index}")), range(12)))
    records = service.load(workspace_id="w", task_id="t", run_id="r", stage="search")
    assert [record.sequence for record in records] == list(range(1, 13))
    projected = (tmp_path / "runtime/w/t/r/search.log").read_text().splitlines()
    assert len(projected) == 12
    assert [StageLogEvent.model_validate_json(raw).sequence for raw in projected] == list(range(1, 13))
