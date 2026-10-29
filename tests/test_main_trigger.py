"""Behavioral CLI acceptance: dynamic task, stage and artifact identities."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4

import pytest

from task import TaskStore

PROJECT = Path(__file__).resolve().parents[1]
NOT_ESTABLISHED = [
    "approver_identity", "source_refs", "research_semantic_correctness",
    "plan_semantic_correctness", "artifact_content_correctness",
    "concurrent_path_identity", "atomic_multi_file_build",
]


def uid() -> str:
    return uuid4().hex


def load_trigger():
    path = PROJECT / "main.py"
    definition = importlib.util.spec_from_file_location(f"trigger_{uid()}", path)
    assert definition and definition.loader
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module


def scenario(tmp_path: Path, *, use_research: bool = True, count: int = 1):
    request_id, plan_id, research_id = uid(), uid(), uid()
    names = [f"{uid()}.txt" for _ in range(count)]
    contents = [f"independent content {uid()}\n" for _ in names]
    spec = {
        "request_id": request_id,
        "objective": f"Produce validated artifacts {uid()}",
        "plan": {"type": "plan", "id": plan_id, "request_id": request_id,
                 "actions": [{"description": f"Generate {name}", "target": name} for name in names]},
        "writes": [{"name": n, "content": c} for n, c in zip(names, contents)],
    }
    if use_research:
        value_id = uid()
        spec["research"] = {
            "type": "research", "id": research_id, "request_id": request_id,
            "findings": [{"statement": "Host-provided observation", "source_refs": [f"source:{uid()}"]}],
            "validation_values": [{"id": value_id, "criterion": "Compare independent bytes",
                                   "expected": contents[0], "source_refs": [f"source:{uid()}"]}],
        }
        spec["plan"]["research_id"] = research_id
        spec["plan"]["validation_value_refs"] = [value_id]
    run_spec = tmp_path / f"{uid()}.json"
    run_spec.write_text(json.dumps(spec), encoding="utf-8")
    build_root = tmp_path / f"workspace_{uid()}"
    build_root.mkdir()
    db = tmp_path / f"{uid()}.sqlite"
    argv = ["--run-spec", str(run_spec), "--state-db", str(db),
            "--scope", f"scope_{uid()}", "--build-root", str(build_root)]
    return spec, run_spec, db, build_root, argv


def invoke(module, capsys, argv):
    code = module.main(argv)
    captured = capsys.readouterr()
    decoder = json.JSONDecoder()
    response, pos = decoder.raw_decode(captured.out.lstrip())
    assert captured.out.lstrip()[pos:].strip() == ""
    assert isinstance(response, dict)
    assert response["not_established"] == NOT_ESTABLISHED
    assert type(response["state_mutated"]) is bool
    if code == 2:
        assert response["state_mutated"] is False
    return code, response


def approval(module, capsys, argv):
    code, response = invoke(module, capsys, argv)
    assert code == 2 and response["gate"] == "review_required"
    return response["approval_digest"]


def assert_refused(module, capsys, argv, *, gate=None):
    code, data = invoke(module, capsys, argv)
    assert code == 2
    assert data["gate"] is gate
    assert data["state_mutated"] is False
    assert data["error"]
    assert set(data["stages"].values()) <= {"not_run", "blocked", "failed", "skipped"}
    return data


def test_dynamic_identity_approved_success_and_restart(tmp_path, capsys):
    module = load_trigger()
    spec, file, db, root, argv = scenario(tmp_path)
    digest = approval(module, capsys, argv)
    assert not db.exists() and not list(root.iterdir())
    code, data = invoke(module, capsys, argv + ["--approve-digest", digest])
    assert code == 0
    assert data["gate"] == "approved_for_apply"
    assert data["stages"] == {"research": "completed", "plan": "completed", "build": "completed"}
    assert data["task"]["final"]
    assert data["task"]["id"] not in {spec["request_id"], spec["plan"]["id"]}
    store = TaskStore(db, scope=argv[argv.index("--scope") + 1])
    assert store.get_final(data["task"]["id"]) == data["build"]
    assert store.get_task(data["task"]["id"])["revision"] == data["task"]["revision"]
    assert store.get_result(data["task"]["id"], "research", spec["research"]["id"]) == spec["research"]
    assert store.get_result(data["task"]["id"], "plan", spec["plan"]["id"]) == spec["plan"]
    path = root / "artifacts" / spec["writes"][0]["name"]
    assert path.read_bytes() == spec["writes"][0]["content"].encode("utf-8")
    assert data["build"]["verification"]["evidence_refs"] == [f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"]
    assert not (root / "build_tmp" / data["build"]["id"]).exists()


def test_without_research_builds_with_dynamic_plan_id(tmp_path, capsys):
    module = load_trigger()
    spec, _, _, _, argv = scenario(tmp_path, use_research=False)
    digest = approval(module, capsys, argv)
    code, data = invoke(module, capsys, argv + ["--approve-digest", digest])
    assert code == 0 and data["stages"]["research"] == "skipped"
    assert data["build"]["plan_id"] == spec["plan"]["id"]


def test_digest_mismatch_tampering_context_and_no_mutation(tmp_path, capsys):
    module = load_trigger()
    spec, path, db, root, argv = scenario(tmp_path)
    digest = approval(module, capsys, argv)
    for changes in (["--approve-digest", "0" * 64], ["--approve-digest", "A" * 64]):
        code, data = invoke(module, capsys, argv + changes)
        assert code == 2 and data["gate"] == "not_approved"
    changed = list(argv)
    for key, updated in (("--scope", f"changed_{uid()}"),
                         ("--state-db", str(tmp_path / f"{uid()}.sqlite")),
                         ("--build-root", str(tmp_path / f"{uid()}"))):
        other = list(changed)
        other[other.index(key) + 1] = updated
        code, data = invoke(module, capsys, other + ["--approve-digest", digest])
        assert code == 2 and data["state_mutated"] is False
    spec["objective"] = "modified after review"
    path.write_text(json.dumps(spec), encoding="utf-8")
    code, response = invoke(module, capsys, argv + ["--approve-digest", digest])
    assert code == 2 and response["gate"] == "not_approved"
    assert not db.exists() and not list(root.iterdir())


@pytest.mark.parametrize("corrupt", [
    lambda s: s.update(extra_field=uid()),
    lambda s: s.update(grant=uid()),
    lambda s: s["plan"].update(request_id=uid()),
    lambda s: s["research"].update(id=""),
    lambda s: s["plan"].update(research_id=uid()),
    lambda s: s["plan"].update(validation_value_refs=[uid()]),
    lambda s: s["research"]["validation_values"].append(dict(s["research"]["validation_values"][0])),
    lambda s: s["plan"].update(actions=[]),
    lambda s: s["writes"][0].update(name=f"{uid()}.dat"),
    lambda s: s["writes"].append(dict(s["writes"][0])),
    lambda s: s["writes"][0].update(name=f"../{uid()}"),
    lambda s: s["writes"][0].update(content="q" * 128001),
    lambda s: s.update(writes=[]),
], ids=["unknown_field", "grant_field", "request_mismatch", "research_schema", "research_id_mismatch",
        "missing_validation_id", "duplicate_validation_id", "empty_targets", "undeclared_name",
        "duplicate_name", "traversal", "oversized_write", "empty_writes"])
def test_invalid_spec_no_mutation(tmp_path, capsys, corrupt):
    module = load_trigger()
    spec, path, db, root, argv = scenario(tmp_path)
    corrupt(spec)
    path.write_text(json.dumps(spec), encoding="utf-8")
    assert_refused(module, capsys, argv)
    assert not db.exists() and not list(root.iterdir())


def test_invalid_research_absent_and_plan_ref_present(tmp_path, capsys):
    module = load_trigger()
    spec, path, db, root, argv = scenario(tmp_path)
    del spec["research"]
    path.write_text(json.dumps(spec))
    assert_refused(module, capsys, argv)
    assert not db.exists() and not list(root.iterdir())


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a": NaN}', b'{"a": Infinity}',
                                  b'\xff\xff', b'{' + b'x' * (2 * 1024 * 1024) + b'}'],
                         ids=["duplicate_keys", "not_a_number", "infinity", "invalid_utf8", "size_exceeded"])
def test_invalid_json_or_size_no_mutation(tmp_path, capsys, raw):
    module = load_trigger()
    _, path, db, root, argv = scenario(tmp_path)
    path.write_bytes(raw)
    assert_refused(module, capsys, argv)
    assert not db.exists() and not list(root.iterdir())


def test_missing_required_argument_json_exit_two(tmp_path, capsys):
    module = load_trigger()
    _, _, _, _, argv = scenario(tmp_path)
    idx = argv.index("--run-spec")
    del argv[idx:idx + 2]
    assert_refused(module, capsys, argv)


def test_link_and_collision_refusal_preserves_workspace(tmp_path, capsys):
    module = load_trigger()
    spec, _, db, root, argv = scenario(tmp_path)
    existing = root / "artifacts"
    existing.mkdir()
    path = existing / spec["writes"][0]["name"]
    path.write_text("original", encoding="utf-8")
    assert_refused(module, capsys, argv)
    assert path.read_text() == "original" and not db.exists()
    assert not (root / "build_tmp").exists()
    linked = tmp_path / f"link_{uid()}"
    try:
        linked.symlink_to(root, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks unavailable in this environment")
    other = list(argv)
    other[other.index("--build-root") + 1] = str(linked)
    assert_refused(module, capsys, other)
    assert not db.exists()


def test_database_incompatible_and_replay_no_state_change(tmp_path, capsys):
    module = load_trigger()
    spec, _, db, root, argv = scenario(tmp_path)
    sqlite3.connect(db).close()
    before = db.read_bytes()
    assert_refused(module, capsys, argv)
    assert db.read_bytes() == before
    db.unlink()
    store = TaskStore(db, scope=argv[argv.index("--scope") + 1])
    store.create_task(request_id=spec["request_id"], objective=spec["objective"])
    before = db.read_bytes()
    assert_refused(module, capsys, argv)
    assert db.read_bytes() == before
    assert not list(root.iterdir())


def test_digest_gate_mutation_detection(tmp_path, capsys, monkeypatch):
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path)
    approval(module, capsys, argv)
    with monkeypatch.context() as patch:
        patch.setattr(module, "_approval_matches", lambda supplied, expected: True)
        with pytest.raises(AssertionError):
            code, data = invoke(module, capsys, argv + ["--approve-digest", "f" * 64])
            assert code == 2 and data["gate"] == "not_approved"
    # The rejection assertion failed under the mutated gate; pytest removes the patch.


def test_second_permanent_write_failure_records_partial_evidence(tmp_path, capsys, monkeypatch):
    import build
    module = load_trigger()
    spec, _, db, root, argv = scenario(tmp_path, count=2)
    digest = approval(module, capsys, argv)
    existing = set((root / "artifacts").iterdir()) if (root / "artifacts").exists() else set()
    original = build._exclusive_bytes
    permanent = 0

    def fail_second_permanent(target, content):
        nonlocal permanent
        if target.parent == root / "artifacts":
            permanent += 1
            if permanent == 2:
                raise OSError("synthetic second permanent failure")
        return original(target, content)

    monkeypatch.setattr(build, "_exclusive_bytes", fail_second_permanent)
    code, data = invoke(module, capsys, argv + ["--approve-digest", digest])
    assert code == 1 and permanent == 2
    assert data["task"]["final"] is False
    assert data["build"]["execution"]["outcome"] == "failed"
    assert data["build"]["verification"]["outcome"] == "not_valid"
    assert data["build"]["cleanup"]["outcome"] == "completed"
    now = set((root / "artifacts").iterdir())
    assert {f"artifacts/{p.name}" for p in now - existing} == set(data["build"]["execution"]["artifact_refs"])
    assert (root / "artifacts" / spec["writes"][0]["name"]).exists()
    assert not (root / "artifacts" / spec["writes"][1]["name"]).exists()
    assert not (root / "build_tmp" / data["build"]["id"]).exists()
    store = TaskStore(db, scope=argv[argv.index("--scope") + 1])
    assert store.get_result(data["task"]["id"], "build", data["build"]["id"]) == data["build"]


def test_escaped_build_failure_no_fabricated_result(tmp_path, capsys, monkeypatch):
    module = load_trigger()
    spec, _, db, root, argv = scenario(tmp_path)
    digest = approval(module, capsys, argv)

    def escape(**kwargs):
        raise OSError("forced escaping failure")

    monkeypatch.setattr(module, "run_build", escape)
    code, data = invoke(module, capsys, argv + ["--approve-digest", digest])
    assert code == 1 and data["build"] is None and not data["task"]["final"]
    store = TaskStore(db, scope=argv[argv.index("--scope") + 1])
    assert store.get_result(data["task"]["id"], "research", spec["research"]["id"]) == spec["research"]
    assert store.get_result(data["task"]["id"], "plan", spec["plan"]["id"]) == spec["plan"]


def run_subprocess(argv):
    result = subprocess.run([sys.executable, str(PROJECT / "main.py"), *argv],
                            cwd=PROJECT, capture_output=True, text=True, check=False)
    parser = json.JSONDecoder()
    value, consumed = parser.raw_decode(result.stdout.lstrip())
    assert result.stdout.lstrip()[consumed:].strip() == ""
    assert isinstance(value, dict) and value["not_established"] == NOT_ESTABLISHED
    return result.returncode, value


def test_subprocess_exit_two(tmp_path):
    _, _, _, _, argv = scenario(tmp_path)
    assert run_subprocess(argv[2:])[0] == 2  # Missing --run-spec


def test_subprocess_exit_zero(tmp_path):
    _, _, _, _, argv = scenario(tmp_path)
    code, review = run_subprocess(argv)
    assert code == 2 and review["gate"] == "review_required"
    code, result = run_subprocess(argv + ["--approve-digest", review["approval_digest"]])
    assert code == 0 and result["task"]["final"]


def test_subprocess_exit_one(tmp_path):
    _, _, db, _, argv = scenario(tmp_path)
    store = TaskStore(db, scope=argv[argv.index("--scope") + 1])
    with sqlite3.connect(db) as conn:
        conn.execute(f"CREATE TRIGGER {('block_' + uid())} BEFORE INSERT ON tasks BEGIN SELECT RAISE(ABORT, 'test insertion refused'); END")
    code, review = run_subprocess(argv)
    assert code == 2 and review["gate"] == "review_required"
    code, result = run_subprocess(argv + ["--approve-digest", review["approval_digest"]])
    assert code == 1 and result["state_mutated"] is True and result["error"]


def test_existing_database_missing_required_columns_or_uniqueness(tmp_path, capsys):
    module = load_trigger()
    spec, _, db, root, argv = scenario(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE tasks (id TEXT, scope TEXT, request_id TEXT)")
    snapshot = db.read_bytes()
    assert_refused(module, capsys, argv)
    assert db.read_bytes() == snapshot and not list(root.iterdir())
    db.unlink()
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, scope TEXT, request_id TEXT, objective TEXT, revision INTEGER, final_type TEXT, final_id TEXT)")
    snapshot = db.read_bytes()
    assert_refused(module, capsys, argv)
    assert db.read_bytes() == snapshot and not list(root.iterdir())


def test_existing_database_in_wal_mode_refused_without_extra_files(tmp_path, capsys):
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path)
    store = TaskStore(db, scope=argv[argv.index("--scope") + 1])
    with sqlite3.connect(db) as conn:
        assert conn.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    before = {p.name: p.read_bytes() for p in db.parent.iterdir() if p.name.startswith(db.name)}
    assert_refused(module, capsys, argv)
    after = {p.name: p.read_bytes() for p in db.parent.iterdir() if p.name.startswith(db.name)}
    assert after == before and not list(root.iterdir())


def test_replay_revision_zero_even_when_objective_matches(tmp_path, capsys):
    module = load_trigger()
    spec, _, db, root, argv = scenario(tmp_path)
    store = TaskStore(db, scope=argv[argv.index("--scope") + 1])
    task = store.create_task(request_id=spec["request_id"], objective=spec["objective"])
    assert task["revision"] == 0
    before = db.read_bytes()
    assert_refused(module, capsys, argv)
    assert db.read_bytes() == before and not list(root.iterdir())


def test_existing_database_corruption(tmp_path, capsys):
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path)
    db.write_bytes(b"not sqlite")
    assert_refused(module, capsys, argv)
    assert db.read_bytes() == b"not sqlite" and not list(root.iterdir())


@pytest.mark.parametrize("replacement", ["CON.txt", "COM9.txt", "LPT9.log", "a?.txt", "a<.txt", "a|.txt"])
def test_cross_platform_unsafe_filename_rejected(tmp_path, capsys, replacement):
    module = load_trigger()
    spec, filename, db, root, argv = scenario(tmp_path)
    spec["plan"]["actions"][0]["target"] = replacement
    spec["writes"][0]["name"] = replacement
    filename.write_text(json.dumps(spec))
    assert_refused(module, capsys, argv)
    assert not db.exists() and not list(root.iterdir())


def test_scope_exact_and_whitespace_rejected(tmp_path, capsys):
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path)
    original = approval(module, capsys, argv)
    altered = list(argv)
    altered[altered.index("--scope") + 1] += " "
    code, response = invoke(module, capsys, altered + ["--approve-digest", original])
    assert code == 2 and response["gate"] == "not_approved"
    empty = list(argv)
    empty[empty.index("--scope") + 1] = "   "
    assert_refused(module, capsys, empty)
    assert not db.exists() and not list(root.iterdir())


def test_environment_does_not_grant_permission(tmp_path, capsys, monkeypatch):
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path)
    monkeypatch.setenv("ONESHOT_APPROVED_BUILDS", "*")
    code, data = invoke(module, capsys, argv)
    assert code == 2 and data["gate"] == "review_required"
    assert not db.exists() and not list(root.iterdir())


def test_escape_before_mutation_reports_null_gate(tmp_path, capsys):
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path)
    result = assert_refused(module, capsys, argv + ["--approve-digest", "not-a-digest"])
    assert result["gate"] is None
    assert not db.exists() and not list(root.iterdir())


def test_db_inside_owned_directory_is_rejected(tmp_path, capsys):
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path)
    new_args = list(argv)
    new_args[new_args.index("--state-db") + 1] = str(root / "artifacts" / f"{uid()}.sqlite")
    assert_refused(module, capsys, new_args)
    assert not db.exists() and not list(root.iterdir())


def test_symlinked_database_parent_rejected(tmp_path, capsys):
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path)
    linked_parent = tmp_path / f"linked_{uid()}"
    try:
        linked_parent.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks unavailable in this environment")
    new_args = list(argv)
    new_args[new_args.index("--state-db") + 1] = str(linked_parent / db.name)
    assert_refused(module, capsys, new_args)
    assert not db.exists() and not list(root.iterdir())


def test_unknown_nested_fields_and_nonfinite_json(tmp_path, capsys):
    module = load_trigger()
    spec, filename, db, root, argv = scenario(tmp_path)
    spec["writes"][0]["extra"] = uid()
    filename.write_text(json.dumps(spec))
    assert_refused(module, capsys, argv)
    assert not db.exists() and not list(root.iterdir())

# Regression tests for conditions that survived the first independent mutation probe.
# Identifiers and filenames come from the scenario; none are fixed application targets.


def test_digest_changes_with_existing_alternate_build_root(tmp_path, capsys):
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path)
    issued = approval(module, capsys, argv)
    alternate = tmp_path / f"alternate_{uid()}"
    alternate.mkdir()
    changed = list(argv)
    changed[changed.index("--build-root") + 1] = str(alternate)
    code, actual = invoke(module, capsys, changed + ["--approve-digest", issued])
    assert code == 2 and actual["gate"] == "not_approved"
    assert actual["approval_digest"] != issued
    assert not db.exists() and not list(root.iterdir()) and not list(alternate.iterdir())


def test_duplicate_json_object_key_rejected_when_last_value_is_valid(tmp_path, capsys):
    module = load_trigger()
    spec, file, db, root, argv = scenario(tmp_path)
    original = json.dumps(spec)
    original_objective = json.dumps(spec["objective"])
    assert original.count('"objective":') == 1
    altered = original.replace('"objective": ' + original_objective,
                               '"objective": "shadow", "objective": ' + original_objective)
    assert json.loads(altered)["objective"] == spec["objective"]
    file.write_text(altered, encoding="utf-8")
    result = assert_refused(module, capsys, argv)
    assert "Duplicate JSON key" in result["error"]
    assert not db.exists() and not list(root.iterdir())


def test_raw_bytes_digest_changes_after_valid_trailing_whitespace(tmp_path, capsys):
    module = load_trigger()
    _, file, db, root, argv = scenario(tmp_path)
    original = file.read_bytes()
    original_digest = hashlib.sha256(original).hexdigest()
    issued = approval(module, capsys, argv)
    file.write_bytes(original + b"\n")
    code, result = invoke(module, capsys, argv + ["--approve-digest", issued])
    assert code == 2 and result["gate"] == "not_approved"
    assert result["spec_sha256"] == hashlib.sha256(original + b"\n").hexdigest()
    assert result["spec_sha256"] != original_digest
    assert not db.exists() and not list(root.iterdir())


def test_size_limit_accepts_valid_exact_boundary_and_rejects_plus_one(tmp_path, capsys):
    module = load_trigger()
    spec, file, db, root, argv = scenario(tmp_path)
    raw = json.dumps(spec).encode("utf-8")
    cap = module._MAX_SPEC_BYTES
    assert len(raw) < cap
    exact = raw + b" " * (cap - len(raw))
    file.write_bytes(exact)
    code, result = invoke(module, capsys, argv)
    assert code == 2 and result["gate"] == "review_required"
    assert result["spec_sha256"] == hashlib.sha256(exact).hexdigest()
    file.write_bytes(exact + b" ")
    refused = assert_refused(module, capsys, argv)
    assert "maximum size" in refused["error"]
    assert not db.exists() and not list(root.iterdir())


def test_cleanup_incomplete_prevents_successful_build_finalization(tmp_path, capsys, monkeypatch):
    import build
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path)
    issued = approval(module, capsys, argv)
    with monkeypatch.context() as patch:
        patch.setattr(build, "_cleanup_owned", lambda path, build_id: ("incomplete", [f"build_tmp/{build_id}"]))
        code, result = invoke(module, capsys, argv + ["--approve-digest", issued])
    assert code == 1 and result["task"]["final"] is False
    assert result["build"] is not None
    assert result["build"]["execution"]["outcome"] == "succeeded"
    assert result["build"]["verification"]["outcome"] == "valid"
    assert result["build"]["cleanup"]["outcome"] == "incomplete"
    scope = argv[argv.index("--scope") + 1]
    assert TaskStore(db, scope=scope).get_task(result["task"]["id"])["final_type"] is None


def test_successful_execution_cannot_have_not_valid_verification_under_schema(tmp_path, capsys):
    from copy import deepcopy
    from output.main import OutputRejected, validate_output
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path)
    issued = approval(module, capsys, argv)
    code, result = invoke(module, capsys, argv + ["--approve-digest", issued])
    assert code == 0
    incompatible = deepcopy(result["build"])
    incompatible["verification"]["outcome"] = "not_valid"
    # The canonical Build schema disallows this combination. A mutant that ignores
    # this condition is observationally equivalent for valid persisted Build records.
    with pytest.raises(OutputRejected):
        validate_output(incompatible)


def test_second_path_recheck_rejects_collision_appearing_after_approval(tmp_path, capsys, monkeypatch):
    module = load_trigger()
    spec, _, db, root, argv = scenario(tmp_path)
    issued = approval(module, capsys, argv)
    candidate = root / "artifacts" / spec["writes"][0]["name"]
    original_match = module._approval_matches

    def changed_after_first_admission(supplied, expected):
        accepted = original_match(supplied, expected)
        if accepted:
            candidate.parent.mkdir()
            candidate.write_text("external collision", encoding="utf-8")
        return accepted

    with monkeypatch.context() as patch:
        patch.setattr(module, "_approval_matches", changed_after_first_admission)
        code, result = invoke(module, capsys, argv + ["--approve-digest", issued])
    assert code == 2 and result["gate"] == "approved_for_apply"
    assert result["state_mutated"] is False and result["task"]["id"] is None
    assert candidate.read_text(encoding="utf-8") == "external collision"
    assert not db.exists() and not (root / "build_tmp").exists()


def test_second_db_recheck_rejects_replay_appearing_after_approval(tmp_path, capsys, monkeypatch):
    module = load_trigger()
    spec, _, db, root, argv = scenario(tmp_path)
    scope = argv[argv.index("--scope") + 1]
    issued = approval(module, capsys, argv)
    original_match = module._approval_matches
    created = []

    def competing_task_after_first_admission(supplied, expected):
        accepted = original_match(supplied, expected)
        if accepted:
            store = TaskStore(db, scope=scope)
            created.append(store.create_task(request_id=spec["request_id"], objective=spec["objective"]))
        return accepted

    with monkeypatch.context() as patch:
        patch.setattr(module, "_approval_matches", competing_task_after_first_admission)
        code, result = invoke(module, capsys, argv + ["--approve-digest", issued])
    assert len(created) == 1
    assert code == 2 and result["gate"] == "approved_for_apply"
    assert result["state_mutated"] is False and result["task"]["id"] is None
    assert TaskStore(db, scope=scope).get_task(created[0]["id"])["revision"] == 0
    assert not list(root.iterdir())


def test_final_readback_mismatch_rejected_after_recorded_build(tmp_path, capsys, monkeypatch):
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path)
    issued = approval(module, capsys, argv)
    with monkeypatch.context() as patch:
        patch.setattr(TaskStore, "get_final", lambda self, task_id: {"not": "persisted result"})
        code, result = invoke(module, capsys, argv + ["--approve-digest", issued])
    assert code == 1 and result["state_mutated"] is True
    assert result["build"] is not None
    assert result["error"] and "RuntimeError" in result["error"]
    scope = argv[argv.index("--scope") + 1]
    store = TaskStore(db, scope=scope)
    assert store.get_final(result["task"]["id"]) == result["build"]


def test_repository_rejections_surface_bounded_error_messages(tmp_path, capsys, monkeypatch):
    from task import TaskRejected
    module = load_trigger()
    spec, file, db, root, argv = scenario(tmp_path)
    spec["plan"]["actions"] = [{"target": spec["writes"][0]["name"]}]
    file.write_text(json.dumps(spec), encoding="utf-8")
    refused = assert_refused(module, capsys, argv)
    assert refused["error"].startswith("OutputRejected: Invalid plan output")
    spec, file, db, root, argv = scenario(tmp_path)
    issued = approval(module, capsys, argv)
    original = TaskStore.save_host_result
    for failing_stage in ("research", "plan"):
        def injected_save(self, *, task_id, expected_revision, value):
            if value["type"] == failing_stage:
                raise TaskRejected("controlled record rejection " + "x" * 250)
            return original(self, task_id=task_id, expected_revision=expected_revision, value=value)
        with monkeypatch.context() as patch:
            patch.setattr(TaskStore, "save_host_result", injected_save)
            code, response = invoke(module, capsys, argv + ["--approve-digest", issued])
        assert code == 1 and response["state_mutated"] is True
        assert response["error"].startswith("TaskRejected: controlled record rejection")
        assert len(response["error"]) <= 200 + len("TaskRejected: ")
        assert response["stages"][failing_stage] == "failed"
        assert response["stages"]["build"] == "not_run"
        if failing_stage == "research":
            assert response["stages"]["plan"] == "not_run"
        else:
            assert response["stages"]["research"] == "completed"
        # Use a newly generated task identity for the next rejection; no replay state reuse.
        if failing_stage == "research":
            spec, file, db, root, argv = scenario(tmp_path)
            issued = approval(module, capsys, argv)


def test_excessive_write_count_rejected_with_matching_plan_targets(tmp_path, capsys):
    from build import MAX_BUILD_FILES
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path, count=MAX_BUILD_FILES + 1)
    result = assert_refused(module, capsys, argv)
    assert "number of bounded writes" in result["error"]
    assert not db.exists() and not list(root.iterdir())


def test_equivalent_path_spellings_produce_same_digest(tmp_path, capsys):
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path)
    first = approval(module, capsys, argv)
    second_argv = list(argv)
    second_argv[second_argv.index("--build-root") + 1] = str(root) + os.sep + "."
    second_argv[second_argv.index("--state-db") + 1] = str(db.parent) + os.sep + "." + os.sep + db.name
    code, response = invoke(module, capsys, second_argv)
    assert code == 2 and response["gate"] == "review_required"
    assert response["approval_digest"] == first
    relative = list(argv)
    relative[relative.index("--build-root") + 1] = os.path.relpath(root, PROJECT)
    relative[relative.index("--state-db") + 1] = os.path.relpath(db, PROJECT)
    code, response = invoke(module, capsys, relative)
    assert code == 2 and response["gate"] == "review_required"
    assert response["approval_digest"] == first


def test_builder_rejection_surfaces_bounded_reason_before_mutation(tmp_path, capsys, monkeypatch):
    from build import BuildRejected
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path)
    with monkeypatch.context() as patch:
        def reject(_name):
            raise BuildRejected("controlled build refusal " + "z" * 250)
        patch.setattr(module, "_safe_filename", reject)
        data = assert_refused(module, capsys, argv)
    assert data["error"].startswith("BuildRejected: controlled build refusal")
    assert len(data["error"]) <= 200 + len("BuildRejected: ")
    assert data["stages"] == {"research": "not_run", "plan": "not_run", "build": "not_run"}
    assert not db.exists() and not list(root.iterdir())

# Admitted-input regression coverage: reject inputs that cannot safely reach
# the existing TaskStore/Builder without modifying state.


def test_unpaired_unicode_surrogate_artifact_name_refused_before_mutation(tmp_path, capsys):
    module = load_trigger()
    spec, run_spec, db, root, argv = scenario(tmp_path)
    invalid_name = f"{uid()}\ud800.txt"
    spec["plan"]["actions"][0]["target"] = invalid_name
    spec["writes"][0]["name"] = invalid_name
    # The file is valid JSON: the unpaired surrogate is escaped in the bytes.
    run_spec.write_text(json.dumps(spec, ensure_ascii=True), encoding="utf-8")
    refusal = assert_refused(module, capsys, argv, gate=None)
    assert "UTF-8" in refusal["error"] or "filename" in refusal["error"].lower()
    assert not db.exists() and not list(root.iterdir())


@pytest.mark.parametrize("device_prefix", ["COM¹", "COM²", "COM³", "LPT¹", "LPT²", "LPT³", "CONIN$", "CONOUT$"])
def test_windows_extended_device_filename_refused_before_mutation(tmp_path, capsys, device_prefix):
    module = load_trigger()
    spec, run_spec, db, root, argv = scenario(tmp_path)
    # Dynamic suffix, while keeping the Windows-reserved base name.
    invalid_name = f"{device_prefix}.{uid()}"
    spec["plan"]["actions"][0]["target"] = invalid_name
    spec["writes"][0]["name"] = invalid_name
    run_spec.write_text(json.dumps(spec), encoding="utf-8")
    assert_refused(module, capsys, argv, gate=None)
    assert not db.exists() and not list(root.iterdir())


@pytest.mark.parametrize("missing_table", ["results", "events", "attempts"])
def test_existing_database_missing_taskstore_table_refused_without_modification(tmp_path, capsys, missing_table):
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path)
    scope = argv[argv.index("--scope") + 1]
    TaskStore(db, scope=scope)
    with sqlite3.connect(db) as conn:
        conn.execute(f"DROP TABLE {missing_table}")
    before = db.read_bytes()
    refusal = assert_refused(module, capsys, argv, gate=None)
    assert "database" in refusal["error"].lower()
    assert db.read_bytes() == before and not list(root.iterdir())
    with sqlite3.connect(db) as conn:
        assert missing_table not in {name for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


@pytest.mark.parametrize("table,missing_column", [
    ("results", "body"), ("events", "detail"), ("attempts", "evidence"),
])
def test_existing_database_missing_taskstore_column_refused_without_modification(
    tmp_path, capsys, table, missing_column
):
    module = load_trigger()
    _, _, db, root, argv = scenario(tmp_path)
    scope = argv[argv.index("--scope") + 1]
    TaskStore(db, scope=scope)
    # Identifiers are a fixed internal fixture selection, not SQL from input.
    with sqlite3.connect(db) as conn:
        conn.execute(f"ALTER TABLE {table} DROP COLUMN {missing_column}")
    before = db.read_bytes()
    assert_refused(module, capsys, argv, gate=None)
    assert db.read_bytes() == before and not list(root.iterdir())
