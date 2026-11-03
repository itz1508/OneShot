"""Schema-validated YAML loaders for configuration and workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class LoaderError(Exception):
    pass


def load_config(path: str | Path) -> dict[str, Any]:
    """Load and validate a YAML configuration file."""
    path = Path(path)
    if not path.exists():
        raise LoaderError(f"config file not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise LoaderError(f"config must be a mapping, got {type(data).__name__}")
    return data


def load_stage_workflow(path: str | Path) -> dict[str, Any]:
    """Load a stage workflow YAML. Rejects unknown stage/capability IDs."""
    path = Path(path)
    if not path.exists():
        raise LoaderError(f"workflow file not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise LoaderError("workflow must be a mapping")
    if "stage" not in data:
        raise LoaderError("workflow missing 'stage' key")
    return data


def load_role_policy(path: str | Path) -> dict[str, Any]:
    """Load a role policy YAML."""
    path = Path(path)
    if not path.exists():
        raise LoaderError(f"role policy file not found: {path}")
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise LoaderError("role policy must be a mapping")
    return data


def load_app_config(path: str | Path) -> Any:
    """Load an AppConfig from a YAML file."""
    from agent.contracts.config import AppConfig

    return AppConfig.model_validate(load_config(path))


def load_selected_provider(app: Any, root: str | Path) -> Any:
    """Load the ProviderConfig selected by the AppConfig."""
    from agent.runtime.provider_config import load_provider_config

    root = Path(root)
    provider_path = root / app.provider.profile
    return load_provider_config(provider_path)
