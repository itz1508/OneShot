"""Host-assigned role dispatch: exact routing, automatic work and return validation."""

from __future__ import annotations

import pytest

from agent.contracts.common import ArtifactRef
from agent.contracts.host import HostDispatchEnvelope, HostDispatchResult
from agent.contracts.research import Requirement, ResearchRecord
from agent.contracts.work_todo import WorkStatus
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE
from agent.runtime.controller import HostController, Stage, TransitionError
from mvp.service import MVPService
from tests.e2e.test_real_workflow import _advance_with_receipt


def _request(service: MVPService, task_id: str) -> ArtifactRef:
    _, revision, digest = service.read_input(task_id)
    return ArtifactRef(
        artifact_id=f"mvp-input:{task_id}",
        artifact_revision=revision,
        artifact_digest=digest,
        contract_id="mvp_task_input",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )


def _research_output(service: MVPService, task_id: str, run_id: str) -> ArtifactRef:
    record = ResearchRecord(
        task_id=task_id,
        run_id=run_id,
        stage_revision=1,
        requirements=(
            Requirement(
                requirement_id="REQ-001",
                source_reference="submitted-task",
                original_wording="Inspect real repository files",
                statement="Inspect real repository files",
            ),
        ),
    )
    digest = service.artifacts.put_immutable(record, f"research-result-{task_id}", 1, "research_record", "1.0")
    return ArtifactRef(
        artifact_id=f"research-result-{task_id}",
        artifact_revision=1,
        artifact_digest=digest,
        contract_id="research_record",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )


def test_host_creates_and_persists_routing_and_todo_before_dispatch(tmp_path) -> None:
    service = MVPService(tmp_path)
    task = service.create("Inspect real repository files")
    task_id = str(task["task_id"])
    envelope, dispatch_ref, todo_ref = service.host.prepare_agent_dispatch(
        task_id, _request(service, task_id), "Inspect real repository files", requested_role="researcher"
    )
    assert envelope.task_id == task_id
    assert envelope.run_id == task["run_id"]
    assert envelope.role == "researcher"
    assert envelope.stage == "research"
    assert envelope.request_id
    assert envelope.request_revision == 1
    assert envelope.respond_to == "workflow_entry"
    assert (
        service.artifacts.get_digest(dispatch_ref.artifact_id, dispatch_ref.artifact_revision)
        == dispatch_ref.artifact_digest
    )
    assert (
        HostDispatchEnvelope.model_validate_json(
            service.artifacts.get_verified(dispatch_ref.artifact_id, dispatch_ref.artifact_revision)
        )
        == envelope
    )
    service.host.verify_agent_dispatch(envelope)
    assert service.host.work_todos.read(todo_ref).actions[0].status is WorkStatus.PENDING
    assert service.host.get_state(task_id).active_work_artifact_id == todo_ref.artifact_id


def test_missing_invalid_and_mismatched_envelopes_rejected(tmp_path) -> None:
    service = MVPService(tmp_path)
    task_id = str(service.create("Inspect real repository files")["task_id"])
    input_ref = _request(service, task_id)
    with pytest.raises(TransitionError, match="incorrect agent role"):
        service.host.prepare_agent_dispatch(task_id, input_ref, "Inspect", requested_role="builder")
    assert any(event["type"] == "agent_dispatch_rejected" for event in service.events(task_id))
    assert service.host.get_state(task_id).current_stage is Stage.RESEARCH
    with pytest.raises(TransitionError, match="Research requester"):
        service.host.prepare_agent_dispatch(task_id, input_ref, "Inspect", requester_role="builder")
    with pytest.raises(TransitionError, match="digest mismatch"):
        service.host.prepare_agent_dispatch(
            task_id, input_ref.model_copy(update={"artifact_digest": "f" * 64}), "Inspect"
        )
    envelope, _, _ = service.host.prepare_agent_dispatch(task_id, input_ref, "Inspect", requested_role="researcher")
    for field, value in (
        ("task_id", "other-task"),
        ("run_id", "other-run"),
        ("role", "builder"),
        ("stage", "build"),
        ("respond_to", "planner"),
        ("request_revision", 4),
    ):
        with pytest.raises(TransitionError):
            service.host.verify_agent_dispatch(envelope.model_copy(update={field: value}))
    with pytest.raises(ValueError):
        HostDispatchEnvelope.model_validate(
            {key: value for key, value in envelope.model_dump(mode="json").items() if key != "respond_to"}
        )


