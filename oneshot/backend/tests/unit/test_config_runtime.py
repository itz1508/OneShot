"""Config resolution + daemon wiring (deployment Phase 1).

Locks the fail-closed precedence documented in ``rsm.config.runtime``:
explicit argument > RSM_CONFIG env > ./rsm.conf.toml > built-in defaults.
"""

from __future__ import annotations

import pytest

from rsm.config import (
    ConfigValidationError,
    RSMConfig,
    get_active_config,
    resolve_config,
)
from rsm.config import runtime as runtime_mod
from rsm.daemon import service as svc


@pytest.fixture(autouse=True)
def _clean_runtime(monkeypatch):
    """Isolate the module-global active config and default daemon per test."""
    monkeypatch.setattr(runtime_mod, "_active", None)
    monkeypatch.setattr(svc, "_default_daemon", None)
    monkeypatch.delenv("RSM_CONFIG", raising=False)


def test_explicit_config_wins_over_env(monkeypatch, tmp_path):
    cfg_file = tmp_path / "rsm.conf.toml"
    cfg_file.write_text('[daemon]\nport = 9001\n', encoding="utf-8")
    monkeypatch.setenv("RSM_CONFIG", str(cfg_file))
    explicit = RSMConfig()
    assert resolve_config(explicit) is explicit


def test_env_var_loads_pointed_file(monkeypatch, tmp_path):
    cfg_file = tmp_path / "custom.toml"
    cfg_file.write_text('[daemon]\nport = 9100\n', encoding="utf-8")
    monkeypatch.setenv("RSM_CONFIG", str(cfg_file))
    assert resolve_config(None).daemon.port == 9100


def test_env_var_missing_file_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("RSM_CONFIG", str(tmp_path / "nope.toml"))
    with pytest.raises(ConfigValidationError):
        resolve_config(None)


def test_env_var_unknown_key_fails_closed(monkeypatch, tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text('[daemon]\nnot_a_key = true\n', encoding="utf-8")
    monkeypatch.setenv("RSM_CONFIG", str(bad))
    with pytest.raises(ConfigValidationError):
        resolve_config(None)


def test_default_file_in_cwd_is_loaded(monkeypatch, tmp_path):
    (tmp_path / "rsm.conf.toml").write_text('[daemon]\nport = 9200\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert resolve_config(None).daemon.port == 9200


def test_builtin_defaults_when_nothing_configured(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # empty dir → no ./rsm.conf.toml
    cfg = resolve_config(None)
    assert cfg.daemon.host == "127.0.0.1"
    assert cfg.daemon.port == 8787
    assert cfg.daemon.allowed_origins == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    assert cfg.persistence.root == "./.rsm-store"


def test_allowed_origins_validation():
    assert RSMConfig.validate_dict(
        {"daemon": {"allowed_origins": ["https://app.example"]}}
    ).daemon.allowed_origins == ["https://app.example"]
    with pytest.raises(ConfigValidationError):
        RSMConfig.validate_dict({"daemon": {"allowed_origins": "not-a-list"}})


def test_get_active_config_defaults_before_wiring():
    assert get_active_config().daemon.port == 8787


def test_daemon_store_root_follows_active_config(tmp_path):
    store_root = tmp_path / "prod-store"
    cfg = RSMConfig.validate_dict({"persistence": {"root": str(store_root)}})
    runtime_mod.set_active_config(cfg)

    daemon = svc.get_daemon()  # _default_daemon is None (fixture)
    assert daemon.store.root == store_root / "buckets"

    # …and it actually persists under the configured root, not ./.rsm-store
    bucket = daemon.ingest_text("wired to config")
    assert (store_root / "buckets" / f"{bucket.bucket_id}.json").is_file()
    assert (store_root / "events.log").is_file()


def test_relative_root_resolves_against_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    cfg = RSMConfig.validate_dict({"persistence": {"root": "./rel-store"}})
    runtime_mod.set_active_config(cfg)
    daemon = svc.get_daemon()
    assert daemon.store.root == (tmp_path / "rel-store" / "buckets").resolve()
