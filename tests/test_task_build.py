"""Independent E2E behavior: persistent Task, host-authored Plan and bounded Build."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from build import BuildPolicy, BuildRejected, reconcile_interrupted_builds, run_build
from scanner import admit_file, inspect_text
from task import TaskRejected, TaskStore


def create_plan(store: TaskStore, *, request_id: str = "req-one") -> tuple[str, str]:
    task = store.create_task(request_id=request_id, objective="Prepare a synthetic reviewed artifact")
    plan = {"type": "plan", "id": "plan-approved-1", "request_id": request_id,
            "actions": [{"description": "Create the reviewed report", "target": "report.txt"}]}
    store.save_host_result(task_id=task["id"], expected_revision=0, value=plan)
    return task["id"], plan["id"]


def test_task_restart_final_result_and_events(tmp_path: Path) -> None:
    db = tmp_path / "state" / "task.sqlite"
    store = TaskStore(db, scope="thread-1")
    task = store.create_task(request_id="req-1", objective="Inspect policy")
    assert store.create_task(request_id="req-1", objective="Inspect policy")["id"] == task["id"]
    research = {"type": "research", "id": "r-1", "request_id": "req-1",
                "findings": [{"statement": "7 day retention", "source_refs": ["policy.txt:0-17"]}]}
    updated = store.save_host_result(task_id=task["id"], expected_revision=0, value=research)
    assert updated["revision"] == 1
    assert store.finish_task(task_id=task["id"], expected_revision=1,
                             result_type="research", result_id="r-1")["revision"] == 2
    store2 = TaskStore(db, scope="thread-1")
    assert store2.get_final(task["id"]) == research
    assert [v["kind"] for v in store2.events(task["id"])] == ["created", "result_recorded", "finalized"]
    with pytest.raises(TaskRejected, match="Stale"):
        store2.finish_task(task_id=task["id"], expected_revision=1,
                           result_type="research", result_id="r-1")
    with pytest.raises(TaskRejected):
        store2.save_host_result(task_id=task["id"], expected_revision=2, value=research)


def test_task_scope_isolation_and_wrong_links(tmp_path: Path) -> None:
    db = tmp_path / "database.sqlite"
    store = TaskStore(db, scope="allowed")
    task = store.create_task(request_id="req-one", objective="do work")
    isolated = TaskStore(db, scope="other")
    with pytest.raises(TaskRejected):
        isolated.get_task(task["id"])
    with pytest.raises(TaskRejected):
        isolated.get_final(task["id"])
    with pytest.raises(TaskRejected):
        store.save_host_result(task_id=task["id"], expected_revision=0, value={
            "type": "plan", "id": "plan-1", "request_id": "req-one", "research_id": "unknown",
            "actions": [{"description": "some work"}],
        })
    assert store.get_task(task["id"])["revision"] == 0
    with pytest.raises(TaskRejected):
        store.save_host_result(task_id=task["id"], expected_revision=0, value={
            "type": "build", "id": "build-1", "request_id": "req-one", "plan_id": "p",
            "execution": {"outcome": "succeeded", "artifact_refs": ["artifact-1"]},
            "verification": {"outcome": "valid", "evidence_refs": ["sha256:" + "1"*64]},
            "cleanup": {"outcome": "completed"},
        })


def test_synthetic_end_to_end_scanner_task_plan_builder_cleanup_restart(tmp_path: Path) -> None:
    source = tmp_path / "sources"
    source.mkdir()
    (source / "policy.txt").write_text("Keep logs seven days.\nKeep logs seven days.\n", encoding="utf-8")
    admitted = admit_file(trusted_root=source, relative_name="policy.txt", source_id="source-1")
    scan = inspect_text(admitted)
    assert scan["findings"][0]["kind"] == "exact_repeated_line"
    assert len(scan["findings"][0]["byte_spans"]) == 2
    db = tmp_path / "state.sqlite"
    store = TaskStore(db, scope="thread")
    task = store.create_task(request_id="req-one", objective="Write a bounded source review")
    research = {"type": "research", "id": "r-1", "request_id": "req-one",
                "findings": [{"statement": "Exact line occurs twice", "source_refs": ["source-1:0-21"]}]}
    task = store.save_host_result(task_id=task["id"], expected_revision=0, value=research)
    plan = {"type": "plan", "id": "p-1", "request_id": "req-one", "research_id": "r-1",
            "actions": [{"description": "Create standalone reviewed report", "target": "review.txt"}]}
    task = store.save_host_result(task_id=task["id"], expected_revision=1, value=plan)
    workspace = tmp_path / "build-space"
    workspace.mkdir()
    policy = BuildPolicy(workspace, frozenset({f"{task['id']}:p-1"}))
    result = run_build(store=store, policy=policy, task_id=task["id"], expected_revision=task["revision"],
                       plan_id="p-1", writes=[{"name": "review.txt", "content": "Exact repeated line verified.\n"}])
    assert result["execution"]["outcome"] == "succeeded"
    assert result["verification"]["outcome"] == "valid"
    assert result["cleanup"] == {"outcome": "completed", "remaining_refs": []}
    artifact = workspace / "artifacts" / "review.txt"
    assert artifact.read_text() == "Exact repeated line verified.\n"
    assert result["verification"]["evidence_refs"] == ["sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()]
    assert not (workspace / "build_tmp" / result["id"]).exists()
    fresh_store = TaskStore(db, scope="thread")
    final_task = fresh_store.finish_task(task_id=task["id"], expected_revision=fresh_store.get_task(task["id"])["revision"],
                                         result_type="build", result_id=result["id"])
    assert fresh_store.get_final(task["id"]) == result
    assert fresh_store.get_task(task["id"])["revision"] == final_task["revision"]
    assert [x["kind"] for x in fresh_store.events(task["id"])][-4:] == ["build_started", "build_observed", "build_finished", "finalized"]
    assert not fresh_store.pending_builds()


def test_build_requires_grant_and_named_targets(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "state.sqlite", scope="thread")
    task_id, plan_id = create_plan(store)
    root = tmp_path / "workspace"
    root.mkdir()
    args = dict(store=store, task_id=task_id, expected_revision=1, plan_id=plan_id)
    with pytest.raises(BuildRejected, match="grant"):
        run_build(**args, policy=BuildPolicy(root, frozenset()),
                  writes=[{"name": "report.txt", "content": "ok"}])
    policy = BuildPolicy(root, frozenset({f"{task_id}:{plan_id}"}))
    for bad in ("../outside.txt", "other.txt", "CON", "nested/file.txt"):
        with pytest.raises(BuildRejected):
            run_build(**args, policy=policy, writes=[{"name": bad, "content": "bad"}])
    assert store.get_task(task_id)["revision"] == 1
    assert not list(root.iterdir())


def test_overwrite_rejected_without_rewriting_original(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "state.sqlite", scope="thread")
    task_id, plan_id = create_plan(store)
    root = tmp_path / "workspace"
    (root / "artifacts").mkdir(parents=True)
    (root / "artifacts" / "report.txt").write_text("original")
    with pytest.raises(BuildRejected, match="overwrite"):
        run_build(store=store, policy=BuildPolicy(root, frozenset({f"{task_id}:{plan_id}"})), task_id=task_id,
                  expected_revision=1, plan_id=plan_id,
                  writes=[{"name": "report.txt", "content": "changed"}])
    assert (root / "artifacts" / "report.txt").read_text() == "original"
    assert store.get_task(task_id)["revision"] == 1


def test_terminated_worker_reconciliation_not_reported_as_success(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "state.sqlite", scope="thread")
    task_id, plan_id = create_plan(store)
    root = tmp_path / "workspace"
    (root / "build_tmp").mkdir(parents=True)
    _, plan = store.begin_build(task_id=task_id, expected_revision=1,
                                plan_id=plan_id, build_id="a" * 32)
    assert plan["id"] == plan_id
    (root / "build_tmp" / ("a" * 32)).mkdir()
    (root / "build_tmp" / ("a" * 32) / "tmp.txt").write_text("temporary")
    second = TaskStore(store.database, scope="thread")
    result = reconcile_interrupted_builds(store=second, policy=BuildPolicy(root, frozenset({f"{task_id}:{plan_id}"})))
    assert len(result) == 1
    assert result[0]["execution"]["outcome"] == "interrupted"
    assert result[0]["verification"]["outcome"] == "not_verified"
    assert result[0]["cleanup"]["outcome"] == "completed"
    assert not (root / "build_tmp" / ("a" * 32)).exists()
    assert not second.pending_builds()
    assert reconcile_interrupted_builds(store=second, policy=BuildPolicy(root, frozenset({f"{task_id}:{plan_id}"}))) == []


def test_failed_build_cleans_owned_resources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import build
    store = TaskStore(tmp_path / "state.sqlite", scope="thread")
    task_id, plan_id = create_plan(store)
    root = tmp_path / "workspace"
    root.mkdir()
    original = build._exclusive_bytes
    def fail_write(target: Path, content: bytes) -> None:
        if target.parent.name == "artifacts":
            raise OSError("synthetic failed disk write")
        original(target, content)
    monkeypatch.setattr(build, "_exclusive_bytes", fail_write)
    result = run_build(store=store, policy=BuildPolicy(root, frozenset({f"{task_id}:{plan_id}"})),
                       task_id=task_id, expected_revision=1, plan_id=plan_id,
                       writes=[{"name": "report.txt", "content": "write"}])
    assert result["execution"]["outcome"] == "failed"
    assert result["cleanup"]["outcome"] == "completed"
    assert not (root / "build_tmp" / result["id"]).exists()
    assert store.get_result(task_id, "build", result["id"]) == result

@pytest.mark.parametrize("raised,expected", [(TimeoutError("synthetic timeout"), "timed_out"),
                                            (KeyboardInterrupt(), "cancelled")])
def test_timeout_or_cancellation_records_and_cleans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, raised: BaseException, expected: str,
) -> None:
    import build
    store = TaskStore(tmp_path / "state.sqlite", scope="thread")
    task_id, plan_id = create_plan(store)
    root = tmp_path / "workspace"
    root.mkdir()
    def fail_write(target: Path, content: bytes) -> None:
        raise raised
    monkeypatch.setattr(build, "_exclusive_bytes", fail_write)
    result = run_build(store=store, policy=BuildPolicy(root, frozenset({f"{task_id}:{plan_id}"})),
                       task_id=task_id, expected_revision=1, plan_id=plan_id,
                       writes=[{"name": "report.txt", "content": "write"}])
    assert result["execution"]["outcome"] == expected
    assert result["cleanup"]["outcome"] == "completed"
    assert not (root / "build_tmp" / result["id"]).exists()
    assert store.get_result(task_id, "build", result["id"]) == result


def test_reconcile_rejects_invalid_internal_cleanup_identity(tmp_path: Path) -> None:
    store = TaskStore(tmp_path / "state.sqlite", scope="thread")
    task_id, plan_id = create_plan(store)
    with pytest.raises(TaskRejected, match="internal build identity"):
        store.begin_build(task_id=task_id, expected_revision=1,
                          plan_id=plan_id, build_id="../../outside")
    assert store.get_task(task_id)["revision"] == 1
