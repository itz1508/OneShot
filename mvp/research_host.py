"""Host-owned Research execution and persistence with strict MCP result validation."""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath

from agent.audit.core import Finding as AuditCoreFinding
from agent.contracts.audit import AuditFinding, AuditFindingsRecord
from agent.contracts.common import ArtifactRef
from agent.contracts.research import ResearchRecord
from agent.contracts.work_todo import WorkBinding, WorkStatus
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE, digest_dict, digest_model
from agent.runtime.controller import Stage
from agent.runtime.providers.base import ProviderError, ProviderRequest
from mvp.mcp_research import ResearchMCPOutput, research_artifact_id
from mvp.service import MVPError, MVPService


def configured_evidence_sources() -> dict[str, object] | None:
    """Read host-owned, bounded repository evidence selection from environment.

    The MCP server remains responsible for execution-time filesystem containment.
    Never derive workspace paths from untrusted task text.
    """
    raw = os.environ.get("ONESHOT_RESEARCH_WORKSPACE_PATHS_JSON", "").strip()
    if not raw:
        return None
    if os.environ.get("MCP_TRUSTED_ANCESTRY") != "true":
        raise MVPError("workspace evidence requires MCP_TRUSTED_ANCESTRY=true")
    root = os.environ.get("MCP_WORKSPACE_ROOT", "")
    if not root or not Path(root).is_absolute():
        raise MVPError("workspace evidence requires an absolute MCP_WORKSPACE_ROOT")
    try:
        paths = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise MVPError("invalid ONESHOT_RESEARCH_WORKSPACE_PATHS_JSON") from exc
    if not isinstance(paths, list) or not (1 <= len(paths) <= 32):
        raise MVPError("Research workspace evidence paths must contain 1-32 items")
    for path in paths:
        if (
            not isinstance(path, str)
            or not (1 <= len(path) <= 4096)
            or chr(0) in path
            or "\\" in path
            or path.startswith("/")
            or ":" in path
            or path != PurePosixPath(path).as_posix()
            or any(part in ("", ".", "..") for part in PurePosixPath(path).parts)
        ):
            raise MVPError("Research evidence paths must be safe relative POSIX paths")
    if len(set(paths)) != len(paths):
        raise MVPError("Research evidence paths must be unique")
    return {"workspace_paths": paths, "snapshots": []}


def research_ref(task_id: str, run_id: str, digest: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=research_artifact_id(task_id, run_id),
        artifact_revision=1,
        artifact_digest=digest,
        contract_id="research_record",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )


def audit_artifact_id(task_id: str, run_id: str) -> str:
    """Content-derived identity for audit findings; distinct from research artifacts."""
    identity = digest_dict({"run_id": run_id, "stage": "research", "task_id": task_id, "capability": "audit"})
    return f"audit-{identity[:32]}"


def audit_ref(task_id: str, run_id: str, digest: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=audit_artifact_id(task_id, run_id),
        artifact_revision=1,
        artifact_digest=digest,
        contract_id="audit_findings",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )


def _git_revision(root: Path) -> str:
    """Best-effort source revision capture; empty if git is unavailable."""
    import subprocess

    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        return ""


def _build_finding(f: AuditCoreFinding, root: Path) -> AuditFinding:
    """Convert a core.Finding dataclass to the persisted contract."""
    import hashlib

    identity = "|".join((f.capability, f.path, str(f.line), f.code))
    finding_id = "AUD-" + hashlib.sha256(identity.encode()).hexdigest()[:16]
    return AuditFinding(
        finding_id=finding_id,
        capability=f.capability,
        code=f.code,
        status=f.status,
        severity=f.severity,
        path=f.path,
        line=f.line,
        message=f.message,
        evidence_digest=f.evidence_digest,
    )


def execute_audit(service: MVPService, task_id: str) -> dict[str, object]:
    """Run Audit capability within the existing Research stage admission guard."""
    with service.research_slot(task_id):
        return _execute_audit(service, task_id)


