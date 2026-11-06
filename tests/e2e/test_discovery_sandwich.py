"""Contract and Host-backed E2E tests for the Discovery sandwich."""

from pathlib import Path

import pytest

from agent.contracts.common import ArtifactRef
from agent.contracts.discovery_sandwich import DiscoveryPre, InspectionStatus
from agent.contracts.host import HostDispatchResult
from agent.contracts.research import Requirement, ResearchClaim, ResearchRecord
from agent.contracts.work_todo import WorkStatus
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE
from agent.runtime.controller import Stage, TransitionError
from agent.runtime.discovery_sandwich import (
    DiscoveryError,
    DiscoverySandwich,
    inspect_scoped_workspace,
)
from mvp.mcp_research import research_artifact_id
from mvp.research_host import execute_research
from mvp.service import MVPService


def input_ref(service: MVPService, task_id: str) -> ArtifactRef:
    _, rev, digest = service.read_input(task_id)
    return ArtifactRef(
        artifact_id=f"mvp-input:{task_id}",
        artifact_revision=rev,
        artifact_digest=digest,
        contract_id="mvp_task_input",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )


def pre(service: MVPService, task_id: str, root: Path | None = None):
    record, _, _ = service.read_input(task_id)
    assert record.thread_message_id is not None
    return DiscoverySandwich(service.host).pre_scan(
        task_id=task_id,
        thread_message_id=record.thread_message_id,
        input_ref=input_ref(service, task_id),
        user_intent=record.text,
        source=inspect_scoped_workspace(root),
    )


def finish_research(service: MVPService, task_id: str, request_ref: ArtifactRef, question: str):
    host = service.host
    state = host.get_state(task_id)
    assert state is not None
    dispatch, _, todo_ref = host.prepare_agent_dispatch(task_id, request_ref, question, requested_role="researcher")
    record = ResearchRecord(
        task_id=task_id,
        run_id=state.run_id,
        stage_revision=1,
        requirements=(
            Requirement(
                requirement_id="REQ-001",
                source_reference="user",
                original_wording="Integrate leads",
                statement="Integrate incoming leads",
            ),
        ),
        claims=(
            ResearchClaim(
                claim_id="claim-1",
                requirement_ids=("REQ-001",),
                statement="An external service could be used",
                evidence_refs=("EVD-001",),
            ),
        ),
    )
    aid = f"research-output:{task_id}"
    digest = host.artifact_store.put_immutable(record, aid, 1, "research_record", "1.0")
    result_ref = ArtifactRef(
        artifact_id=aid,
        artifact_revision=1,
        artifact_digest=digest,
        contract_id="research_record",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )
    host.receive_agent_result(
        dispatch,
        HostDispatchResult(
            task_id=dispatch.task_id,
            run_id=dispatch.run_id,
            stage=dispatch.stage,
            role=dispatch.role,
            request_id=dispatch.request_id,
            request_revision=dispatch.request_revision,
            respond_to=dispatch.respond_to,
            output_ref=result_ref,
        ),
    )
    _, running = host.work_todos.set_status(todo_ref, "work-1", WorkStatus.RUNNING)
    _, completed = host.work_todos.set_status(
        running,
        "work-1",
        WorkStatus.COMPLETED,
        actual_result="Research artifact persisted",
        evidence_refs=(result_ref,),
    )
    receipt = host.issue_stage_receipt(
        Stage.RESEARCH,
        task_id=task_id,
        run_id=state.run_id,
        artifact_id=result_ref.artifact_id,
        revision=1,
        artifact_digest=digest,
    )
    host.advance_stage(task_id, state.run_id, Stage.RESEARCH, receipt, todo_ref=completed)
    return result_ref


def test_pre_binds_original_message_to_request(tmp_path: Path) -> None:
    service = MVPService(tmp_path)
    task = service.create("Integrate Facebook leads into the existing CRM")
    task_id = str(task["task_id"])
    request, pre_ref, request_ref = pre(service, task_id)
    pre_record = DiscoveryPre.model_validate_json(
        service.artifacts.get_verified(pre_ref.artifact_id, pre_ref.artifact_revision)
    )
    assert request.thread_message_id == task["thread_message_id"]
    assert pre_record.user_intent_ref == input_ref(service, task_id)
    assert "Original user intent: Integrate Facebook leads" in request.information_needed
    assert request_ref.contract_id == "discovery_research_request"
    envelope, _, _ = service.host.prepare_agent_dispatch(
        task_id, request_ref, request.information_needed, requested_role="researcher"
    )
    assert envelope.role == "researcher"
    assert envelope.respond_to == "workflow_entry"


def test_pre_uses_registered_catalog_without_promoting_it_to_evidence(tmp_path: Path) -> None:
    service = MVPService(tmp_path)
    task_id = str(service.create("Add integration")["task_id"])
    request, pre_ref, _ = pre(service, task_id)
    record = DiscoveryPre.model_validate_json(
        service.artifacts.get_verified(pre_ref.artifact_id, pre_ref.artifact_revision)
    )
    assert record.template_id == "SAMPLE-INTEGRATION-001"
    assert record.template_version == "1.0.0"
    assert record.provisional_success_criteria
    assert "Catalog guidance (synthetic)" in request.information_needed


