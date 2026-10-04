"""TOML configuration (stdlib tomllib) with fail-closed validation."""
from .loader import load_config
from .schema import RSMConfig, ConfigValidationError
__all__ = ["load_config", "RSMConfig", "ConfigValidationError"]
