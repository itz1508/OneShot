"""Host-owned Research execution and persistence with strict MCP result validation."""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath

from agent.audit.core import Finding as AuditCoreFinding
from agent.contracts.audit import AuditFinding, AuditFindingsRecord
from agent.contracts.common import ArtifactRef
from agent.contracts.host import HostDispatchEnvelope, HostDispatchResult
from agent.contracts.research import ResearchRecord
from agent.contracts.work_todo import WorkBinding, WorkStatus
from agent.runtime.authorization import Capability
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE, digest_dict, digest_model
from agent.runtime.controller import Stage
from agent.runtime.providers.base import ProviderError, ProviderRequest
from agent.runtime.work_todo import WorkTodoManager
from mvp.mcp_research import ResearchMCPOutput, mcp_transport_config, research_artifact_id
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
    """Distinct, stable artifact identity for the selected Research capability."""
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


def _audit_finding(f: AuditCoreFinding) -> AuditFinding:
    import hashlib

    identity = "|".join((f.capability, f.path, str(f.line), f.code))
    return AuditFinding(
        finding_id="AUD-" + hashlib.sha256(identity.encode()).hexdigest()[:16],
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
    """Execute or reconcile a host-admitted Research capability without stage advancement."""
    with service.research_slot(task_id):
        state = service.host.get_state(service._check_id(task_id))
        if state is not None and state.current_stage is Stage.RESEARCH and state.active_work_artifact_id:
            return _reconcile_audit(service, task_id)
        return _execute_audit(service, task_id)


def _reconcile_audit(service: MVPService, task_id: str) -> dict[str, object]:
    """Recover verified, persisted Audit findings without repeating the scanner effect."""
    state = service.host.get_state(task_id)
    if state is None or state.current_stage is not Stage.RESEARCH or not state.active_work_artifact_id:
        raise MVPError("Audit reconciliation requires active Research work")
    input_record, input_revision, input_digest = service.read_input(task_id)
    if input_record.purpose != "audit":
        raise MVPError("task purpose is not audit; Audit reconciliation rejected")
    artifact_id = audit_artifact_id(task_id, state.run_id)
    if service.artifacts.latest_revision(artifact_id) != 1:
        raise MVPError("Audit recovery blocked: verified findings unavailable")
    try:
        raw = service.artifacts.get_verified(artifact_id, 1)
        record = AuditFindingsRecord.model_validate_json(raw)
        if (
            record.task_id != task_id
            or record.run_id != state.run_id
            or record.request != input_record.text
            or record.stage_revision != 1
        ):
            raise ValueError("persisted Audit input or task identity mismatch")
        if (
            service.audit_workspace_root is None
            or record.root != str(service.audit_workspace_root)
            or os.environ.get("MCP_TRUSTED_ANCESTRY") != "true"
        ):
            raise ValueError("persisted Audit scope is not host-authorized")
        if record.disposition == "blocked" or (set(record.executed_capabilities) != set(record.requested_capabilities)):
            raise ValueError("incomplete Audit scanners require explicit correction")
        digest = digest_model(record)
        if service.artifacts.get_digest(artifact_id, 1) != digest:
            raise ValueError("persisted Audit digest mismatch")
        ref = audit_ref(task_id, state.run_id, digest)
        todo_id = state.active_work_artifact_id
        todo_revision = service.artifacts.latest_revision(todo_id)
        todo_digest = service.artifacts.get_digest(todo_id, todo_revision)
        if todo_revision < 1 or not todo_digest:
            raise ValueError("persisted Audit work evidence unavailable")
        todo_ref = WorkTodoManager._ref(todo_id, todo_revision, todo_digest, "work_todo")
        work = service.host.work_todos.read(todo_ref)
        if (
            work.task_id != task_id
            or work.run_id != state.run_id
            or work.stage != Stage.RESEARCH.value
            or work.request_id != f"audit-{task_id}"
            or work.request_revision != input_revision
            or work.input_request_ref.artifact_digest != input_digest
            or len(work.actions) != 1
        ):
            raise ValueError("persisted Audit work binding mismatch")
        action = work.actions[0]
        if action.status is WorkStatus.RUNNING:
            _, todo_ref = service.host.work_todos.set_status(
                todo_ref,
                action.action_id,
                WorkStatus.COMPLETED,
                actual_result="Recovered verified persisted AuditFindingsRecord",
                evidence_refs=(ref,),
            )
        elif action.status is WorkStatus.COMPLETED:
            if ref not in action.evidence_refs:
                raise ValueError("completed Audit work does not cite the persisted findings")
        else:
            raise ValueError("failed or blocked Audit work cannot be automatically retried")
        remaining = service.host.finish_capability_work(task_id, state.run_id, Stage.RESEARCH, todo_ref)
    except Exception as exc:
        service.host.event_store.append(task_id, "audit_recovery_required", type(exc).__name__)
        raise MVPError(f"Audit recovery blocked: {type(exc).__name__}") from exc
    service.host.event_store.append(task_id, "audit_reconciled", artifact_id)
    return {
        "task_id": task_id,
        "run_id": state.run_id,
        "status": "completed",
        "stage": "audit",
        "current_stage": remaining.current_stage.value,
        "artifact_ref": ref.model_dump(mode="json"),
        "disposition": record.disposition,
        "findings_count": len(record.findings),
    }


def _execute_audit(service: MVPService, task_id: str) -> dict[str, object]:
    from agent.audit import scan as audit_scan

    state = service.host.get_state(service._check_id(task_id))
    if state is None:
        raise MVPError("task not found")
    if state.current_stage is not Stage.RESEARCH:
        raise MVPError("Research stage is not active")
    if state.active_work_artifact_id is not None:
        raise MVPError("Research already assigned; reconcile host state before retry")
    input_record, input_revision, input_digest = service.read_input(task_id)
    if input_record.purpose != "audit":
        raise MVPError("task purpose is not audit; Audit dispatch rejected")
    if service.artifacts.latest_revision(audit_artifact_id(task_id, state.run_id)) > 0:
        raise MVPError("Audit already has persisted output; submit a new task for another scan")

    configured_root = os.environ.get("MCP_WORKSPACE_ROOT", "")
    if not configured_root or not Path(configured_root).is_absolute():
        raise MVPError("Audit requires an absolute MCP_WORKSPACE_ROOT")
    if os.environ.get("MCP_TRUSTED_ANCESTRY") != "true":
        raise MVPError("Audit requires MCP_TRUSTED_ANCESTRY=true")
    root = Path(configured_root).resolve()
    if service.audit_workspace_root is None or root != service.audit_workspace_root or not root.is_dir():
        raise MVPError("Audit workspace is not the host-approved root")
    service.host.authorization.authorize_tool("research-audit", Capability.SCANNER, str(root))
    service.host.authorization.check_path_safety(root)

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
        action="Execute read-only Audit capability",
        expected_result="Persist source-grounded AuditFindingsRecord",
    )
    _, running_ref = service.host.work_todos.set_status(todo_ref, "work-1", WorkStatus.RUNNING)
    service.host.event_store.append(task_id, "audit_started", "Invoking read-only Audit scanners")
    try:
        result = audit_scan(root, scope=".", request=input_record.text)
        record = AuditFindingsRecord(
            task_id=task_id,
            run_id=state.run_id,
            stage_revision=1,
            root=result.root,
            scope=result.scope,
            requested_capabilities=result.requested_capabilities,
            executed_capabilities=result.executed_capabilities,
            findings=tuple(_audit_finding(f) for f in result.findings),
            limitations=(*result.limitations, "Source revision not verified by host"),
            disposition=result.disposition,
            request=result.request,
            source_revision="",
        )
        ref = audit_ref(task_id, state.run_id, digest_model(record))
        persisted = service.artifacts.put_immutable(
            record, ref.artifact_id, ref.artifact_revision, ref.contract_id, ref.contract_version
        )
        if persisted != ref.artifact_digest:
            raise ProviderError("persisted Audit digest mismatch")
        # Incomplete scanners cannot complete a capability or the Research stage.
        if record.disposition == "blocked" or (set(record.executed_capabilities) != set(record.requested_capabilities)):
            service.host.work_todos.set_status(
                running_ref,
                "work-1",
                WorkStatus.BLOCKED,
                actual_result="Audit scanners incomplete; review stored findings and limitations",
            )
            service.host.event_store.append(task_id, "audit_blocked", ref.artifact_id)
            return {
                "task_id": task_id,
                "run_id": state.run_id,
                "status": "blocked",
                "stage": "audit",
                "current_stage": state.current_stage.value,
                "artifact_ref": ref.model_dump(mode="json"),
                "disposition": record.disposition,
                "findings_count": len(record.findings),
            }
        _, done_ref = service.host.work_todos.set_status(
            running_ref,
            "work-1",
            WorkStatus.COMPLETED,
            actual_result="AuditFindingsRecord persisted and digest verified",
            evidence_refs=(ref,),
        )
        remaining = service.host.finish_capability_work(task_id, state.run_id, Stage.RESEARCH, done_ref)
        service.host.event_store.append(task_id, "audit_completed", ref.artifact_id)
        return {
            "task_id": task_id,
            "run_id": state.run_id,
            "status": "completed",
            "stage": "audit",
            "current_stage": remaining.current_stage.value,
            "artifact_ref": ref.model_dump(mode="json"),
            "disposition": record.disposition,
            "findings_count": len(record.findings),
        }
    except Exception as exc:
        try:
            service.host.work_todos.set_status(
                running_ref, "work-1", WorkStatus.FAILED, actual_result=type(exc).__name__
            )
        except Exception as recovery_exc:
            service.host.event_store.append(task_id, "audit_recovery_required", type(recovery_exc).__name__)
        service.host.event_store.append(task_id, "audit_failed", type(exc).__name__)
        raise MVPError(f"Audit execution blocked: {type(exc).__name__}") from exc


