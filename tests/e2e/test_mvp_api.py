"""FastAPI route smoke tests. Requires optional MVP runtime dependencies."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from mvp.api import app  # noqa: E402


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
