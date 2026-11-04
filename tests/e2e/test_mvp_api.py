"""FastAPI route smoke tests. Requires optional MVP runtime dependencies."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from mvp.api import app


def test_health_reports_no_fake_execution():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "mcp_connected": False,
        "workflow_execution": "not_started",
    }


def test_invalid_task_does_not_leak_information():
    response = TestClient(app).get("/api/tasks/../../secret")
    assert response.status_code in {400, 404}


def test_real_http_create_restore_and_revision():
    client = TestClient(app)
    created = client.post("/api/tasks", json={"prompt": "Inspect the repository"})
    assert created.status_code == 201
    body = created.json()
    task_id = body["task_id"]
    assert body["current_stage"] == "research"
    assert body["mcp_connected"] is False

    loaded = client.get(f"/api/tasks/{task_id}")
    assert loaded.status_code == 200
    assert loaded.json() == body
    artifacts = client.get(f"/api/tasks/{task_id}/artifacts").json()
    assert len(artifacts) == 1
    assert artifacts[0]["name"] == "_input.json"
    assert artifacts[0]["revision"] == 1
    assert "Inspect the repository" in artifacts[0]["content"]

    history = client.get(f"/api/tasks/{task_id}/events").json()
    assert history[-1]["type"] == "mvp_mcp_unavailable"
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