def execute_research(service: MVPService, task_id: str) -> dict[str, object]:
    """Run Research with a per-task in-process admission guard."""
    with service.research_slot(task_id):
        selected, _, _ = service.read_input(task_id)
        if selected.purpose != "research":
            raise MVPError("task purpose is not research; Research dispatch rejected")
        state = service.host.get_state(service._check_id(task_id))
        if state is not None and state.current_stage is Stage.RESEARCH and state.active_work_artifact_id:
            return _reconcile_research(service, task_id)
        return _execute_research(service, task_id)


def _reconcile_research(service: MVPService, task_id: str) -> dict[str, object]:
    """Resume only if the exact Research output already persisted and can be verified.

    No MCP re-invocation occurs while its side effects are uncertain.
    """
    state = service.host.get_state(task_id)
    if state is None or state.current_stage is not Stage.RESEARCH or not state.active_work_artifact_id:
        raise MVPError("Research reconciliation requires active host work")
    artifact_id = research_artifact_id(task_id, state.run_id)
    if service.artifacts.latest_revision(artifact_id) != 1:
        raise MVPError("Research recovery blocked: upstream effect uncertain; reconcile manually")
    try:
        raw = service.artifacts.get_verified(artifact_id, 1)
        artifact = ResearchRecord.model_validate_json(raw)
        if artifact.task_id != task_id or artifact.run_id != state.run_id:
            raise ValueError("persisted Research identity mismatch")
        digest = digest_model(artifact)
        if service.artifacts.get_digest(artifact_id, 1) != digest:
            raise ValueError("persisted Research digest mismatch")
        ref = research_ref(task_id, state.run_id, digest)
        todo_id = state.active_work_artifact_id
        todo_rev = service.artifacts.latest_revision(todo_id)
        todo_digest = service.artifacts.get_digest(todo_id, todo_rev)
        if todo_rev < 1 or todo_digest is None:
            raise ValueError("work-list evidence unavailable")
        todo_ref = WorkTodoManager._ref(todo_id, todo_rev, todo_digest, "work_todo")
        todo = service.host.work_todos.read(todo_ref)
        input_record, input_revision, input_digest = service.read_input(task_id)
        if (
            todo.task_id != task_id
            or todo.run_id != state.run_id
            or todo.stage != Stage.RESEARCH.value
            or todo.request_id != f"research-{task_id}"
            or todo.request_revision != input_revision
            or todo.input_request_ref.artifact_id != f"mvp-input:{task_id}"
            or todo.input_request_ref.contract_id != "mvp_task_input"
            or todo.input_request_ref.artifact_revision != input_revision
            or todo.input_request_ref.artifact_digest != input_digest
            or input_record.task_id != task_id
            or len(todo.actions) != 1
        ):
            raise ValueError("work assignment or input revision changed")
        dispatch_raw = service.artifacts.get_verified(f"agent-dispatch:{todo.request_id}", todo.request_revision)
        dispatch = HostDispatchEnvelope.model_validate_json(dispatch_raw)
        service.host.verify_agent_dispatch(dispatch)
        if (
            dispatch.input_request_ref != todo.input_request_ref
            or dispatch.request_id != todo.request_id
            or dispatch.request_revision != todo.request_revision
        ):
            raise ValueError("Research dispatch was not host-bound")
        service.host.receive_agent_result(
            dispatch,
            HostDispatchResult(
                task_id=dispatch.task_id,
                run_id=dispatch.run_id,
                stage=dispatch.stage,
                role=dispatch.role,
                request_id=dispatch.request_id,
                request_revision=dispatch.request_revision,
                respond_to=dispatch.respond_to,
                output_ref=ref,
            ),
        )
        action = todo.actions[0]
        if action.status is WorkStatus.RUNNING:
            _, todo_ref = service.host.work_todos.set_status(
                todo_ref,
                action.action_id,
                WorkStatus.COMPLETED,
                actual_result="Recovered persisted ResearchRecord with exact digest",
                evidence_refs=(ref,),
            )
        elif action.status is WorkStatus.COMPLETED:
            if ref not in action.evidence_refs:
                raise ValueError("completed work does not cite persisted Research artifact")
        else:
            raise ValueError("uncertain or terminal work action requires manual reconciliation")
        receipt = service.host.issue_stage_receipt(
            Stage.RESEARCH,
            task_id=task_id,
            run_id=state.run_id,
            artifact_id=artifact_id,
            revision=1,
            artifact_digest=digest,
        )
        advanced = service.host.advance_stage(
            task_id=task_id,
            run_id=state.run_id,
            expected_stage=Stage.RESEARCH,
            completion_receipt_ref=receipt,
            todo_ref=todo_ref,
        )
    except Exception as exc:
        service.host.event_store.append(task_id, "mcp_research_recovery_required", type(exc).__name__)
        raise MVPError(f"Research recovery blocked: {type(exc).__name__}") from exc
    service.host.event_store.append(task_id, "mcp_research_reconciled", artifact_id)
    return {
        "task_id": task_id,
        "run_id": state.run_id,
        "status": "completed",
        "stage": "research",
        "current_stage": advanced.current_stage.value,
        "artifact_ref": ref.model_dump(mode="json"),
    }


