"""Connector configuration routes: validation, discovery, persistence, and auth."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

import mvp.api
from agent.runtime.providers.base import ProviderError
from mvp.service import MVPService


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ONESHOT_STATE_ROOT", str(tmp_path))
    monkeypatch.setattr(mvp.api, "DEFAULT_ROOT", tmp_path)
    monkeypatch.setattr(mvp.api, "service", MVPService(tmp_path))
    return TestClient(mvp.api.app)


def test_mcp_connect_persists_tools_but_not_bearer_token(client, monkeypatch):
    monkeypatch.setattr(
        "mvp.connector_store.discover_mcp_tools_sync",
        lambda url, bearer_token=None: [
            {"name": "oneshot_research", "description": "Research tool"},
            {"name": "source_lookup", "description": "Lookup source data"},
        ],
    )
    response = client.post(
        "/api/connectors/mcp/connect",
        headers={"X-Operator-Token": ""},
        json={"url": "http://127.0.0.1:9222/mcp", "auth_type": "bearer", "bearer_token": "secret-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "connected"
    assert body["tool_count"] == 2
    assert body["tools"][0]["name"] == "oneshot_research"
    snapshot = client.get("/api/connectors").json()
    assert snapshot["mcp"]["has_bearer_token"] is True
    assert snapshot["mcp"]["url"] == "http://127.0.0.1:9222/mcp"
    assert "secret-token" not in json.dumps(snapshot)


def test_mcp_test_persists_connection_settings(client, monkeypatch):
    monkeypatch.setattr(
        "mvp.connector_store.discover_mcp_tools_sync",
        lambda url, bearer_token=None: [{"name": "oneshot_research", "description": "Research tool"}],
    )
    response = client.post(
        "/api/connectors/mcp/test",
        json={"url": "http://127.0.0.1:9222/mcp", "auth_type": "bearer", "bearer_token": "secret-token"},
    )
    assert response.status_code == 200
    snapshot = client.get("/api/connectors").json()
    assert snapshot["mcp"]["url"] == "http://127.0.0.1:9222/mcp"
    assert snapshot["mcp"]["auth_type"] == "bearer"
    assert snapshot["mcp"]["has_bearer_token"] is True
    assert snapshot["mcp"]["tools"][0]["name"] == "oneshot_research"


def test_mcp_invalid_url_and_missing_bearer_are_rejected(client):
    invalid = client.post(
        "/api/connectors/mcp/connect",
        json={"url": "ftp://example.com", "auth_type": "none", "bearer_token": ""},
    )
    assert invalid.status_code == 400
    missing = client.post(
        "/api/connectors/mcp/connect",
        json={"url": "http://127.0.0.1:9222/mcp", "auth_type": "bearer", "bearer_token": ""},
    )
    assert missing.status_code == 400


def test_mcp_connection_failure_returns_502(client, monkeypatch):
    def broken(*_args, **_kwargs):
        raise ProviderError("connection failed")

    monkeypatch.setattr("mvp.connector_store.discover_mcp_tools_sync", broken)
    response = client.post(
        "/api/connectors/mcp/connect",
        json={"url": "http://127.0.0.1:9222/mcp", "auth_type": "none", "bearer_token": ""},
    )
    assert response.status_code == 502
    assert "connection failed" in response.text


def test_operator_token_gates_connector_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("ONESHOT_STATE_ROOT", str(tmp_path))
    monkeypatch.setenv("ONESHOT_OPERATOR_TOKEN", "operator-secret")
    monkeypatch.setattr(mvp.api, "DEFAULT_ROOT", tmp_path)
    monkeypatch.setattr(mvp.api, "service", MVPService(tmp_path))
    monkeypatch.setattr("mvp.connector_store.discover_mcp_tools_sync", lambda *_args, **_kwargs: [])
    locked = TestClient(mvp.api.app)
    denied = locked.post(
        "/api/connectors/mcp/connect",
        json={"url": "http://127.0.0.1:9222/mcp", "auth_type": "none", "bearer_token": ""},
    )
    assert denied.status_code == 403
    allowed = locked.post(
        "/api/connectors/mcp/connect",
        headers={"X-Operator-Token": "operator-secret"},
        json={"url": "http://127.0.0.1:9222/mcp", "auth_type": "none", "bearer_token": ""},
    )
    assert allowed.status_code == 200


def test_model_save_and_test_persist_non_sensitive_settings(client, monkeypatch):
    monkeypatch.setattr("mvp.connector_store.test_model_provider_sync", lambda *_args: "provider-ready")
    saved = client.post(
        "/api/connectors/model/save",
        json={
            "api_base_url": "http://127.0.0.1:9333/v1",
            "model_id": "test-model",
            "api_key": "model-secret",
        },
    )
    assert saved.status_code == 200
    tested = client.post(
        "/api/connectors/model/test",
        json={
            "api_base_url": "http://127.0.0.1:9333/v1",
            "model_id": "test-model",
            "api_key": "model-secret",
        },
    )
    assert tested.status_code == 200
    assert tested.json()["provider_response"] == "provider-ready"
    snapshot = client.get("/api/connectors").json()
    assert snapshot["model"]["api_base_url"] == "http://127.0.0.1:9333/v1"
    assert snapshot["model"]["model_id"] == "test-model"
    assert snapshot["model"]["has_api_key"] is True
    assert "model-secret" not in json.dumps(snapshot)


def test_model_connection_failure_returns_502(client, monkeypatch):
    monkeypatch.setattr(
        "mvp.connector_store.test_model_provider_sync",
        lambda *_args: (_ for _ in ()).throw(ProviderError("provider unavailable")),
    )
    response = client.post(
        "/api/connectors/model/test",
        json={
            "api_base_url": "http://127.0.0.1:9333/v1",
            "model_id": "test-model",
            "api_key": "model-secret",
        },
    )
    assert response.status_code == 502
    assert "provider unavailable" in response.text