def _execute_audit(service: MVPService, task_id: str) -> dict[str, object]:
    """Host-owned audit dispatch: authorize, scan, persist, receipt, advance."""
    from agent.audit import scan as audit_scan

    state = service.host.get_state(service._check_id(task_id))
    if state is None:
        raise MVPError("task not found")
    if state.current_stage is not Stage.RESEARCH:
        raise MVPError("Research stage is not active")
    if state.active_work_artifact_id is not None:
        raise MVPError("Research already assigned; reconcile host state before retry")

    workspace_root = os.environ.get("MCP_WORKSPACE_ROOT", "")
    if not workspace_root or not Path(workspace_root).is_absolute():
        raise MVPError("Audit requires an absolute MCP_WORKSPACE_ROOT")
    if os.environ.get("MCP_TRUSTED_ANCESTRY") != "true":
        raise MVPError("Audit requires MCP_TRUSTED_ANCESTRY=true")
    root = Path(workspace_root)
    if not root.is_dir():
        raise MVPError("Audit workspace root is not a directory")

    input_record, input_revision, input_digest = service.read_input(task_id)
    input_ref = ArtifactRef(
        artifact_id=f"mvp-input:{task_id}",
        artifact_revision=input_revision,
        artifact_digest=input_digest,
        contract_id="mvp_task_input",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )
    binding = WorkBinding(
        task_id=task_id,
        run_id=state.run_id,
        stage="research",
        request_id=f"audit-{task_id}",
        request_revision=input_revision,
        input_request_ref=input_ref,
    )
    _, todo_ref = service.host.assign_work(
        binding,
        action="Execute Audit capabilities",
        expected_result="AuditFindingsRecord persisted and verified by the host",
    )
    _, running_ref = service.host.work_todos.set_status(todo_ref, "work-1", WorkStatus.RUNNING)
    service.host.event_store.append(task_id, "audit_started", "Invoking audit capabilities")
    try:
        result = audit_scan(root, scope=".", request=input_record.text)
        findings = tuple(_build_finding(f, root) for f in result.findings)
        source_revision = _git_revision(root)
        record = AuditFindingsRecord(
            task_id=task_id,
            run_id=state.run_id,
            stage_revision=1,
            root=result.root,
            scope=result.scope,
            requested_capabilities=result.requested_capabilities,
            executed_capabilities=result.executed_capabilities,
            findings=findings,
            limitations=result.limitations,
            disposition=result.disposition,
            request=result.request,
            source_revision=source_revision,
        )
        record_digest = digest_model(record)
        ref = audit_ref(task_id, state.run_id, record_digest)
        actual_digest = service.artifacts.put_immutable(
            record, ref.artifact_id, ref.artifact_revision, ref.contract_id, ref.contract_version
        )
        if actual_digest != ref.artifact_digest:
            raise ProviderError("persisted Audit digest mismatch")
        _, done_ref = service.host.work_todos.set_status(
            running_ref,
            "work-1",
            WorkStatus.COMPLETED,
            actual_result="AuditFindingsRecord persisted and digest verified",
            evidence_refs=(ref,),
        )
        receipt = service.host.issue_stage_receipt(Stage.RESEARCH, task_id=task_id, run_id=state.run_id)
        advanced = service.host.advance_stage(
            task_id=task_id,
            run_id=state.run_id,
            expected_stage=Stage.RESEARCH,
            completion_receipt_ref=receipt,
            todo_ref=done_ref,
        )
        service.host.event_store.append(task_id, "audit_completed", ref.artifact_id)
        return {
            "task_id": task_id,
            "run_id": state.run_id,
            "status": "completed",
            "stage": "audit",
            "current_stage": advanced.current_stage.value,
            "artifact_ref": ref.model_dump(mode="json"),
            "disposition": result.disposition,
            "findings_count": len(findings),
        }
    except Exception as exc:
        try:
            service.host.work_todos.set_status(
                running_ref, "work-1", WorkStatus.FAILED, actual_result=type(exc).__name__
            )
        except Exception as inner_exc:
            service.host.event_store.append(
                task_id,
                "audit_recovery_required",
                f"Reconcile partial host effects: {type(inner_exc).__name__}",
            )
        service.host.event_store.append(task_id, "audit_failed", type(exc).__name__)
        raise MVPError(f"Audit execution blocked: {type(exc).__name__}") from exc


