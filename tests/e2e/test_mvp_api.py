"""FastAPI route smoke tests. Requires optional MVP runtime dependencies."""

import sqlite3

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from mvp.api import app


def test_health_reports_api_and_transport_configuration(monkeypatch):
    monkeypatch.delenv("ONESHOT_MCP_COMMAND", raising=False)
    monkeypatch.delenv("ONESHOT_MCP_URL", raising=False)
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mcp_transport_configured": False}
    monkeypatch.setenv("ONESHOT_MCP_COMMAND", "test-mcp-server")
    assert TestClient(app).get("/api/health").json()["mcp_transport_configured"] is True


def test_invalid_task_does_not_leak_information():
    response = TestClient(app).get("/api/tasks/../../secret")
    assert response.status_code in {400, 404}


def test_deployed_public_mode_disables_research_by_handler(monkeypatch):
    monkeypatch.setenv("ONESHOT_RESEARCH_DISABLED", "true")
    response = TestClient(app).post("/api/tasks/" + "a" * 32 + "/research")
    assert response.status_code == 403
    assert "disabled" in response.json()["detail"].lower()


def test_untrusted_host_header_is_rejected():
    response = TestClient(app, base_url="http://attacker.example").get("/api/health")
    assert response.status_code == 400


def test_real_http_create_restore_and_revision():
    client = TestClient(app)
    created = client.post("/api/tasks", json={"prompt": "Inspect the repository"})
    assert created.status_code == 201
    body = created.json()
    task_id = body["task_id"]
    assert body["current_stage"] == "research"
    assert body["research_completed"] is False

    loaded = client.get(f"/api/tasks/{task_id}")
    assert loaded.status_code == 200
    assert loaded.json() == body
    artifacts = client.get(f"/api/tasks/{task_id}/artifacts").json()
    assert len(artifacts) == 1
    assert artifacts[0]["name"] == "_input.json"
    assert artifacts[0]["revision"] == 1
    assert "Inspect the repository" in artifacts[0]["content"]

    history = client.get(f"/api/tasks/{task_id}/events").json()
    assert history[-1]["type"] == "mvp_research_ready"
    assert client.get(f"/api/tasks/{task_id}/events?after={history[-1]['sequence']}").json() == []

    edit = client.patch(
        f"/api/tasks/{task_id}/input",
        json={"text": "Review the actual source", "expected_revision": 1},
    )
    assert edit.status_code == 200
    assert edit.json()["input_revision"] == 2
    stale = client.patch(
        f"/api/tasks/{task_id}/input",
        json={"text": "Stale revision", "expected_revision": 1},
    )
    assert stale.status_code == 409
    assert client.get(f"/api/tasks/{task_id}").json()["input_text"] == "Review the actual source"


def test_sse_database_error_is_classified_and_does_not_create_fake_events(tmp_path, monkeypatch):
    import mvp.api
    from mvp.service import MVPService

    service = MVPService(tmp_path)
    task_id = service.create("Check SSE recovery")["task_id"]
    original_events = service.events
    recorded_before = original_events(task_id)
    monkeypatch.setattr(mvp.api, "service", service)

    def broken_events(_task_id, _cursor=0):
        raise sqlite3.OperationalError("private database details must not leak")

    monkeypatch.setattr(service, "events", broken_events)
    response = TestClient(mvp.api.app).get(f"/api/tasks/{task_id}/stream")
    assert response.status_code == 200
    assert "event: stream_error\ndata:" in response.text
    assert '"code":"EVENT_READ_FAILED"' in response.text
    assert "private database details" not in response.text
    assert "id:" not in response.text
    assert original_events(task_id) == recorded_before
