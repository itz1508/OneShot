"""Schema-validated YAML loaders for configuration and stage workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class LoaderError(Exception):
    pass


_STAGE_ROLES = {
    "research": "researcher",
    "audit_discovery": "audit_discovery",
    "planning": "planner",
    "fixture_validation": "fixture_validator",
    "build": "builder",
    "build_validation": "build_verifier",
}


class _UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate keys rather than silently overriding workflow policy."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[str, Any]:
        mapping: dict[str, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise LoaderError("workflow mapping keys must be strings")
            if key in mapping:
                raise LoaderError(f"duplicate workflow mapping key: {key}")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


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


def _check_exchange_schema(schema: object, label: str) -> None:
    """Check schema metadata; actual payload and external-ref validation is host-owned."""
    if not isinstance(schema, dict):
        raise LoaderError(f"{label} must be a JSON Schema mapping")
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise LoaderError(f"{label} must use JSON Schema 2020-12")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        raise LoaderError(f"{label} must be a closed object schema")
    required, properties = schema.get("required"), schema.get("properties")
    if not isinstance(required, list) or not isinstance(properties, dict):
        raise LoaderError(f"{label} must define required and properties")
    if len(required) != len(set(required)) or not all(isinstance(k, str) for k in required):
        raise LoaderError(f"{label} has duplicate or invalid required fields")
    if set(required) - set(properties):
        raise LoaderError(f"{label} requires undeclared properties")
    for field in ("request_id", "request_revision", "task_id", "user_intent_ref"):
        if field not in required:
            raise LoaderError(f"{label} missing request binding: {field}")


def load_stage_workflow(path: str | Path) -> dict[str, Any]:
    """Load a role workflow and reject structural contract/identity drift.

    This checks workflow definitions, not runtime InputRequest/OutputResult
    payloads. Host-side JSON Schema evaluation and trusted $ref resolution
    remain separate responsibilities.
    """
    path = Path(path)
    if not path.exists():
        raise LoaderError(f"workflow file not found: {path}")
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except yaml.YAMLError as e:
        raise LoaderError(f"invalid workflow YAML: {e}") from e
    if not isinstance(data, dict):
        raise LoaderError("workflow must be a mapping")
    stage = data.get("stage")
    if stage not in _STAGE_ROLES or data.get("id") != stage or data.get("version") != 1:
        raise LoaderError("unknown or mismatched workflow stage/id/version")
    workflow = data.get("workflow")
    if not isinstance(workflow, dict):
        raise LoaderError("workflow missing role contract")
    if workflow.get("stage_id") != stage or workflow.get("role_id") != _STAGE_ROLES[stage]:
        raise LoaderError("workflow stage or role does not match registered identity")
    for field in ("input_schema", "output_schema"):
        _check_exchange_schema(workflow.get(field), field)
    output_required = workflow["output_schema"]["required"]
    if "input_request_ref" not in output_required or "status" not in output_required:
        raise LoaderError("output_schema must bind the exact input request and status")
    validation = workflow.get("schema_validation")
    if not isinstance(validation, dict) or validation.get("validator_owner") != "host":
        raise LoaderError("host-owned schema validation is required")
    if validation.get("unresolved_external_ref") != "reject":
        raise LoaderError("unknown schema references must fail closed")
    exchange = workflow.get("request_result_exchange")
    if not isinstance(exchange, dict) or exchange.get("mode") != "bidirectional_request_result":
        raise LoaderError("bidirectional request/result exchange is required")
    inputs = workflow.get("inputs")
    required_inputs = inputs.get("required") if isinstance(inputs, dict) else None
    if not isinstance(required_inputs, list) or not any(
        isinstance(item, dict) and item.get("input_id") == "input_request" for item in required_inputs
    ):
        raise LoaderError("input_request must be declared as a required stage input")
    success = workflow.get("success_contract")
    if not isinstance(success, dict) or success.get("derived_from") != "accepted_user_intent_and_supplied_criteria":
        raise LoaderError("success must be derived from accepted user intent")
    if stage == "research" and success.get("criteria_completeness_gate") is not False:
        raise LoaderError("research must not require criteria completeness")
    if stage == "build" and not exchange.get("build_admission_precedes_execution"):
        raise LoaderError("builder must be admitted before effects")
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