def execute_research(service: MVPService, task_id: str) -> dict[str, object]:
    """Run Research with a per-task in-process admission guard."""
    with service.research_slot(task_id):
        return _execute_research(service, task_id)


def _execute_research(service: MVPService, task_id: str) -> dict[str, object]:
    """Validate, persist and advance Research through host-owned evidence gates."""
    state = service.host.get_state(service._check_id(task_id))
    if state is None:
        raise MVPError("task not found")
    if state.current_stage is not Stage.RESEARCH:
        raise MVPError("Research stage is not active")
    if state.active_work_artifact_id is not None:
        raise MVPError("Research already assigned; reconcile host state before retry")
    evidence_sources = configured_evidence_sources()
    input_record, input_revision, input_digest = service.read_input(task_id)
    input_ref = ArtifactRef(
        artifact_id=f"mvp-input:{task_id}",
        artifact_revision=input_revision,
        artifact_digest=input_digest,
        contract_id="mvp_task_input",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )
    binding = WorkBinding(
        task_id=task_id,
        run_id=state.run_id,
        stage="research",
        request_id=f"research-{task_id}",
        request_revision=input_revision,
        input_request_ref=input_ref,
    )
    _, todo_ref = service.host.assign_work(
        binding,
        action="Execute verified MCP Research",
        expected_result="ResearchRecord validated and persisted by the host",
    )
    _, running_ref = service.host.work_todos.set_status(todo_ref, "work-1", WorkStatus.RUNNING)
    service.host.event_store.append(task_id, "mcp_research_started", "Invoking oneshot_research")
    try:
        request = ProviderRequest(
            run_id=state.run_id,
            prompt=json.dumps(
                {
                    "task_id": task_id,
                    "stage_payload": {
                        "input_text": input_record.text,
                        "input_digest": input_digest,
                        **({"evidence_sources": evidence_sources} if evidence_sources is not None else {}),
                    },
                },
                separators=(",", ":"),
                sort_keys=True,
            ),
            system_prompt="Research only: return source-grounded findings without implementation decisions.",
        )
        result = service.host.providers.generate("mcp_research", request)
        envelope = ResearchMCPOutput.model_validate_json(result.content)
        artifact = ResearchRecord.model_validate(envelope.artifact)
        if digest_model(artifact) != envelope.artifact_digest:
            raise ProviderError("Research artifact verification mismatch")
        ref = research_ref(task_id, state.run_id, envelope.artifact_digest)
        actual_digest = service.artifacts.put_immutable(
            artifact, ref.artifact_id, ref.artifact_revision, ref.contract_id, ref.contract_version
        )
        if actual_digest != ref.artifact_digest:
            raise ProviderError("persisted Research digest mismatch")
        _, done_ref = service.host.work_todos.set_status(
            running_ref,
            "work-1",
            WorkStatus.COMPLETED,
            actual_result="ResearchRecord persisted and digest verified",
            evidence_refs=(ref,),
        )
        receipt = service.host.issue_stage_receipt(Stage.RESEARCH, task_id=task_id, run_id=state.run_id)
        advanced = service.host.advance_stage(
            task_id=task_id,
            run_id=state.run_id,
            expected_stage=Stage.RESEARCH,
            completion_receipt_ref=receipt,
            todo_ref=done_ref,
        )
        service.host.event_store.append(task_id, "mcp_research_completed", ref.artifact_id)
        return {
            "task_id": task_id,
            "run_id": state.run_id,
            "status": "completed",
            "stage": "research",
            "current_stage": advanced.current_stage.value,
            "artifact_ref": ref.model_dump(mode="json"),
        }
    except Exception as exc:
        try:
            service.host.work_todos.set_status(
                running_ref, "work-1", WorkStatus.FAILED, actual_result=type(exc).__name__
            )
        except Exception as inner_exc:
            service.host.event_store.append(
                task_id,
                "mcp_research_recovery_required",
                f"Reconcile partial host effects: {type(inner_exc).__name__}",
            )
        service.host.event_store.append(task_id, "mcp_research_failed", type(exc).__name__)
        raise MVPError(f"Research execution blocked: {type(exc).__name__}") from exc
