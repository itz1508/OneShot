"""Fail-closed Research output finalization using existing TaskManager persistence.

This is a stage completion boundary, not a second workflow controller or a
research tool. The existing host produces evidence and report content.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.contracts.research_stage import ResearchRecord
from agent.workflows.research_validation import (
    CheckReceipt,
    ResearchValidationError,
    checks_passed,
    inspect_persisted_research,
    load_research_contract,
    sha256,
)


@dataclass(frozen=True)
class ResearchFinalizationResult:
    status: str
    task_id: str
    run_id: str
    revision: int
    checks: tuple[CheckReceipt, ...]
    artifacts: dict[str, dict[str, Any]]
    handoff_ref: str | None = None
    failure: str | None = None

    @property
    def handoff_created(self) -> bool:
        return self.status == "passed" and self.handoff_ref is not None


def _stable_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _stage_root(workspace: Path, record: ResearchRecord) -> Path:
    root = workspace.resolve()
    if workspace.is_symlink():
        raise ResearchValidationError("workspace must not be a symlink")
    target = workspace / record.task_id / "research" / f"revision-{record.revision}"
    for item in (workspace / record.task_id, workspace / record.task_id / "research", target):
        if item.is_symlink():
            raise ResearchValidationError("symlink in task output path")
    resolved = target.resolve()
    if not resolved.is_relative_to(root):
        raise ResearchValidationError("Research target escapes task workspace")
    return target


def _write_or_reconcile(path: Path, payload: bytes) -> None:
    """An interrupted retry may reuse identical bytes, never overwrite others."""
    if path.is_symlink():
        raise ResearchValidationError("artifact symlink not permitted")
    if path.exists():
        if not path.is_file() or path.read_bytes() != payload:
            raise ResearchValidationError(f"artifact differs from retry payload: {path.name}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".pending")
    if temp.exists():
        if temp.is_symlink() or not temp.is_file() or temp.read_bytes() != payload:
            raise ResearchValidationError("unreconciled temporary output")
    else:
        with temp.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            import os
            os.fsync(stream.fileno())
    temp.replace(path)


def _store_metadata(manager: Any, task_id: str, key: str, value: dict[str, Any]) -> None:
    existing = manager.get_task(task_id)
    if existing is None:
        manager.create_task(task_id=task_id, metadata={"revision": 1})
        existing = manager.get_task(task_id)
    if existing is None:
        raise ResearchValidationError("TaskManager did not persist task")
    current = dict(existing.metadata or {})
    if current.get("research_handoff") and key == "research_handoff":
        prior = current["research_handoff"]
        if prior != value:
            raise ResearchValidationError("immutable handoff already exists")
        return
    current[key] = value
    manager.set_task_metadata(task_id, current, if_revision=int(current.get("revision", 1)))


def finalize_research(
    *,
    record: ResearchRecord,
    original_request: str,
    report_text: str,
    workspace: Path,
    contract_path: Path,
    task_manager: Any,
    requested_comparisons: bool = False,
    requested_recommendations: bool = False,
) -> ResearchFinalizationResult:
    """Write, re-read, validate and persist a genuine Research-to-Audit handoff.

    The caller cannot inject validation outcomes or receipts. A handoff is
    created only after the existing TaskManager confirms its persisted state.
    """
    checks: list[CheckReceipt] = []
    artifacts: dict[str, dict[str, Any]] = {}
    try:
        contract = load_research_contract(contract_path)
        if not original_request or not report_text.strip():
            raise ResearchValidationError("request and report must be nonempty")
        if not record.requirements or not record.todos:
            raise ResearchValidationError("requirements and TODOs are mandatory")
        if record.request_digest != sha256(original_request.encode("utf-8")):
            raise ResearchValidationError("request digest does not match trusted original")
        expected = {"request": "research_request.md", "report": "final_report.md", "record": "_research.json"}
        declared = {a.artifact_type: a.relative_path for a in record.artifacts}
        if declared != expected or any(a.revision != record.revision for a in record.artifacts):
            raise ResearchValidationError("artifact paths/revisions do not match contract")
        stage_root = _stage_root(workspace, record)
        if stage_root.is_dir() and (stage_root / "_research.json").is_file():
            prior = task_manager.get_task(record.task_id)
            if prior is not None and (prior.metadata or {}).get("research_handoff"):
                raise ResearchValidationError("validated Research revision is immutable")
        stage_root.mkdir(parents=True, exist_ok=True)
        _write_or_reconcile(stage_root / expected["request"], original_request.encode("utf-8"))
        _write_or_reconcile(stage_root / expected["report"], report_text.encode("utf-8"))
        _write_or_reconcile(stage_root / expected["record"], record.model_dump_json(indent=2).encode("utf-8"))

        restored, checks, artifacts = inspect_persisted_research(
            revision_root=stage_root,
            original_request=original_request,
            contract=contract,
            requested_comparisons=requested_comparisons,
            requested_recommendations=requested_recommendations,
        )
        if restored is None or restored != record or not checks_passed(checks, contract):
            raise ResearchValidationError("independent Research validation failed")

        receipt = {
            "task_id": record.task_id,
            "run_id": record.run_id,
            "research_revision": record.revision,
            "contract_sha256": sha256(contract_path.read_bytes()),
            "checks": [c.__dict__ for c in checks],
            "artifacts": artifacts,
            "target_stage": "audit_discovery",
        }
        receipt_ref = sha256(_stable_json(receipt))
        receipt["receipt_ref"] = receipt_ref
        _store_metadata(task_manager, record.task_id, "research_handoff", receipt)
        persisted = task_manager.get_task(record.task_id)
        if persisted is None or (persisted.metadata or {}).get("research_handoff") != receipt:
            raise ResearchValidationError("TaskManager handoff persistence not verified")
        _, final_checks, final_artifacts = inspect_persisted_research(
            revision_root=stage_root,
            original_request=original_request,
            contract=contract,
            requested_comparisons=requested_comparisons,
            requested_recommendations=requested_recommendations,
        )
        if final_artifacts != artifacts or not checks_passed(final_checks, contract):
            raise ResearchValidationError("Research artifacts changed after persistence")
        return ResearchFinalizationResult("passed", record.task_id, record.run_id, record.revision, tuple(checks), artifacts, receipt_ref)
    except (Exception) as exc:
        # The existing TaskManager retains checkpoint and uncertain side-effects.
        # Never convert a failure into a successful handoff.
        if not isinstance(exc, (ResearchValidationError, OSError, ValueError, KeyError)):
            # Surface unexpected host errors without fabricating completion.
            failure = f"{type(exc).__name__}: {exc}"
        else:
            failure = f"{type(exc).__name__}: {exc}"
        try:
            _store_metadata(task_manager, record.task_id, "research_failure", {
                "revision": record.revision,
                "failure": failure,
                "checkpoint": "finalize_research",
                "retry_disposition": "reconcile_first",
            })
        except Exception:
            # A store failure must remain visible in the returned failure.
            failure += "; TaskManager persistence failed"
        return ResearchFinalizationResult("failed", record.task_id, record.run_id, record.revision, tuple(checks), artifacts, None, failure)
