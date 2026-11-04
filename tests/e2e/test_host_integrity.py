"""Adversarial regression tests for artifact-bound receipts and durable Research recovery."""

from __future__ import annotations

import multiprocessing
import sqlite3
from pathlib import Path

import pytest
from pydantic import BaseModel

from agent.contracts.common import ArtifactRef
from agent.contracts.host import ReceiptRef
from agent.contracts.research import Requirement, ResearchRecord
from agent.contracts.work_todo import WorkBinding, WorkStatus
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE
from agent.runtime.controller import HostController, Stage, TransitionError
from mvp.mcp_research import research_artifact_id
from mvp.research_host import execute_research
from mvp.service import MVPError, MVPService


class _Evidence(BaseModel):
    value: str


def _artifact(host: HostController, artifact_id: str, value: str) -> ArtifactRef:
    digest = host.artifact_store.put_immutable(_Evidence(value=value), artifact_id, 1, "fixture", "1.0")
    return ArtifactRef(
        artifact_id=artifact_id,
        artifact_revision=1,
        artifact_digest=digest,
        contract_id="fixture",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )


def _completed_research_work(host: HostController, task_id: str, run_id: str) -> tuple[ArtifactRef, ArtifactRef]:
    source = _artifact(host, f"input-{task_id}", "authorized input")
    binding = WorkBinding(
        task_id=task_id,
        run_id=run_id,
        stage="research",
        request_id=f"research-{task_id}",
        request_revision=1,
        input_request_ref=source,
    )
    _, first = host.assign_work(binding, action="Inspect source", expected_result="Evidence persisted")
    _, running = host.work_todos.set_status(first, "work-1", WorkStatus.RUNNING)
    evidence = _artifact(host, f"result-{task_id}", "observed result")
    _, done = host.work_todos.set_status(
        running, "work-1", WorkStatus.COMPLETED, actual_result="Observed", evidence_refs=(evidence,)
    )
    return done, evidence


def test_receipt_binds_exact_output_and_stage_transition(tmp_path: Path) -> None:
    host = HostController(tmp_path)
    host.init_task("task-one", "run-one")
    todo, evidence = _completed_research_work(host, "task-one", "run-one")
    receipt = host.issue_stage_receipt(
        Stage.RESEARCH,
        task_id="task-one",
        run_id="run-one",
        artifact_id=evidence.artifact_id,
        revision=evidence.artifact_revision,
        artifact_digest=evidence.artifact_digest,
    )
    subject = host.receipt_store.get_subject(receipt.receipt_id)
    assert subject == (f"stage_complete:task-one:run-one:research:{evidence.artifact_id}:1:{evidence.artifact_digest}")
    stage = host.advance_stage("task-one", "run-one", Stage.RESEARCH, receipt, todo_ref=todo)
    assert stage.current_stage is Stage.AUDIT_DISCOVERY


def test_legacy_stage_receipt_rejected(tmp_path: Path) -> None:
    host = HostController(tmp_path)
    host.init_task("task-one", "run-one")
    todo, _ = _completed_research_work(host, "task-one", "run-one")
    _, digest = host.receipt_store.issue_verified("old-receipt", "host", "stage_complete:task-one:run-one:research")
    old = ReceiptRef(receipt_id="old-receipt", receipt_digest=digest, issuer_id="host")
    with pytest.raises(TransitionError, match="invalid completion receipt"):
        host.advance_stage("task-one", "run-one", Stage.RESEARCH, old, todo_ref=todo)


def test_receipt_with_unrelated_artifact_cannot_complete_stage(tmp_path: Path) -> None:
    host = HostController(tmp_path)
    host.init_task("task-one", "run-one")
    todo, _ = _completed_research_work(host, "task-one", "run-one")
    unrelated = _artifact(host, "unrelated-output", "not this work")
    receipt = host.issue_stage_receipt(
        Stage.RESEARCH,
        task_id="task-one",
        run_id="run-one",
        artifact_id=unrelated.artifact_id,
        revision=1,
        artifact_digest=unrelated.artifact_digest,
    )
    with pytest.raises(TransitionError, match="evidence not in completed work"):
        host.advance_stage("task-one", "run-one", Stage.RESEARCH, receipt, todo_ref=todo)
    assert host.get_state("task-one").current_stage is Stage.RESEARCH


def test_forged_receipt_digest_fails(tmp_path: Path) -> None:
    host = HostController(tmp_path)
    host.init_task("task-one", "run-one")
    todo, evidence = _completed_research_work(host, "task-one", "run-one")
    receipt = host.issue_stage_receipt(
        Stage.RESEARCH,
        task_id="task-one",
        run_id="run-one",
        artifact_id=evidence.artifact_id,
        revision=1,
        artifact_digest=evidence.artifact_digest,
    )
    forged = ReceiptRef(receipt_id=receipt.receipt_id, receipt_digest="f" * 64, issuer_id="host")
    with pytest.raises(TransitionError, match="unverified host provenance"):
        host.advance_stage("task-one", "run-one", Stage.RESEARCH, forged, todo_ref=todo)


