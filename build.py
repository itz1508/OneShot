"""Bounded deterministic Build: grant-checked artifact writes and owned cleanup.

Not an autonomous agent. The host prepares and approves Plans. No shell commands,
source mutation, endpoint calls, broad filesystem permissions or model inference.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from output.main import validate_output
from task import TaskRejected, TaskStore

MAX_ARTIFACT_BYTES = 128_000
MAX_BUILD_FILES = 8


class BuildRejected(ValueError):
    """Build request does not satisfy its independent authorization boundary."""


@dataclass(frozen=True, slots=True)
class BuildPolicy:
    workspace: Path
    approved_builds: frozenset[str]


def _safe_filename(name: str) -> None:
    if (not isinstance(name, str) or not name or name in (".", "..")
            or len(name) > 120 or any(c in name for c in "/\\:\0\r\n")
            or name.endswith((".", " "))
            or name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", "COM1", "COM2", "LPT1"}):
        raise BuildRejected("Only simple safe artifact filenames are supported")


def _safe_dir(path: Path) -> None:
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise BuildRejected("Linked workspace directories are not permitted")
    if not path.is_dir():
        raise BuildRejected("Required workspace directory is missing")


def _exclusive_bytes(target: Path, content: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(target, flags, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())


def _cleanup_owned(root: Path, build_id: str) -> tuple[str, list[str]]:
    """Remove only the dedicated directory identified by an issued build ID."""
    if not isinstance(build_id, str) or re.fullmatch(r"[0-9a-f]{32}", build_id) is None:
        return "incomplete", ["Invalid internal cleanup identity"]
    staging = root / "build_tmp" / build_id
    try:
        if staging.is_symlink() or (hasattr(staging, "is_junction") and staging.is_junction()):
            raise BuildRejected("Build staging path was replaced by a link")
        if staging.exists():
            _safe_dir(root)
            _safe_dir(root / "build_tmp")
            shutil.rmtree(staging)
        return "completed", []
    except (OSError, BuildRejected) as exc:
        return "incomplete", [f"build_tmp/{build_id}: {type(exc).__name__}"]


def run_build(
    *, store: TaskStore, policy: BuildPolicy, task_id: str,
    expected_revision: int, plan_id: str, writes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Only approved Plan targets can produce new, non-overwriting artifacts."""
    if f"{task_id}:{plan_id}" not in policy.approved_builds:
        raise BuildRejected("No operator-authorized grant for this Plan")
    workspace = Path(policy.workspace)
    _safe_dir(workspace)
    if type(writes) is not list or not 1 <= len(writes) <= MAX_BUILD_FILES:
        raise BuildRejected("Build requires one to eight bounded artifact writes")
    plan = store.get_result(task_id, "plan", plan_id)
    allowed = {a.get("target") for a in plan["actions"] if a.get("target")}
    if not allowed:
        raise BuildRejected("Plan declares no executable artifact targets")
    names: set[str] = set()
    clean_writes: list[tuple[str, bytes]] = []
    for item in writes:
        if not isinstance(item, dict) or set(item) != {"name", "content"}:
            raise BuildRejected("Each write must specify exactly name and content")
        name, content = item["name"], item["content"]
        _safe_filename(name)
        if name not in allowed or name in names or not isinstance(content, str):
            raise BuildRejected("Unapproved, repeated, or invalid artifact write")
        raw = content.encode("utf-8")
        if len(raw) > MAX_ARTIFACT_BYTES:
            raise BuildRejected("Artifact exceeds the bounded size limit")
        names.add(name)
        clean_writes.append((name, raw))
    artifacts = workspace / "artifacts"
    scratch = workspace / "build_tmp"
    for directory in (artifacts, scratch):
        if directory.exists():
            _safe_dir(directory)
        else:
            directory.mkdir(mode=0o700)
    # Do not overwrite a prior output, even after a prior failed attempt.
    if any((artifacts / name).exists() or (artifacts / name).is_symlink() for name, _ in clean_writes):
        raise BuildRejected("Build would overwrite an existing artifact")

    build_id = uuid4().hex
    store.begin_build(task_id=task_id, expected_revision=expected_revision,
                      plan_id=plan_id, build_id=build_id)
    stage = scratch / build_id
    produced: list[str] = []
    hashes: list[str] = []
    execution = "failed"
    verification = "not_verified"
    try:
        stage.mkdir(mode=0o700)
        for name, content in clean_writes:
            _exclusive_bytes(stage / name, content)
            expected_hash = hashlib.sha256(content).hexdigest()
            if hashlib.sha256((stage / name).read_bytes()).hexdigest() != expected_hash:
                raise BuildRejected("Staged artifact verification failed")
            _exclusive_bytes(artifacts / name, content)
            produced.append(f"artifacts/{name}")
            if hashlib.sha256((artifacts / name).read_bytes()).hexdigest() != expected_hash:
                raise BuildRejected("Permanent artifact verification failed")
            hashes.append(f"sha256:{expected_hash}")
        execution, verification = "succeeded", "valid"
    except TimeoutError:
        execution, verification = "timed_out", "not_verified"
    except (KeyboardInterrupt, asyncio.CancelledError):
        execution, verification = "cancelled", "not_verified"
    except (OSError, ValueError, BuildRejected):
        execution = "failed"
        verification = "not_valid" if produced else "not_verified"
    finally:
        # Durable observation precedes cleanup, even for failed execution.
        try:
            store.note_build_evidence(task_id=task_id, build_id=build_id,
                observation={"execution": execution, "verification": verification,
                             "artifact_refs": produced, "evidence_refs": hashes})
        finally:
            # Cleanup remains mandatory even if evidence persistence fails.
            cleanup_outcome, remaining = _cleanup_owned(workspace, build_id)
        result = {
            "type": "build", "id": build_id,
            "request_id": store.get_task(task_id)["request_id"],
            "plan_id": plan_id,
            "execution": {"outcome": execution, "artifact_refs": produced},
            "verification": {"outcome": verification, "evidence_refs": hashes},
            "cleanup": {"outcome": cleanup_outcome, "remaining_refs": remaining},
        }
        validate_output(result)
        store.finish_build(task_id=task_id, build_id=build_id, value=result)
    return result


def reconcile_interrupted_builds(*, store: TaskStore, policy: BuildPolicy) -> list[dict[str, Any]]:
    """Explicit operator recovery; never guesses a terminated worker succeeded."""
    workspace = Path(policy.workspace)
    _safe_dir(workspace)
    scratch = workspace / "build_tmp"
    if scratch.exists():
        _safe_dir(scratch)
    outcomes: list[dict[str, Any]] = []
    for pending in store.pending_builds():
        # Reconciliation is operator-run only after the old worker is stopped.
        state, remaining = _cleanup_owned(workspace, pending["temp_name"])
        observation = pending.get("evidence") or {}
        result = {
            "type": "build", "id": pending["id"],
            "request_id": store.get_task(pending["task_id"])["request_id"],
            "plan_id": pending["plan_id"],
            "execution": {"outcome": "interrupted", "artifact_refs": observation.get("artifact_refs", [])},
            "verification": {"outcome": "not_verified", "evidence_refs": observation.get("evidence_refs", [])},
            "cleanup": {"outcome": state, "remaining_refs": remaining},
        }
        store.finish_build(task_id=pending["task_id"], build_id=pending["id"], value=result)
        outcomes.append(result)
    return outcomes