def _execute_research(service: MVPService, task_id: str) -> dict[str, object]:
    """Validate, persist and advance Research through host-owned evidence gates."""
    state = service.host.get_state(service._check_id(task_id))
    if state is None:
        raise MVPError("task not found")
    if state.current_stage is not Stage.RESEARCH:
        raise MVPError("Research stage is not active")
    if state.active_work_artifact_id is not None:
        raise MVPError("Research already assigned; reconcile host state before retry")
    try:
        mcp_transport_config()
    except ProviderError as exc:
        raise MVPError(f"Research transport unavailable: {exc}") from exc
    evidence_sources = configured_evidence_sources()
    input_record, input_revision, input_digest = service.read_input(task_id)
    if input_record.purpose != "research":
        raise MVPError("task purpose is not research; Research dispatch rejected")
    input_ref = ArtifactRef(
        artifact_id=f"mvp-input:{task_id}",
        artifact_revision=input_revision,
        artifact_digest=input_digest,
        contract_id="mvp_task_input",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )
    dispatch, _, todo_ref = service.host.prepare_agent_dispatch(
        task_id,
        input_ref,
        input_record.text,
        requested_role="researcher",
        action="Execute verified MCP Research",
        expected_result="ResearchRecord validated and persisted by the host",
    )
    service.host.verify_agent_dispatch(dispatch)
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
                        "routing": {
                            "task_id": dispatch.task_id,
                            "run_id": dispatch.run_id,
                            "request_id": dispatch.request_id,
                            "request_revision": dispatch.request_revision,
                            "respond_to": dispatch.respond_to,
                            "authorized_role": dispatch.role,
                            "stage": dispatch.stage,
                        },
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
        service.host.receive_agent_result(
            dispatch,
            HostDispatchResult(
                task_id=dispatch.task_id,
                run_id=dispatch.run_id,
                stage=dispatch.stage,
                role=dispatch.role,
                request_id=dispatch.request_id,
                request_revision=dispatch.request_revision,
                respond_to=dispatch.respond_to,
                output_ref=ref,
            ),
        )
        _, done_ref = service.host.work_todos.set_status(
            running_ref,
            "work-1",
            WorkStatus.COMPLETED,
            actual_result="ResearchRecord persisted and digest verified",
            evidence_refs=(ref,),
        )
        receipt = service.host.issue_stage_receipt(
            Stage.RESEARCH,
            task_id=task_id,
            run_id=state.run_id,
            artifact_id=ref.artifact_id,
            revision=ref.artifact_revision,
            artifact_digest=ref.artifact_digest,
        )
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
