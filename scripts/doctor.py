from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import sqlite3
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from agent.runtime.loaders import load_app_config, load_selected_provider  # noqa: E402


def check(name, status, detail):
    print(f"{name}: {status} - {detail}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path.cwd())
    a = p.parse_args()
    root = a.root.resolve()
    app = load_app_config(root / "settings/config.yaml")
    provider = load_selected_provider(app, root)
    check("python", "passed", platform.python_version())
    check("pydantic", "passed" if importlib.util.find_spec("pydantic") else "blocked", "import")
    check("provider_sdk", "passed" if importlib.util.find_spec(provider.sdk) else "blocked", provider.sdk)
    key = "passed" if os.getenv(provider.api_key_env) else "not_run"
    check("provider_credentials", key, provider.api_key_env)
    state = os.getenv(app.state.root_env)
    if not state:
        check("state_root", "blocked", app.state.root_env)
        return 1
    target = Path(state)
    target.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(dir=target, delete=True) as fh:
            fh.write(b"probe")
            fh.flush()
            os.fsync(fh.fileno())
        db = sqlite3.connect(target / "doctor.db")
        db.execute("create table if not exists probe(id integer)")
        db.commit()
        db.close()
        check("state_root", "passed", str(target))
    except OSError as exc:
        check("state_root", "blocked", str(exc))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
