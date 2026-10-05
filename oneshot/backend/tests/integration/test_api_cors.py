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


def test_configured_origin_gets_acao_explicit_config_replaces_dev_defaults():
    """Deployment override (Phase 1): allowed_origins from config, fail-closed."""
    from rsm.config import RSMConfig

    cfg = RSMConfig.validate_dict({"daemon": {"allowed_origins": ["https://app.example"]}})
    client = TestClient(create_app(config=cfg))

    r = client.get("/healthz", headers={"Origin": "https://app.example"})
    assert r.headers.get("access-control-allow-origin") == "https://app.example"

    # explicit config replaces the dev defaults entirely…
    r2 = client.get("/healthz", headers={"Origin": "http://localhost:3000"})
    assert "access-control-allow-origin" not in r2.headers

    # …and foreign origins stay blocked
    r3 = client.get("/healthz", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r3.headers


def test_create_app_reads_rsm_config_env(monkeypatch, tmp_path):
    """RSM_CONFIG (the only env var RSM reads) drives the running app."""
    cfg_file = tmp_path / "rsm.conf.toml"
    cfg_file.write_text('[daemon]\nallowed_origins = ["https://env.example"]\n', encoding="utf-8")
    monkeypatch.setenv("RSM_CONFIG", str(cfg_file))

    client = TestClient(create_app())
    r = client.get("/healthz", headers={"Origin": "https://env.example"})
    assert r.headers.get("access-control-allow-origin") == "https://env.example"
    r2 = client.get("/healthz", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r2.headers
