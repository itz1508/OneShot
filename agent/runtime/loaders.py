"""Schema-validated YAML loaders for configuration and stage workflows."""

from __future__ import annotations

from collections.abc import Hashable
from pathlib import Path
from typing import Any, cast

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

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        mapping: dict[Hashable, Any] = {}
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


_REQUIRED_HOST_WORKFLOWS = frozenset(
    {
        "run_initialization",
        "runtime_output_allocation",
        "registry_snapshot",
        "provider_session_initialization",
        "stage_output_persistence",
        "stage_transition",
        "scanner_execution",
        "specification_freeze",
        "package_lock",
        "build_admission",
        "build_task_compilation",
        "build_wave_scheduling",
        "batch_preflight",
        "task_preflight",
        "sandbox_creation",
        "source_snapshot_transfer",
        "effect_execution",
        "task_integration",
        "verification_barrier",
        "integrated_source_promotion",
        "run_cleanup",
        "structural_gap_analysis",
    }
)


def load_workflow_bundle(path: str | Path) -> dict[str, Any]:
    """Load and structurally validate the single registered end-to-end YAML contract.

    This verifies workflow metadata only. Host-owned runtime execution, artifact
    bindings, and external JSON Schema references require separate verification.
    """
    path = Path(path)
    if not path.exists():
        raise LoaderError(f"workflow contract file not found: {path}")
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except yaml.YAMLError as e:
        raise LoaderError(f"invalid workflow YAML: {e}") from e
    if not isinstance(data, dict):
        raise LoaderError("workflow bundle must be a mapping")

    bundle = data.get("bundle")
    roles = data.get("role_workflows")
    hosts = data.get("host_workflows")
    execution = data.get("execution")
    if (
        not isinstance(bundle, dict)
        or not isinstance(roles, dict)
        or not isinstance(hosts, dict)
        or not isinstance(execution, dict)
    ):
        raise LoaderError("single workflow contract requires bundle, role_workflows, host_workflows, execution")

    if bundle.get("bundle_id") != "oneshot_end_to_end":
        raise LoaderError("unknown end-to-end bundle identity")
    if bundle.get("role_guidance_root") != ".agents/reference":
        raise LoaderError("role guidance must reside under .agents/reference")
    if bundle.get("pre_scanner_gate") != "structural_gap_analysis":
        raise LoaderError("structural gap analysis must gate the scanner")

    tracking = bundle.get("work_tracking")
    if not isinstance(tracking, dict):
        raise LoaderError("host work tracking contract missing")
    required_tracking = {
        "owner": "host_controller",
        "todo_contract_id": "work_todo",
        "plan_contract_id": "work_plan",
        "source_request_binding": "exact_artifact_ref",
        "simple_generation": "automatic_single",
        "complex_generation": "plan_derived",
        "persistence": "artifact_store",
        "progress_revisions": "compare_and_swap",
        "events": "event_store",
        "transition_gate": "completed_with_persisted_evidence",
        "final_stage_gate": "verified_completion_receipt_and_todo",
        "effect_authorization": "none",
    }
    if any(tracking.get(k) != v for k, v in required_tracking.items()):
        raise LoaderError("host-owned work tracking contract invalid")
    if tracking.get("tracked_roles") != list(_STAGE_ROLES):
        raise LoaderError("work tracking must cover all six agent roles")

    expected_roles = list(_STAGE_ROLES)
    if bundle.get("role_order") != expected_roles or set(roles) != set(expected_roles):
        raise LoaderError("workflow stage order or membership does not match registered roles")
    for stage, expected_role in _STAGE_ROLES.items():
        role = roles[stage]
        if not isinstance(role, dict):
            raise LoaderError(f"{stage}: workflow must be a mapping")
        workflow = role.get("workflow")
        if (
            role.get("stage") != stage
            or role.get("id") != stage
            or role.get("version") != 1
            or not isinstance(workflow, dict)
            or workflow.get("stage_id") != stage
            or workflow.get("role_id") != expected_role
        ):
            raise LoaderError(f"{stage}: identity or version mismatch")
        for name in ("input_schema", "output_schema"):
            _check_exchange_schema(workflow.get(name), f"{stage}.{name}")
        if not {"input_request_ref", "status"} <= set(workflow["output_schema"]["required"]):
            raise LoaderError(f"{stage}: output must bind the exact input request and status")
        validation = workflow.get("schema_validation")
        exchange = workflow.get("request_result_exchange")
        inputs = workflow.get("inputs")
        success = workflow.get("success_contract")
        if not isinstance(validation, dict) or validation.get("validator_owner") != "host":
            raise LoaderError(f"{stage}: host-owned schema validation required")
        if validation.get("unresolved_external_ref") != "reject":
            raise LoaderError(f"{stage}: unresolved contract references must be rejected")
        if not isinstance(exchange, dict) or exchange.get("mode") != "bidirectional_request_result":
            raise LoaderError(f"{stage}: bidirectional request/result exchange required")
        required_inputs = inputs.get("required") if isinstance(inputs, dict) else None
        if not isinstance(required_inputs, list) or not any(
            isinstance(item, dict) and item.get("input_id") == "input_request" for item in required_inputs
        ):
            raise LoaderError(f"{stage}: required input_request missing")
        if not isinstance(success, dict) or success.get("derived_from") != "accepted_user_intent_and_supplied_criteria":
            raise LoaderError(f"{stage}: success must derive from user intent")
        if stage == "research" and success.get("criteria_completeness_gate") is not False:
            raise LoaderError("research cannot use criteria completeness as a gate")
        if stage == "build" and not exchange.get("build_admission_precedes_execution"):
            raise LoaderError("builder must be admitted before effects")

    if set(hosts) != _REQUIRED_HOST_WORKFLOWS:
        missing = sorted(_REQUIRED_HOST_WORKFLOWS - set(hosts))
        extra = sorted(set(hosts) - _REQUIRED_HOST_WORKFLOWS)
        raise LoaderError(f"host workflow registry differs: missing={missing}, extra={extra}")
    for host_id, workflow in hosts.items():
        if not isinstance(workflow, dict) or workflow.get("workflow_id") != host_id or not workflow.get("owner"):
            raise LoaderError(f"{host_id}: missing host workflow identity or owner")

    gap = hosts["structural_gap_analysis"]
    expected_gap_inputs = {
        "candidate_specification",
        "workflow_contract_bundle",
        "registry_snapshot_set",
        "workflow_trace",
        "concern_matrix",
        "gap_backtest_corpus",
        "source_grounded_analysis",
        "comparable_system_analysis",
    }
    if set(gap.get("input_contracts", ())) != expected_gap_inputs:
        raise LoaderError("structural gap analysis inputs are incomplete")
    expected_passes = {
        "validate_reference_closure",
        "validate_execution_trace",
        "validate_concern_coverage",
        "run_historical_backtest",
        "run_walking_skeleton",
        "perform_source_grounded_gap_analysis",
        "perform_comparable_system_analysis",
        "persist_analysis",
    }
    if set(gap.get("required_work", ())) != expected_passes:
        raise LoaderError("structural gap analysis passes are incomplete")
    if gap.get("completion", {}).get("walking_skeleton_completed") is not True:
        raise LoaderError("walking skeleton must be verified")
    if gap.get("completion", {}).get("known_critical_gap_detection_rate") != 1.0:
        raise LoaderError("known critical backtest detection must be complete")
    gap_completion = gap.get("completion", {})
    if gap_completion.get("successful_result") != {
        "execution_status": "completed",
        "diagnostic_status": "valid",
    }:
        raise LoaderError("structural gap successful result status is invalid")
    if gap_completion.get("invalid_result") != {
        "execution_status": "failed",
        "diagnostic_status": "not_valid",
    }:
        raise LoaderError("structural gap invalid result status is invalid")
    if gap_completion.get("unavailable_runner_result") != {
        "execution_status": "blocked",
        "diagnostic_status": "uncertainty",
    }:
        raise LoaderError("structural gap unavailable-runner status is invalid")
    correction = gap.get("correction", {})
    if (
        correction.get("target_stage") != "planning"
        or correction.get("requires_new_candidate_revision") is not True
        or correction.get("rerun_all_passes_before_scanner") is not True
    ):
        raise LoaderError("gap correction must return to a new planning revision")

    path_to_scanner = execution.get("research_to_planning", ())
    if (
        not isinstance(path_to_scanner, list)
        or "structural_gap_analysis" not in path_to_scanner
        or "scanner_execution" not in path_to_scanner
        or path_to_scanner.index("structural_gap_analysis") >= path_to_scanner.index("scanner_execution")
    ):
        raise LoaderError("structural gap analysis must run before scanner")
    retry = execution.get("on_structural_gap_failure", {})
    if (
        not isinstance(retry, dict)
        or retry.get("return_to") != "planning"
        or retry.get("rerun") != "structural_gap_analysis"
        or retry.get("scanner_blocked_until_valid") is not True
    ):
        raise LoaderError("invalid structural gap correction route")
    return cast(dict[str, Any], data)


def load_stage_workflow(path: str | Path, stage_id: str) -> dict[str, Any]:
    """Resolve one role from the single registered end-to-end workflow file."""
    bundle = load_workflow_bundle(path)
    if stage_id not in _STAGE_ROLES:
        raise LoaderError(f"unknown stage: {stage_id}")
    return cast(dict[str, Any], bundle["role_workflows"][stage_id])


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
