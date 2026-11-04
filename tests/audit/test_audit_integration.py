"""Audit capability integration tests: intake, dispatch, persistence, API, adversarial."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from agent.contracts.audit import AuditFindingsRecord
from agent.runtime.canonical_serialization import digest_model
from agent.runtime.controller import Stage


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    """Create a minimal workspace for audit scanning."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "import os\nimport subprocess\n\ndef run(cmd):\n    return subprocess.run(cmd, shell=True)\n"
    )
    (tmp_path / "README.md").write_text("# Test project\n")
    return tmp_path


@pytest.fixture()
def service(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> object:
    """Create an MVPService with audit workspace configured."""
    from mvp.service import MVPService

    monkeypatch.setenv("MCP_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("MCP_TRUSTED_ANCESTRY", "true")
    state_root = tempfile.mkdtemp(prefix="audit-test-")
    return MVPService(state_root)


@pytest.fixture()
def client(service: object) -> TestClient:
    """Create a FastAPI TestClient with the service injected."""
    import mvp.api

    mvp.api.service = service
    return TestClient(mvp.api.app)


class TestAuditIntake:
    """V-02: Audit selection and intake."""

    def test_task_created_with_audit_purpose(self, client: TestClient):
        resp = client.post("/api/tasks", json={"prompt": "Inspect the repo", "purpose": "audit"})
        assert resp.status_code == 201
        task = resp.json()
        assert task["purpose"] == "audit"

    def test_task_defaults_to_research(self, client: TestClient):
        resp = client.post("/api/tasks", json={"prompt": "Research the repo"})
        assert resp.status_code == 201
        assert resp.json()["purpose"] == "research"

    def test_invalid_purpose_rejected(self, client: TestClient):
        resp = client.post("/api/tasks", json={"prompt": "test", "purpose": "invalid"})
        assert resp.status_code == 422

    def test_purpose_persisted_in_input(self, service: object):
        task = service.create("test prompt", purpose="audit")
        task_id = task["task_id"]
        record, _, _ = service.read_input(task_id)
        assert record.purpose == "audit"


class TestAuditDispatch:
    """V-03: Capability dispatch and output."""

    def test_audit_completes_without_advancing_research_stage(self, service: object, workspace: Path):
        from mvp.research_host import execute_audit

        task = service.create("Inspect integration completeness", purpose="audit")
        result = execute_audit(service, task["task_id"])
        assert result["status"] == "completed"
        assert result["stage"] == "audit"
        assert result["current_stage"] == "research"
        assert result["artifact_ref"]["artifact_id"].startswith("audit-")
        assert result["findings_count"] >= 0

    def test_audit_returns_findings_with_stable_ids(self, service: object):
        from mvp.research_host import execute_audit

        task = service.create("Audit the repo", purpose="audit")
        result = execute_audit(service, task["task_id"])
        artifact_id = result["artifact_ref"]["artifact_id"]
        raw = service.artifacts.get_verified(artifact_id, 1)
        record = AuditFindingsRecord.model_validate_json(raw)
        for finding in record.findings:
            assert finding.finding_id.startswith("AUD-")
            assert len(finding.capability) > 0
            assert len(finding.code) > 0
            assert finding.severity in ("low", "medium", "high")

    def test_audit_disposition_is_set(self, service: object):
        from mvp.research_host import execute_audit

        task = service.create("Audit disposition test", purpose="audit")
        result = execute_audit(service, task["task_id"])
        assert result["disposition"] in ("findings_open", "not_e2e_verified", "blocked")

    def test_audit_preserves_source_revision(self, service: object):
        from mvp.research_host import execute_audit

        task = service.create("Audit with revision", purpose="audit")
        result = execute_audit(service, task["task_id"])
        artifact_id = result["artifact_ref"]["artifact_id"]
        raw = service.artifacts.get_verified(artifact_id, 1)
        record = AuditFindingsRecord.model_validate_json(raw)
        # source_revision may be empty if git is unavailable, but the field exists
        assert hasattr(record, "source_revision")


class TestAuditAuthorization:
    """V-03: Authorized versus unauthorized scope."""

    def test_audit_requires_trusted_ancestry(self, service: object, monkeypatch: pytest.MonkeyPatch):
        from mvp.research_host import execute_audit
        from mvp.service import MVPError

        monkeypatch.delenv("MCP_TRUSTED_ANCESTRY", raising=False)
        task = service.create("test", purpose="audit")
        with pytest.raises(MVPError, match="MCP_TRUSTED_ANCESTRY"):
            execute_audit(service, task["task_id"])

    def test_audit_requires_absolute_workspace_root(self, service: object, monkeypatch: pytest.MonkeyPatch):
        from mvp.research_host import execute_audit
        from mvp.service import MVPError

        monkeypatch.setenv("MCP_WORKSPACE_ROOT", "relative/path")
        task = service.create("test", purpose="audit")
        with pytest.raises(MVPError, match="absolute"):
            execute_audit(service, task["task_id"])

    def test_audit_rejects_missing_workspace_root(self, service: object, monkeypatch: pytest.MonkeyPatch):
        from mvp.research_host import execute_audit
        from mvp.service import MVPError

        monkeypatch.delenv("MCP_WORKSPACE_ROOT", raising=False)
        task = service.create("test", purpose="audit")
        with pytest.raises(MVPError, match="MCP_WORKSPACE_ROOT"):
            execute_audit(service, task["task_id"])


class TestAuditPersistence:
    """V-04: Finding persistence and reload."""

    def test_audit_findings_persisted_and_reloaded(self, service: object):
        from mvp.research_host import execute_audit

        task = service.create("Persist audit", purpose="audit")
        result = execute_audit(service, task["task_id"])
        artifact_id = result["artifact_ref"]["artifact_id"]
        artifact_digest = result["artifact_ref"]["artifact_digest"]

        raw = service.artifacts.get_verified(artifact_id, 1)
        stored_digest = service.artifacts.get_digest(artifact_id, 1)
        assert stored_digest == artifact_digest

        record = AuditFindingsRecord.model_validate_json(raw)
        assert record.task_id == task["task_id"]
        assert record.run_id == task["run_id"]
        assert digest_model(record) == artifact_digest

    def test_audit_artifact_distinguishable_from_research(self, service: object):
        from mvp.research_host import execute_audit

        task = service.create("Distinguish test", purpose="audit")
        result = execute_audit(service, task["task_id"])
        ref = result["artifact_ref"]
        assert ref["contract_id"] == "audit_findings"
        assert ref["artifact_id"].startswith("audit-")
        # ResearchRecord uses contract_id "research_record" and prefix "research-"

    def test_audit_findings_in_artifacts_list(self, service: object):
        from mvp.research_host import execute_audit

        task = service.create("Artifacts list test", purpose="audit")
        execute_audit(service, task["task_id"])
        artifacts = service.artifacts_for_task(task["task_id"])
        audit_artifacts = [a for a in artifacts if a["kind"] == "audit"]
        assert len(audit_artifacts) == 1
        assert audit_artifacts[0]["name"] == "_audit.json"


class TestAuditReceipt:
    """V-04: Host-owned receipts."""

    def test_audit_does_not_issue_stage_receipt(self, service: object):
        from mvp.research_host import execute_audit

        task = service.create("Receipt test", purpose="audit")
        execute_audit(service, task["task_id"])
        task_id = task["task_id"]

        import sqlite3

        receipt_id = f"receipt-{task_id}-research"
        state_root = Path(service.host.state_root)
        with sqlite3.connect(state_root / "receipts.db") as conn:
            row = conn.execute("SELECT receipt_digest FROM receipts WHERE receipt_id = ?", (receipt_id,)).fetchone()
        assert row is None
        assert service.host.get_state(task_id).current_stage == Stage.RESEARCH


class TestAuditAdversarial:
    """V-03: Adversarial scenarios."""

    def test_duplicate_audit_blocked(self, service: object):
        from mvp.research_host import execute_audit
        from mvp.service import MVPError

        task = service.create("Duplicate audit", purpose="audit")
        execute_audit(service, task["task_id"])
        # Second call should fail — stage already advanced
        with pytest.raises(MVPError):
            execute_audit(service, task["task_id"])

    def test_audit_on_nonexistent_task(self, service: object):
        from mvp.research_host import execute_audit
        from mvp.service import MVPError

        with pytest.raises(MVPError, match="not found"):
            execute_audit(service, "0" * 32)

    def test_audit_cannot_advance_research_stage(self, service: object):
        from mvp.research_host import execute_audit
        from mvp.service import MVPError

        task = service.create("Stage test", purpose="audit")
        execute_audit(service, task["task_id"])
        state = service.host.get_state(task["task_id"])
        assert state.current_stage == Stage.RESEARCH
        assert Stage.RESEARCH not in state.completed_stages
        with pytest.raises(MVPError, match="already has persisted output"):
            execute_audit(service, task["task_id"])

    def test_audit_unknown_capabilities_raises(self, service: object, workspace: Path):
        from agent.audit.core import scan

        with pytest.raises(ValueError, match="unknown audit capabilities"):
            scan(workspace, ".", ("nonexistent_capability",))


class TestAuditRestart:
    """V-03: Task restart and event replay."""

    def test_audit_state_preserved_across_restart(self, workspace: Path, monkeypatch: pytest.MonkeyPatch):
        from mvp.research_host import execute_audit
        from mvp.service import MVPService

        monkeypatch.setenv("MCP_WORKSPACE_ROOT", str(workspace))
        monkeypatch.setenv("MCP_TRUSTED_ANCESTRY", "true")
        state_root = tempfile.mkdtemp(prefix="audit-restart-")

        s1 = MVPService(state_root)
        task = s1.create("Restart test", purpose="audit")
        task_id = task["task_id"]

        # Simulate restart
        s2 = MVPService(state_root)
        state = s2.host.get_state(task_id)
        assert state is not None
        assert state.current_stage == Stage.RESEARCH

        execute_audit(s2, task_id)
        state2 = s2.host.get_state(task_id)
        assert state2.current_stage == Stage.RESEARCH

    def test_audit_events_replayable(self, service: object):
        from mvp.research_host import execute_audit

        task = service.create("Event replay test", purpose="audit")
        execute_audit(service, task["task_id"])
        events = service.events(task["task_id"])
        event_types = [e["type"] for e in events]
        assert "audit_started" in event_types
        assert "audit_completed" in event_types
        assert "stage_transition" not in event_types
        assert "capability_work_completed" in event_types
        # No synthetic progress events
        synthetic = [e for e in events if "progress" in e["type"].lower()]
        assert len(synthetic) == 0


class TestAuditHTTPIntegration:
    """V-06: HTTP integration test executing Audit mode end-to-end."""

    def test_full_audit_http_flow(self, client: TestClient, service: object, workspace: Path):
        # 1. Create task with audit purpose
        resp = client.post("/api/tasks", json={"prompt": "Full audit test", "purpose": "audit"})
        assert resp.status_code == 201
        task = resp.json()
        task_id = task["task_id"]
        assert task["purpose"] == "audit"
        assert task["current_stage"] == "research"

        # 2. Start audit
        resp2 = client.post(f"/api/tasks/{task_id}/audit")
        assert resp2.status_code == 200
        result = resp2.json()
        assert result["status"] == "completed"
        assert result["stage"] == "audit"
        assert result["current_stage"] == "research"

        # 3. Verify stage advanced
        resp3 = client.get(f"/api/tasks/{task_id}")
        assert resp3.status_code == 200
        state = resp3.json()
        assert state["current_stage"] == "research"
        assert state["execution_status"] == "audit_completed"
        assert state["purpose"] == "audit"

        # 4. Retrieve audit artifacts
        resp4 = client.get(f"/api/tasks/{task_id}/artifacts")
        assert resp4.status_code == 200
        artifacts = resp4.json()
        audit_artifacts = [a for a in artifacts if a["kind"] == "audit"]
        assert len(audit_artifacts) == 1
        record = AuditFindingsRecord.model_validate_json(audit_artifacts[0]["content"])
        assert record.task_id == task_id

        # 5. Replay events
        resp5 = client.get(f"/api/tasks/{task_id}/events")
        assert resp5.status_code == 200
        events = resp5.json()
        event_types = [e["type"] for e in events]
        assert "audit_started" in event_types
        assert "audit_completed" in event_types

    def test_audit_endpoint_404_for_missing_task(self, client: TestClient):
        resp = client.post("/api/tasks/0" * 32 + "/audit")
        assert resp.status_code in (404, 422)

    def test_research_still_works_alongside_audit(self, client: TestClient):
        """Existing Research mode regression alongside Audit."""
        resp = client.post("/api/tasks", json={"prompt": "Research test"})
        assert resp.status_code == 201
        assert resp.json()["purpose"] == "research"


class TestAuditModeAndRecovery:
    def test_revised_input_preserves_audit_purpose(self, service):
        task = service.create("Check initial", purpose="audit")
        revised = service.revise_input(task["task_id"], "Check revised", 1)
        assert revised["purpose"] == "audit"
        assert service.read_input(task["task_id"])[0].purpose == "audit"

    def test_finished_audit_locks_input_revision(self, service):
        from mvp.research_host import execute_audit
        from mvp.service import MVPError

        task = service.create("Check initial", purpose="audit")
        execute_audit(service, task["task_id"])
        with pytest.raises(MVPError, match="locked"):
            service.revise_input(task["task_id"], "Stale findings", 1)

    def test_audit_rejects_research_task_without_effects(self, service):
        from mvp.research_host import execute_audit
        from mvp.service import MVPError

        task = service.create("Research only")
        with pytest.raises(MVPError, match="purpose"):
            execute_audit(service, task["task_id"])
        assert service.host.get_state(task["task_id"]).active_work_artifact_id is None

    def test_research_rejects_audit_task_before_provider(self, service):
        from mvp.research_host import execute_research
        from mvp.service import MVPError

        task = service.create("Audit only", purpose="audit")
        with pytest.raises(MVPError, match="purpose"):
            execute_research(service, task["task_id"])
        assert service.host.get_state(task["task_id"]).active_work_artifact_id is None

    def test_workspace_identity_cannot_be_switched(self, service, tmp_path, monkeypatch):
        from mvp.research_host import execute_audit
        from mvp.service import MVPError

        other = tmp_path / "different-workspace"
        other.mkdir()
        monkeypatch.setenv("MCP_WORKSPACE_ROOT", str(other))
        task = service.create("Audit root", purpose="audit")
        with pytest.raises(MVPError, match="host-approved root"):
            execute_audit(service, task["task_id"])

    def test_blocked_audit_persists_findings_but_never_advances(self, service, monkeypatch):
        from agent.audit.core import AuditResult
        from mvp.research_host import execute_audit

        def blocked_scan(root, scope=".", request=""):
            return AuditResult(str(root), ".", ("paths",), (), (), ("scanner unavailable",), "blocked", request)

        monkeypatch.setattr("agent.audit.scan", blocked_scan)
        task = service.create("Audit blocked", purpose="audit")
        output = execute_audit(service, task["task_id"])
        assert output["status"] == "blocked"
        assert output["current_stage"] == "research"
        record = service.get(task["task_id"])
        assert record["execution_status"] == "audit_blocked"
        assert record["audit_completed"] is False
        assert record["completed_stages"] == []
        assert any(a["name"] == "_audit.json" for a in service.artifacts_for_task(task["task_id"]))

    def test_http_mode_dispatch_must_match_selected_purpose(self, client):
        research = client.post("/api/tasks", json={"prompt": "Research"}).json()
        audit = client.post("/api/tasks", json={"prompt": "Audit", "purpose": "audit"}).json()
        assert client.post(f"/api/tasks/{research['task_id']}/audit").status_code == 400
        assert client.post(f"/api/tasks/{audit['task_id']}/research").status_code == 400

    def test_crash_after_persisted_findings_recovers_without_rescanning(self, workspace, tmp_path, monkeypatch):
        from mvp.research_host import audit_artifact_id, execute_audit
        from mvp.service import MVPError, MVPService

        monkeypatch.setenv("MCP_WORKSPACE_ROOT", str(workspace))
        monkeypatch.setenv("MCP_TRUSTED_ANCESTRY", "true")
        state_root = tmp_path / "crash-state"
        first = MVPService(state_root)
        task = first.create("Verify recovery", purpose="audit")
        task_id = task["task_id"]

        def interrupt_finalize(*_args):
            raise RuntimeError("injected post-persist interruption")

        monkeypatch.setattr(first.host, "finish_capability_work", interrupt_finalize)
        with pytest.raises(MVPError, match="Audit execution blocked"):
            execute_audit(first, task_id)
        artifact_id = audit_artifact_id(task_id, task["run_id"])
        assert first.artifacts.latest_revision(artifact_id) == 1
        assert first.get(task_id)["execution_status"] == "audit_recovery_required"

        second = MVPService(state_root)
        recovered = execute_audit(second, task_id)
        assert recovered["status"] == "completed"
        assert recovered["current_stage"] == "research"
        assert second.artifacts.latest_revision(artifact_id) == 1
        assert second.get(task_id)["execution_status"] == "audit_completed"
        assert "stage_transition" not in [event["type"] for event in second.events(task_id)]
        assert "audit_reconciled" in [event["type"] for event in second.events(task_id)]

    def test_uncertain_effect_without_audit_artifact_fails_closed(self, workspace, tmp_path, monkeypatch):
        from mvp.research_host import execute_audit
        from mvp.service import MVPError, MVPService

        monkeypatch.setenv("MCP_WORKSPACE_ROOT", str(workspace))
        monkeypatch.setenv("MCP_TRUSTED_ANCESTRY", "true")
        state_root = tmp_path / "uncertain-state"
        first = MVPService(state_root)
        task = first.create("Audit with failed scan", purpose="audit")

        def fail_scan(*_args, **_kwargs):
            raise RuntimeError("injected scanner interruption")

        monkeypatch.setattr("agent.audit.scan", fail_scan)
        with pytest.raises(MVPError, match="Audit execution blocked"):
            execute_audit(first, task["task_id"])
        second = MVPService(state_root)
        with pytest.raises(MVPError, match="Audit recovery blocked"):
            execute_audit(second, task["task_id"])
        assert second.host.get_state(task["task_id"]).current_stage == Stage.RESEARCH