def test_pre_rejects_spoofed_message(tmp_path: Path) -> None:
    service = MVPService(tmp_path)
    task_id = str(service.create("Original intent")["task_id"])
    with pytest.raises(DiscoveryError, match="thread message identity"):
        DiscoverySandwich(service.host).pre_scan(
            task_id=task_id,
            thread_message_id="forged",
            input_ref=input_ref(service, task_id),
            user_intent="Original intent",
            source=inspect_scoped_workspace(None),
        )
    assert service.host.get_state(task_id).active_work_artifact_id is None


def test_pre_rejects_changed_intent(tmp_path: Path) -> None:
    service = MVPService(tmp_path)
    task = service.create("Original intent")
    with pytest.raises(DiscoveryError, match="verified task input"):
        DiscoverySandwich(service.host).pre_scan(
            task_id=str(task["task_id"]),
            thread_message_id=str(task["thread_message_id"]),
            input_ref=input_ref(service, str(task["task_id"])),
            user_intent="Injected requirements",
            source=inspect_scoped_workspace(None),
        )


def test_post_requires_research_completion(tmp_path: Path) -> None:
    service = MVPService(tmp_path)
    task_id = str(service.create("Inspect project")["task_id"])
    _, pre_ref, _ = pre(service, task_id)
    with pytest.raises(TransitionError, match="POST requires active"):
        DiscoverySandwich(service.host).normalize_ingest(
            task_id=task_id,
            pre_ref=pre_ref,
            research_ref=input_ref(service, task_id),
            source=inspect_scoped_workspace(None),
        )


def test_post_preserves_research_and_does_not_advance_audit(tmp_path: Path) -> None:
    service = MVPService(tmp_path)
    task_id = str(service.create("Integrate incoming leads")["task_id"])
    request, pre_ref, request_ref = pre(service, task_id)
    research_ref = finish_research(service, task_id, request_ref, request.information_needed)
    post, post_ref = DiscoverySandwich(service.host).normalize_ingest(
        task_id=task_id,
        pre_ref=pre_ref,
        research_ref=research_ref,
        source=inspect_scoped_workspace(None),
    )
    assert post.requires_audit
    assert post.source_stable
    assert post.research_items[0].repository_applicability == "unassessed"
    assert "Referenced verified evidence is missing" in post.research_items[0].limitations
    assert post_ref.contract_id == "discovery_post"
    service.host._verify_discovery_gate(task_id, service.host.get_state(task_id).run_id)
    assert service.host.get_state(task_id).current_stage is Stage.AUDIT_DISCOVERY


def test_post_detects_source_drift(tmp_path: Path) -> None:
    service = MVPService(tmp_path / "state")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "app.py").write_text("revision = 1\n")
    task_id = str(service.create("Preserve app.py")["task_id"])
    request, pre_ref, request_ref = pre(service, task_id, root)
    research_ref = finish_research(service, task_id, request_ref, request.information_needed)
    (root / "app.py").write_text("revision = 2\n")
    post, _ = DiscoverySandwich(service.host).normalize_ingest(
        task_id=task_id,
        pre_ref=pre_ref,
        research_ref=research_ref,
        source=inspect_scoped_workspace(root),
    )
    assert not post.source_stable
    assert "Repository changed" in post.contradictions[0]
    with pytest.raises(TransitionError, match="POST gate blocked"):
        service.host._verify_discovery_gate(task_id, service.host.get_state(task_id).run_id)


def test_recovered_research_uses_pre_request_binding_and_runs_post(tmp_path: Path) -> None:
    service = MVPService(tmp_path)
    task_id = str(service.create("Research integration changes")["task_id"])
    request, _, request_ref = pre(service, task_id)
    state = service.host.get_state(task_id)
    assert state is not None
    _, _, todo_ref = service.host.prepare_agent_dispatch(
        task_id, request_ref, request.information_needed, requested_role="researcher"
    )
    service.host.work_todos.set_status(todo_ref, "work-1", WorkStatus.RUNNING)
    research = ResearchRecord(
        task_id=task_id,
        run_id=state.run_id,
        stage_revision=1,
        requirements=(
            Requirement(
                requirement_id="REQ-001",
                source_reference="user",
                original_wording="Research integration changes",
                statement="Research integration changes",
            ),
        ),
    )
    service.artifacts.put_immutable(research, research_artifact_id(task_id, state.run_id), 1, "research_record", "1.0")
    outcome = execute_research(service, task_id)
    assert outcome["status"] == "completed"
    assert outcome["discovery_post_status"] == "ready_for_audit"
    assert service.host.get_state(task_id).current_stage is Stage.AUDIT_DISCOVERY
    assert service.artifacts.latest_revision(f"discovery-post:{task_id}") == 1


def test_scoped_scan_skips_symlinks(tmp_path: Path) -> None:
    (tmp_path / "visible.py").write_text("print(1)\n")
    (tmp_path / "alias.py").symlink_to(tmp_path / "visible.py")
    source = inspect_scoped_workspace(tmp_path)
    assert source.status is InspectionStatus.CAPTURED
    assert "visible.py" in source.inspected_paths
    assert "alias.py" not in source.inspected_paths