def _interrupted_research(service: MVPService, persist_output: bool) -> str:
    task_id = str(service.create("Inspect authorized files")["task_id"])
    state = service.host.get_state(task_id)
    assert state is not None
    _, revision, input_digest = service.read_input(task_id)
    input_ref = ArtifactRef(
        artifact_id=f"mvp-input:{task_id}",
        artifact_revision=revision,
        artifact_digest=input_digest,
        contract_id="mvp_task_input",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )
    _, _, first = service.host.prepare_agent_dispatch(
        task_id,
        input_ref,
        "Inspect authorized files",
        requested_role="researcher",
        action="Execute verified MCP Research",
        expected_result="ResearchRecord validated and persisted by the host",
    )
    service.host.work_todos.set_status(first, "work-1", WorkStatus.RUNNING)
    if persist_output:
        artifact = ResearchRecord(
            task_id=task_id,
            run_id=state.run_id,
            stage_revision=1,
            requirements=(
                Requirement(
                    requirement_id="REQ-001",
                    source_reference="request",
                    original_wording="Inspect authorized files",
                    statement="Inspect authorized files before implementation",
                ),
            ),
        )
        service.artifacts.put_immutable(
            artifact,
            research_artifact_id(task_id, state.run_id),
            1,
            "research_record",
            "1.0",
        )
    return task_id


def test_recovery_after_artifact_persistence_without_upstream_retry(tmp_path: Path, monkeypatch) -> None:
    service = MVPService(tmp_path)
    task_id = _interrupted_research(service, True)

    def upstream_must_not_run(*_args, **_kwargs):
        raise AssertionError("MCP may not be retried after uncertain effects")

    monkeypatch.setattr(service.host.providers, "generate", upstream_must_not_run)
    restarted = MVPService(tmp_path)
    monkeypatch.setattr(restarted.host.providers, "generate", upstream_must_not_run)
    outcome = execute_research(restarted, task_id)
    assert outcome["current_stage"] == "audit_discovery"
    assert sum(event["type"] == "stage_transition" for event in restarted.events(task_id)) == 1
    with pytest.raises(MVPError, match="not active"):
        execute_research(restarted, task_id)


def test_uncertain_upstream_without_persisted_artifact_stays_blocked(tmp_path: Path) -> None:
    service = MVPService(tmp_path)
    task_id = _interrupted_research(service, False)
    with pytest.raises(MVPError, match="upstream effect uncertain"):
        execute_research(MVPService(tmp_path), task_id)
    assert service.host.get_state(task_id).current_stage is Stage.RESEARCH


def test_sqlite_admission_blocks_other_service_instance(tmp_path: Path) -> None:
    task_id = "a" * 32
    first = MVPService(tmp_path)
    second = MVPService(tmp_path)
    with first.research_slot(task_id), pytest.raises(MVPError, match="conflict"), second.research_slot(task_id):
        raise AssertionError("must not acquire")
    with second.research_slot(task_id):
        pass


def test_dead_process_admission_can_be_reclaimed(tmp_path: Path) -> None:
    service = MVPService(tmp_path)
    task_id = "b" * 32
    with sqlite3.connect(str(tmp_path / "research_admission.db")) as conn:
        conn.execute(
            "INSERT INTO active_research (task_id, owner_token, owner_pid) VALUES (?, ?, ?)",
            (task_id, "stale-token", 2_000_000_000),
        )
    with service.research_slot(task_id):
        pass
    with sqlite3.connect(str(tmp_path / "research_admission.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM active_research WHERE task_id = ?", (task_id,)).fetchone()[0] == 0


def _hold_research_slot(state_root: str, task_id: str, ready: object, release: object) -> None:
    """Separate process holding a real SQLite admission record."""
    service = MVPService(state_root)
    with service.research_slot(task_id):
        ready.set()
        if not release.wait(timeout=20):
            raise RuntimeError("slot holder timed out")


def test_independent_processes_cannot_run_same_research(tmp_path: Path) -> None:
    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Event()
    release = ctx.Event()
    task_id = "c" * 32
    child = ctx.Process(target=_hold_research_slot, args=(str(tmp_path), task_id, ready, release))
    child.start()
    try:
        assert ready.wait(timeout=15), "child process failed to acquire Research slot"
        with pytest.raises(MVPError, match="conflict"), MVPService(tmp_path).research_slot(task_id):
            raise AssertionError("duplicate Research admitted")
    finally:
        release.set()
        child.join(timeout=15)
        if child.is_alive():
            child.terminate()
            child.join(timeout=5)
    assert child.exitcode == 0
    with MVPService(tmp_path).research_slot(task_id):
        pass


def test_crashed_process_slot_is_reclaimable_without_replaying_mcp(tmp_path: Path) -> None:
    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Event()
    release = ctx.Event()
    task_id = "d" * 32
    child = ctx.Process(target=_hold_research_slot, args=(str(tmp_path), task_id, ready, release))
    child.start()
    try:
        assert ready.wait(timeout=15), "child process failed to acquire Research slot"
        child.terminate()
        child.join(timeout=15)
        assert child.exitcode is not None
        with MVPService(tmp_path).research_slot(task_id):
            pass
    finally:
        if child.is_alive():
            child.kill()
            child.join(timeout=5)
