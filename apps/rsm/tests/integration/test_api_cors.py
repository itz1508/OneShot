"""CORS contract: the Next.js UI (localhost:3000) must read daemon responses.

Regression guard for GAP-0007 — without these headers every browser fetch
from the UI fails the same-origin policy while the daemon stays green.
"""

from fastapi.testclient import TestClient
from rsm.api.app import create_app


def test_dev_origin_get_is_readable():
    client = TestClient(create_app())
    r = client.get("/healthz", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") in (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )


def test_alternate_dev_origin_get_is_readable():
    client = TestClient(create_app())
    r = client.get("/healthz", headers={"Origin": "http://127.0.0.1:3000"})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://127.0.0.1:3000"


def test_foreign_origin_gets_no_acao_header():
    client = TestClient(create_app())
    r = client.get("/healthz", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_preflight_for_json_post():
    client = TestClient(create_app())
    r = client.options(
        "/v1/buckets/",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