def test_host_return_validates_request_and_output_then_advances(tmp_path) -> None:
    service = MVPService(tmp_path)
    task = service.create("Inspect real repository files")
    task_id = str(task["task_id"])
    envelope, _, todo_ref = service.host.prepare_agent_dispatch(
        task_id, _request(service, task_id), "Inspect real repository files"
    )
    output_ref = _research_output(service, task_id, str(task["run_id"]))
    result = HostDispatchResult(
        task_id=envelope.task_id,
        run_id=envelope.run_id,
        stage=envelope.stage,
        role=envelope.role,
        request_id=envelope.request_id,
        request_revision=envelope.request_revision,
        respond_to=envelope.respond_to,
        output_ref=output_ref,
    )
    for field, value in (
        ("request_id", "wrong-request"),
        ("request_revision", 4),
        ("role", "builder"),
        ("respond_to", "planning"),
    ):
        with pytest.raises(TransitionError, match="routing mismatch"):
            service.host.receive_agent_result(envelope, result.model_copy(update={field: value}))
    with pytest.raises(TransitionError, match="output contract"):
        service.host.receive_agent_result(
            envelope, result.model_copy(update={"output_ref": envelope.input_request_ref})
        )
    returned = service.host.receive_agent_result(envelope, result)
    assert service.artifacts.get_digest(returned.artifact_id, returned.artifact_revision) == returned.artifact_digest
    _, running = service.host.work_todos.set_status(todo_ref, "work-1", WorkStatus.RUNNING)
    _, completed = service.host.work_todos.set_status(
        running, "work-1", WorkStatus.COMPLETED, actual_result="Research persisted", evidence_refs=(output_ref,)
    )
    receipt = service.host.issue_stage_receipt(
        Stage.RESEARCH,
        task_id=task_id,
        run_id=str(task["run_id"]),
        artifact_id=output_ref.artifact_id,
        revision=output_ref.artifact_revision,
        artifact_digest=output_ref.artifact_digest,
    )
    assert (
        service.host.advance_stage(
            task_id, str(task["run_id"]), Stage.RESEARCH, receipt, todo_ref=completed
        ).current_stage
        is Stage.AUDIT_DISCOVERY
    )
    audit, _, audit_todo = service.host.prepare_agent_dispatch(
        task_id, output_ref, "Discover code paths", requested_role="audit_discovery"
    )
    assert audit.role == "audit_discovery"
    assert audit.respond_to == "host_controller"
    assert service.host.work_todos.read(audit_todo).stage == "audit_discovery"
    with pytest.raises(TransitionError, match="incorrect agent role"):
        service.host.prepare_agent_dispatch(task_id, output_ref, "Attempt wrong routing", requested_role="researcher")


def test_build_stage_cannot_be_sent_to_researcher(tmp_path) -> None:
    host = HostController(tmp_path)
    host.init_task("task-001", "run-001")
    for stage in (Stage.RESEARCH, Stage.AUDIT_DISCOVERY, Stage.PLANNING, Stage.FIXTURE_VALIDATION):
        _advance_with_receipt(host, "task-001", "run-001", stage)
    assert host.get_state("task-001").current_stage is Stage.BUILD
    with pytest.raises(TransitionError, match="incorrect agent role"):
        host.prepare_agent_dispatch(
            "task-001",
            ArtifactRef(
                artifact_id="missing",
                artifact_revision=1,
                artifact_digest="f" * 64,
                contract_id="fixture",
                contract_version="1.0",
                serializer_profile=SERIALIZER_PROFILE,
            ),
            "Implement admitted actions",
            requested_role="researcher",
        )
