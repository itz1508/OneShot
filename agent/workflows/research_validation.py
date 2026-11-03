"""Independent Research completion checks; never trusts model-supplied success."""
from __future__ import annotations

import hashlib
import json
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agent.contracts.research_stage import (
    EvidenceStatus,
    HelpTaskStatus,
    ResearchRecord,
    TodoStatus,
)


@dataclass(frozen=True)
class CheckReceipt:
    check_id: str
    status: str
    observation: str
    evidence_digest: str


class ResearchValidationError(ValueError):
    """A contract, output, or evidence validation cannot be established."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(data: Any) -> bytes:
    return json.dumps(data, sort_keys=True, default=str, separators=(",", ":")).encode()


def load_research_contract(path: Path) -> dict[str, Any]:
    contract = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(contract, dict) or contract.get("id") != "research":
        raise ResearchValidationError("invalid Research workflow contract")
    recovery_path = path.parent / "error_handling.yaml"
    if not recovery_path.is_file():
        raise ResearchValidationError("shared error-handling contract missing")
    recovery = yaml.safe_load(recovery_path.read_text(encoding="utf-8"))
    if recovery.get("id") != contract.get("runtime", {}).get("recovery_handler"):
        raise ResearchValidationError("shared error-handling contract mismatch")
    steps = contract.get("workflow")
    if not isinstance(steps, list) or len(steps) != 13:
        raise ResearchValidationError("Research must declare its 13 stage actions")
    ids = [item.get("id") for item in steps]
    if len(set(ids)) != len(ids):
        raise ResearchValidationError("duplicate Research workflow action")
    known = set(ids)
    produced: set[str] = set()
    for step in steps:
        if step.get("action") != step.get("id"):
            raise ResearchValidationError("action ID and handler must match")
        requires = set(step.get("requires", []))
        if not requires <= known or step["id"] in requires:
            raise ResearchValidationError(f"unknown or circular dependency: {step['id']}")
        if not requires <= produced:
            raise ResearchValidationError(f"out-of-order dependency: {step['id']}")
        if not set(step.get("accepts_skipped_dependencies", [])) <= requires:
            raise ResearchValidationError(f"invalid skipped dependency: {step['id']}")
        produced.add(step["id"])
    checks = contract.get("checks") or {}
    required = contract.get("stage_validation", {}).get("required_checks") or []
    if len(required) != 10 or set(required) != set(checks) or len(set(required)) != 10:
        raise ResearchValidationError("Research checks must be declared exactly once")
    if contract["outputs"]["request"]["filename"] != "research_request.md":
        raise ResearchValidationError("wrong request output name")
    if contract["outputs"]["report"]["filename"] != "final_report.md":
        raise ResearchValidationError("wrong report output name")
    if contract["outputs"]["record"]["filename"] != "_research.json":
        raise ResearchValidationError("wrong Research record output name")
    return contract


def _safe_file(root: Path, relative_path: str, expected: str) -> Path:
    if relative_path != expected:
        raise ResearchValidationError(f"unexpected {expected} path: {relative_path}")
    if root.is_symlink():
        raise ResearchValidationError("symlinked revision directory is not trusted")
    path = root / relative_path
    if path.is_symlink() or path.resolve().parent != root.resolve():
        raise ResearchValidationError("artifact path escapes revision root")
    return path


def inspect_persisted_research(
    *,
    revision_root: Path,
    original_request: str,
    contract: dict[str, Any],
    requested_comparisons: bool = False,
    requested_recommendations: bool = False,
) -> tuple[ResearchRecord | None, list[CheckReceipt], dict[str, dict[str, Any]]]:
    """Read actual files and independently derive every completion check.

    Check receipts derive from inspected bytes or canonical model sections, not
    from user-supplied check flags or synthetic EVD identifiers.
    """
    names = {
        kind: contract["outputs"][kind]["filename"]
        for kind in ("request", "report", "record")
    }
    paths = {kind: _safe_file(revision_root, name, name) for kind, name in names.items()}
    observed: dict[str, dict[str, Any]] = {}
    for kind, path in paths.items():
        if path.is_file():
            raw = path.read_bytes()
            observed[kind] = {"path": str(path), "sha256": sha256(raw), "bytes": len(raw)}
    record: ResearchRecord | None = None
    if "record" in observed:
        with suppress(ValueError, UnicodeError):
            record = ResearchRecord.model_validate_json(paths["record"].read_bytes())

    receipts: dict[str, CheckReceipt] = {}

    def check(check_id: str, passed: bool, observed_value: Any, note: str) -> None:
        proof = _canonical({"check": check_id, "value": observed_value, "passed": passed})
        receipts[check_id] = CheckReceipt(
            check_id, "passed" if passed else "failed", note, sha256(proof)
        )

    request_bytes = paths["request"].read_bytes() if "request" in observed else None
    request_match = request_bytes == original_request.encode("utf-8")
    request_match = (
        request_match
        and record is not None
        and record.request_digest == sha256(original_request.encode("utf-8"))
    )
    check(
        "check_request_preserved",
        request_match,
        {"actual": observed.get("request"),
         "expected_sha256": sha256(original_request.encode("utf-8"))},
        "Request bytes and digest match" if request_match else "Request bytes or digest differ",
    )

    requirements = record.requirements if record else []
    check("check_requirement_coverage", bool(requirements) and all(
        (
            r.evidence_status is EvidenceStatus.UNRESOLVED
            and bool(r.missing_evidence)
            and bool(r.investigation_needed)
        )
        or r.evidence_status is EvidenceStatus.NOT_APPLICABLE
        or (
            r.evidence_status in {
                EvidenceStatus.VERIFIED, EvidenceStatus.SUPPORTED, EvidenceStatus.CONFLICTING
            } and bool(r.finding_ids)
        )
        for r in requirements
    ), [r.model_dump(mode="json") for r in requirements],
        "Requirements have coverage, justified N/A, or an explicit evidence gap")

    trace_ok = record is not None and all(
        (f.evidence_status in {EvidenceStatus.UNRESOLVED, EvidenceStatus.NOT_APPLICABLE})
        or bool(f.source_ids)
        for f in record.findings
    ) and all(
        any(
            r.requirement_id in f.requirement_ids
            for f in record.findings if f.finding_id in r.finding_ids
        )
        for r in requirements if r.finding_ids
    )
    check(
        "check_findings_traceable", trace_ok,
        [(f.finding_id, f.requirement_ids, f.source_ids)
         for f in (record.findings if record else [])],
        "Finding and requirement references are reciprocal",
    )

    help_ok = record is not None and all(
        h.status not in {HelpTaskStatus.PENDING, HelpTaskStatus.RUNNING}
        and (h.status is not HelpTaskStatus.COMPLETED or (h.assessed and bool(h.result_reference)))
        for h in record.help_tasks
    )
    check(
        "check_help_results_assessed", help_ok,
        [(h.help_task_id, str(h.status), h.assessed)
         for h in (record.help_tasks if record else [])],
        "No pending or unassessed help",
    )

    conflicts_ok = record is not None and all(
        f.evidence_status is not EvidenceStatus.CONFLICTING or bool(f.contradictions)
        for f in record.findings
    )
    check(
        "check_conflicts_preserved", conflicts_ok,
        [(f.finding_id, f.contradictions)
         for f in (record.findings if record else [])
         if f.evidence_status is EvidenceStatus.CONFLICTING],
        "Conflicting findings retain competing positions",
    )

    compare_ok = record is not None and (not requested_comparisons or bool(record.comparisons))
    check(
        "check_requested_comparisons", compare_ok,
        [c.model_dump(mode="json") for c in (record.comparisons if record else [])],
        "Requested comparisons present",
    )
    recommend_ok = (
        record is not None
        and (not requested_recommendations or bool(record.recommendations))
    )
    check(
        "check_requested_recommendations", recommend_ok,
        [c.model_dump(mode="json") for c in (record.recommendations if record else [])],
        "Requested recommendations present",
    )

    todo_ok = record is not None and bool(record.todos) and all(
        t.status is TodoStatus.COMPLETED and t.action_check.status.value == "passed"
        and bool(t.evidence_ids) and bool(t.action_check.actual_result)
        for t in record.todos
    )
    check(
        "check_todos_finalized", todo_ok,
        [t.model_dump(mode="json") for t in (record.todos if record else [])],
        "TODOs completed with action-level evidence",
    )

    output_ok = record is not None and set(observed) == {"request", "report", "record"} and all(
        x["bytes"] > 0 and paths[kind].is_file() for kind, x in observed.items()
    ) and {a.artifact_type for a in record.artifacts} == {"request", "report", "record"} and all(
        a.relative_path == names[a.artifact_type] and a.revision == record.revision
        for a in record.artifacts
    )
    check(
        "check_outputs_exist", output_ok, observed,
        "Canonical outputs present and nonempty at the current revision",
    )

    record_ok = (
        record is not None
        and ResearchRecord.model_validate_json(paths["record"].read_bytes()) == record
    )
    check(
        "check_record_valid", record_ok, observed.get("record"),
        "Persisted ResearchRecord validates and round-trips",
    )

    expected = contract["stage_validation"]["required_checks"]
    if len(receipts) != len(expected) or set(receipts) != set(expected):
        raise ResearchValidationError("named check set differs from workflow contract")
    return record, [receipts[key] for key in expected], observed


def checks_passed(checks: list[CheckReceipt], contract: dict[str, Any]) -> bool:
    required = contract["stage_validation"]["required_checks"]
    return len(checks) == len(required) and {c.check_id for c in checks} == set(required) and all(
        c.status == "passed" and bool(c.evidence_digest) for c in checks
    )
