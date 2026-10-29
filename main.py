"""Operator-gated local trigger for host-authored Research/Plan and bounded Build.

This script does not authenticate an approver, call a model, or grant general Build
permissions. It is deliberately not an installed module or an MCP entrypoint.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any

from build import BuildPolicy, BuildRejected, MAX_ARTIFACT_BYTES, MAX_BUILD_FILES, _safe_filename, run_build
from output.main import OutputRejected, validate_output
from task import TaskRejected, TaskStore

_MAX_SPEC_BYTES = 2 * 1024 * 1024
_NOT_ESTABLISHED = [
    "approver_identity", "source_refs", "research_semantic_correctness",
    "plan_semantic_correctness", "artifact_content_correctness",
    "concurrent_path_identity", "atomic_multi_file_build",
]
_ALLOWED_SPEC = {"request_id", "objective", "research", "plan", "writes"}
_REQUIRED_SPEC = {"request_id", "objective", "plan", "writes"}
_RESTRICTED_WINDOWS = set('<>:"/\\|?*')
_RESERVED_WINDOWS = re.compile(
    r"(?i)^(con|prn|aux|nul|conin\$|conout\$|com[1-9¹²³]|lpt[1-9¹²³])(?:\..*)?$"
)


class AdmissionRejected(ValueError):
    """Invalid or out-of-scope input before the application mutation boundary."""


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise AdmissionRejected(f"Invalid arguments: {message}")

    def exit(self, status: int = 0, message: str | None = None) -> None:
        raise AdmissionRejected(message or "Help is not supported by this JSON-only CLI")


def _parser() -> _ArgumentParser:
    parser = _ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--run-spec", required=True)
    parser.add_argument("--state-db", required=True)
    parser.add_argument("--scope", required=True)
    parser.add_argument("--build-root", required=True)
    parser.add_argument("--approve-digest")
    return parser


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise AdmissionRejected("Duplicate JSON key")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise AdmissionRejected("Nonstandard JSON numeric constant is not permitted")


def _read_spec(filename: str) -> tuple[dict[str, Any], str]:
    with open(filename, "rb") as handle:
        raw = handle.read(_MAX_SPEC_BYTES + 1)
    if len(raw) > _MAX_SPEC_BYTES:
        raise AdmissionRejected("Run specification exceeds maximum size")
    digest = hashlib.sha256(raw).hexdigest()
    document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                          parse_constant=_reject_constant)
    if not isinstance(document, dict) or set(document) - _ALLOWED_SPEC or not _REQUIRED_SPEC <= set(document):
        raise AdmissionRejected("Unexpected or missing run-spec fields")
    for field in ("request_id", "objective"):
        if not isinstance(document[field], str) or not document[field].strip():
            raise AdmissionRejected(f"{field} must be nonempty")
    return document, digest


def _normalized(raw: str) -> Path:
    return Path(os.path.normcase(os.path.realpath(os.path.abspath(raw))))


def _components(path: Path):
    for parent in reversed((path, *path.parents)):
        yield parent


def _no_linked_components(raw: str) -> None:
    original = Path(os.path.abspath(raw))
    for component in _components(original):
        if component.is_symlink() or (hasattr(component, "is_junction") and component.is_junction()):
            raise AdmissionRejected("Linked or junction filesystem path is not permitted")


def _digest(spec_sha256: str, scope: str, state_db: Path, build_root: Path) -> str:
    context = {"spec_sha256": spec_sha256, "scope": scope,
               "state_db": str(state_db), "build_root": str(build_root)}
    encoded = json.dumps(context, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _approval_matches(supplied: str, expected: str) -> bool:
    return hmac.compare_digest(supplied, expected)


def _validate_stages(spec: dict[str, Any]) -> set[str]:
    research = spec.get("research")
    plan = spec["plan"]
    if research is not None:
        validate_output(research)
        if research["type"] != "research" or research["request_id"] != spec["request_id"]:
            raise AdmissionRejected("Research identity does not match run specification")
    validate_output(plan)
    if plan["type"] != "plan" or plan["request_id"] != spec["request_id"]:
        raise AdmissionRejected("Plan identity does not match run specification")
    if research is None:
        if "research_id" in plan or "validation_value_refs" in plan:
            raise AdmissionRejected("Plan has no accompanying Research record")
    else:
        if plan.get("research_id") != research["id"]:
            raise AdmissionRejected("Plan must reference supplied Research ID")
        identifiers = [item["id"] for item in research.get("validation_values", [])]
        if len(identifiers) != len(set(identifiers)):
            raise AdmissionRejected("Duplicate Research validation value ID")
        if not set(plan.get("validation_value_refs", [])).issubset(set(identifiers)):
            raise AdmissionRejected("Plan references an unknown Research validation value")
    targets = {action["target"] for action in plan["actions"] if action.get("target")}
    if not targets:
        raise AdmissionRejected("Plan has no executable targets")
    return targets


def _validate_writes(writes: Any, targets: set[str]) -> list[dict[str, str]]:
    if type(writes) is not list or not 1 <= len(writes) <= MAX_BUILD_FILES:
        raise AdmissionRejected("Invalid number of bounded writes")
    seen: set[str] = set()
    cleaned: list[dict[str, str]] = []
    for item in writes:
        if not isinstance(item, dict) or set(item) != {"name", "content"}:
            raise AdmissionRejected("Each write must contain only name and content")
        name, content = item["name"], item["content"]
        _safe_filename(name)
        # A JSON escaped surrogate can otherwise pass review, then fail only
        # after TaskStore has created state. Reject it before the mutation gate.
        try:
            name.encode("utf-8")
        except UnicodeError as exc:
            raise AdmissionRejected("Artifact filename is not valid UTF-8") from exc
        if (any(c in _RESTRICTED_WINDOWS or ord(c) < 32 for c in name)
                or _RESERVED_WINDOWS.fullmatch(name)):
            raise AdmissionRejected("Filename is incompatible with supported filesystems")
        folded = name.casefold()
        if folded in seen or name not in targets or not isinstance(content, str):
            raise AdmissionRejected("Duplicate, undeclared or invalid write")
        try:
            byte_count = len(content.encode("utf-8"))
        except UnicodeError as exc:
            raise AdmissionRejected("Artifact content is not valid UTF-8") from exc
        if byte_count > MAX_ARTIFACT_BYTES:
            raise AdmissionRejected("Artifact content exceeds bounded size")
        seen.add(folded)
        cleaned.append({"name": name, "content": content})
    return cleaned


def _inspect_paths(db_raw: str, root_raw: str, names: list[str], *, db: Path, root: Path) -> None:
    _no_linked_components(root_raw)
    _no_linked_components(db_raw)
    if not root.is_dir():
        raise AdmissionRejected("Build root must be an existing real directory")
    for sub in ("artifacts", "build_tmp"):
        _no_linked_components(str(root / sub))
        directory = root / sub
        if (directory.exists() or directory.is_symlink()) and not directory.is_dir():
            raise AdmissionRejected("Builder directory is not a real directory")
    artifacts = root / "artifacts"
    scratch = root / "build_tmp"
    if db == root or db == artifacts or db == scratch or db.is_relative_to(scratch) or db.is_relative_to(artifacts):
        raise AdmissionRejected("Database overlaps Builder-owned directories")
    for name in names:
        output = artifacts / name
        if output.exists() or output.is_symlink() or (hasattr(output, "is_junction") and output.is_junction()):
            raise AdmissionRejected("Output artifact already exists")
    if db.exists() and not db.is_file():
        raise AdmissionRejected("Existing database must be a regular file")


# Version-pinned read-only compatibility check for the verified OneShot base,
# not a replacement for TaskStore or a general persistence adapter.
def _check_database(db: Path, scope: str, request_id: str) -> None:
    if not db.exists():
        return
    # Byte 18 identifies the SQLite journal file-format write version (2 == WAL).
    with db.open("rb") as file:
        header = file.read(20)
    if len(header) < 20 or header[:16] != b"SQLite format 3\x00":
        raise AdmissionRejected("Existing database has an incompatible header")
    if header[18] == 2 or header[19] == 2:
        raise AdmissionRejected("WAL-mode databases are outside the read-only admission guarantee")
    conn = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=1)
    try:
        # TaskStore.__init__ uses CREATE TABLE IF NOT EXISTS for four tables.
        # An existing partial schema must be rejected BEFORE construction rather
        # than being silently extended during an approved invocation.
        required_tables = {
            "tasks": {"id", "scope", "request_id", "objective", "revision", "final_type", "final_id"},
            "results": {"scope", "task_id", "type", "id", "body"},
            "events": {"event_id", "scope", "task_id", "revision", "kind", "detail"},
            "attempts": {"id", "scope", "task_id", "plan_id", "temp_name", "state", "evidence"},
        }
        present_tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        for table, required_columns in required_tables.items():
            if table not in present_tables:
                raise AdmissionRejected("Existing database has a missing TaskStore table")
            # Table names are fixed canonical TaskStore schema identifiers, not
            # caller-provided input. Do not accept a view or alternate table.
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if not required_columns <= columns:
                raise AdmissionRejected("Existing database has incompatible TaskStore columns")
        unique = False
        for index in conn.execute("PRAGMA index_list(tasks)"):
            if not index[2] or index[4]:
                continue
            fields = [row[0] for row in conn.execute("SELECT name FROM pragma_index_info(?)", (index[1],))]
            if len(fields) == 2 and set(fields) == {"scope", "request_id"}:
                unique = True
                break
        if not unique:
            raise AdmissionRejected("Missing scoped request identity uniqueness")
        if conn.execute("SELECT 1 FROM tasks WHERE scope=? AND request_id=? LIMIT 1",
                        (scope, request_id)).fetchone():
            raise AdmissionRejected("Request identity already exists in the authorized scope")
    finally:
        conn.close()


def _response() -> dict[str, Any]:
    return {"gate": None, "spec_sha256": None, "approval_digest": None,
            "state_mutated": False,
            "stages": {"research": "not_run", "plan": "not_run", "build": "not_run"},
            "task": {"id": None, "revision": None, "final": False},
            "build": None, "not_established": list(_NOT_ESTABLISHED), "error": None}


def main(argv: list[str] | None = None) -> int:
    response = _response()
    result_code = 2
    store: TaskStore | None = None
    task_id: str | None = None
    attempted_stage: str | None = None
    try:
        args = _parser().parse_args(argv)
        if not args.scope.strip():
            raise AdmissionRejected("Scope must be nonempty")
        if args.approve_digest is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", args.approve_digest):
            raise AdmissionRejected("Approval digest must be 64 hexadecimal characters")
        spec, spec_hash = _read_spec(args.run_spec)
        response["spec_sha256"] = spec_hash
        targets = _validate_stages(spec)
        writes = _validate_writes(spec["writes"], targets)
        db, root = _normalized(args.state_db), _normalized(args.build_root)
        _inspect_paths(args.state_db, args.build_root, [v["name"] for v in writes], db=db, root=root)
        _check_database(db, args.scope, spec["request_id"])
        approval_digest = _digest(spec_hash, args.scope, db, root)
        response["approval_digest"] = approval_digest
        if args.approve_digest is None:
            response["gate"] = "review_required"
            return 2
        if not _approval_matches(args.approve_digest.lower(), approval_digest):
            response["gate"] = "not_approved"
            response["error"] = "Approval digest does not match reviewed input and context"
            return 2
        response["gate"] = "approved_for_apply"
        _inspect_paths(args.state_db, args.build_root, [v["name"] for v in writes], db=db, root=root)
        _check_database(db, args.scope, spec["request_id"])
        # Conservative: the mutation-capable boundary was entered; durable changes
        # are not independently established merely by this flag.
        response["state_mutated"] = True
        result_code = 1
        store = TaskStore(db, scope=args.scope)
        task = store.create_task(request_id=spec["request_id"], objective=spec["objective"])
        task_id = task["id"]
        response["task"].update(id=task_id, revision=task["revision"])
        if task["revision"] != 0:
            raise RuntimeError("Created task was not fresh")
        if spec.get("research") is not None:
            attempted_stage = "research"
            task = store.save_host_result(task_id=task_id, expected_revision=task["revision"],
                                          value=spec["research"])
            response["stages"]["research"] = "completed"
            response["task"]["revision"] = task["revision"]
            attempted_stage = None
        else:
            response["stages"]["research"] = "skipped"
        attempted_stage = "plan"
        task = store.save_host_result(task_id=task_id, expected_revision=task["revision"], value=spec["plan"])
        response["stages"]["plan"] = "completed"
        response["task"]["revision"] = task["revision"]
        attempted_stage = None
        policy = BuildPolicy(root, frozenset({f"{task_id}:{spec['plan']['id']}"}))
        attempted_stage = "build"
        built = run_build(store=store, policy=policy, task_id=task_id,
                          expected_revision=task["revision"], plan_id=spec["plan"]["id"], writes=writes)
        persisted = store.get_result(task_id, "build", built["id"])
        response["build"] = persisted
        if built != persisted:
            raise RuntimeError("Build result and stored result disagree")
        task = store.get_task(task_id)
        response["task"]["revision"] = task["revision"]
        success = (persisted["execution"]["outcome"] == "succeeded"
                   and persisted["verification"]["outcome"] == "valid"
                   and persisted["cleanup"]["outcome"] == "completed")
        response["stages"]["build"] = "completed" if success else "failed"
        attempted_stage = None
        if not success:
            response["error"] = "Recorded Build did not satisfy success and cleanup conditions"
            return 1
        task = store.finish_task(task_id=task_id, expected_revision=task["revision"],
                                 result_type="build", result_id=persisted["id"])
        final = store.get_task(task_id)
        if (final["revision"] != task["revision"] or final["final_type"] != "build"
                or final["final_id"] != persisted["id"] or store.get_final(task_id) != persisted):
            raise RuntimeError("Final task readback does not match persisted Build")
        response["task"].update(revision=final["revision"], final=True)
        result_code = 0
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        if isinstance(exc, (AdmissionRejected, OutputRejected, BuildRejected, TaskRejected)):
            response["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
        else:
            response["error"] = f"{type(exc).__name__}: execution refused or failed"
        result_code = 1 if response["state_mutated"] else 2
        if response["state_mutated"]:
            if attempted_stage is not None:
                response["stages"][attempted_stage] = "failed"
            if store is not None and task_id is not None:
                try:
                    task = store.get_task(task_id)
                    response["task"].update(revision=task["revision"],
                                             final=task["final_type"] is not None)
                except Exception:
                    pass
        return result_code
    finally:
        # One response regardless of admitted, rejected, or handled failure path.
        print(json.dumps(response, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    raise SystemExit(main())
