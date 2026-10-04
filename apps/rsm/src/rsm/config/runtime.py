"""Active configuration resolution for the running daemon.

Precedence (fail-closed, first match wins):

1. an explicit ``RSMConfig`` passed to ``create_app(config=...)``
2. the file named by the ``RSM_CONFIG`` environment variable (must exist —
   a broken pointer aborts startup rather than silently falling back)
3. ``./rsm.conf.toml`` in the process working directory (if present)
4. built-in defaults (byte-for-byte the pre-wiring behaviour)

``RSM_CONFIG`` is the only environment variable RSM reads.
"""

from __future__ import annotations

import os
from pathlib import Path

from .loader import load_config
from .schema import RSMConfig

DEFAULT_CONFIG_FILENAME = "rsm.conf.toml"

_active: RSMConfig | None = None


def resolve_config(config: RSMConfig | None = None) -> RSMConfig:
    """Resolve the effective configuration (see module docstring)."""
    if config is not None:
        return config
    env_path = os.environ.get("RSM_CONFIG")
    if env_path:
        return load_config(env_path)
    default = Path(DEFAULT_CONFIG_FILENAME)
    if default.is_file():
        return load_config(default)
    return RSMConfig()


def set_active_config(config: RSMConfig) -> RSMConfig:
    """Install the configuration the running daemon is wired to."""
    global _active
    _active = config
    return config


def get_active_config() -> RSMConfig:
    """Return the active config (defaults before any wiring happened)."""
    global _active
    if _active is None:
        _active = RSMConfig()
    return _active