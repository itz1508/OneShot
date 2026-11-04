"""Host-owned Research execution and persistence with strict MCP result validation."""

from __future__ import annotations

import json

from agent.contracts.common import ArtifactRef
from agent.contracts.research import ResearchRecord
from agent.contracts.work_todo import WorkBinding, WorkStatus
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE, digest_model
from agent.runtime.controller import Stage
from agent.runtime.providers.base import ProviderError, ProviderRequest
from mvp.mcp_research import ResearchMCPOutput, register_mcp_research, research_artifact_id
from mvp.service import MVPError, MVPService


def research_ref(task_id: str, run_id: str, digest: str) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=research_artifact_id(task_id, run_id),
        artifact_revision=1,
        artifact_digest=digest,
        contract_id="research_record",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )


def execute_research(service: MVPService, task_id: str) -> dict[str, object]:
    """Execute one real MCP Research call and advance only after verified evidence.

    The host owns CAS work progress, artifact verification, completion receipt,
    and stage advancement. A failed or uncertain attempt never advances.
    """
    state = service.host.get_state(service._check_id(task_id))
    if state is None:
        raise MVPError("task not found")
    if state.current_stage is not Stage.RESEARCH:
        raise MVPError("Research stage is not active")
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
        if "mcp_research" not in service.host.providers.registered_providers:
            register_mcp_research(service.host.providers)
        request = ProviderRequest(
            run_id=state.run_id,
            prompt=json.dumps(
                {
                    "task_id": task_id,
                    "stage_payload": {"input_text": input_record.text, "input_digest": input_digest},
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
        except Exception:
            service.host.event_store.append(task_id, "mcp_research_recovery_required", "Reconcile partial host effects")
        service.host.event_store.append(task_id, "mcp_research_failed", type(exc).__name__)
        raise MVPError(f"Research execution blocked: {type(exc).__name__}") from exc
