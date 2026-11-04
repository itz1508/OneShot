"""Stage workflow identity, role boundaries, and bidirectional schema tests."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from agent.runtime.loaders import LoaderError, load_stage_workflow

ROOT = Path("agent/workflows/stages")


def test_six_role_workflows_have_distinct_closed_contracts():
    files = sorted(ROOT.glob("*.yaml"))
    assert len(files) == 6
    roles = set()
    for path in files:
        data = load_stage_workflow(path)
        workflow = data["workflow"]
        assert data["stage"] == path.name.removesuffix(".workflow.yaml")
        assert workflow["role_id"] not in roles
        roles.add(workflow["role_id"])
        assert workflow["input_schema"]["additionalProperties"] is False
        assert workflow["output_schema"]["additionalProperties"] is False
        assert workflow["output_schema"]["allOf"]
        assert workflow["schema_validation"]["require_output_input_request_ref_match"] is True


def _write_bad_workflow(tmp_path, change):
    data = deepcopy(load_stage_workflow(ROOT / "research.workflow.yaml"))
    change(data)
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(data))
    return path


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(stage="planning"),
        lambda d: d["workflow"].update(role_id="builder"),
        lambda d: d["workflow"]["input_schema"].update(required=["request_id"]),
        lambda d: d["workflow"]["output_schema"].update(additionalProperties=True),
        lambda d: d["workflow"]["schema_validation"].update(unresolved_external_ref="ignore"),
        lambda d: d["workflow"]["request_result_exchange"].update(mode="one_way"),
        lambda d: d["workflow"]["inputs"].update(required=[]),
        lambda d: d["workflow"]["success_contract"].update(criteria_completeness_gate=True),
    ],
)
def test_invalid_workflow_contract_rejected(tmp_path, mutate):
    with pytest.raises(LoaderError):
        load_stage_workflow(_write_bad_workflow(tmp_path, mutate))


def test_duplicate_policy_key_rejected(tmp_path):
    original = (ROOT / "research.workflow.yaml").read_text()
    duplicate = original.replace("  stage_id: research", "  stage_id: research\n  stage_id: build", 1)
    path = tmp_path / "duplicate.yaml"
    path.write_text(duplicate)
    with pytest.raises(LoaderError, match="duplicate"):
        load_stage_workflow(path)


def test_build_execution_only_and_research_gathers_information():
    build = load_stage_workflow(ROOT / "build.workflow.yaml")["workflow"]
    assert "new_design" in build["request_result_exchange"]["prohibits"]
    assert build["request_result_exchange"]["preflight_and_effect_gate"] == "host_owned"
    assert build["request_result_exchange"]["move_action"] == "single_admitted_action_declaring_source_and_destination"
    research = load_stage_workflow(ROOT / "research.workflow.yaml")["workflow"]
    assert "Gather" in research["success_contract"]["success_meaning"]
    assert research["completion"]["successful_result"]["diagnostic_status_is_not_a_completion_gate"]
    assert research["request_result_exchange"]["returns_result_to"] == "input_request.respond_to"
