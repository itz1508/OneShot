"""TOML configuration (stdlib tomllib) with fail-closed validation."""
from .loader import load_config
from .runtime import get_active_config, resolve_config, set_active_config
from .schema import RSMConfig, ConfigValidationError

__all__ = [
    "load_config",
    "resolve_config",
    "set_active_config",
    "get_active_config",
    "RSMConfig",
    "ConfigValidationError",
]
