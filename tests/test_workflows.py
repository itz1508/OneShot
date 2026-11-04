"""Single end-to-end workflow contract closure and role boundary tests."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from agent.runtime.loaders import LoaderError, load_stage_workflow, load_workflow_bundle

CONTRACT = Path(".agents/contracts/workflow.yaml")
STAGES = (
    "research",
    "audit_discovery",
    "planning",
    "fixture_validation",
    "build",
    "build_validation",
)


def test_single_workflow_contract_parses_and_has_all_six_roles() -> None:
    assert CONTRACT.is_file()
    assert not list(Path("agent/workflows/stages").glob("*.yaml"))
    bundle = load_workflow_bundle(CONTRACT)
    assert tuple(bundle["role_workflows"]) == STAGES
    assert len(bundle["host_workflows"]) == 22
    assert all(stage in bundle["role_workflows"] for stage in STAGES)
    for stage in STAGES:
        role = load_stage_workflow(CONTRACT, stage)["workflow"]
        assert role["input_schema"]["additionalProperties"] is False
        assert role["output_schema"]["additionalProperties"] is False
        assert role["schema_validation"]["require_output_input_request_ref_match"] is True
        assert role["output_schema"]["allOf"]
        assert role["inputs"]["required"]


def test_approved_role_guidance_is_under_reference_not_roles() -> None:
    assert not list(Path(".agents/roles").glob("*.md"))
    for name in ("researcher", "audit-discovery", "planner", "fixture-validator", "builder", "build-verifier"):
        assert (Path(".agents/reference") / f"{name}.md").is_file()


def _bad_contract(tmp_path: Path, edit) -> Path:
    data = deepcopy(load_workflow_bundle(CONTRACT))
    edit(data)
    target = tmp_path / "broken.yaml"
    target.write_text(yaml.safe_dump(data, sort_keys=False))
    return target


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: d["bundle"].update(role_guidance_root=".agents/roles"),
        lambda d: d["bundle"].update(pre_scanner_gate="scanner_execution"),
        lambda d: d["role_workflows"]["research"]["workflow"]["input_schema"].update(required=["request_id"]),
        lambda d: d["role_workflows"]["audit_discovery"]["workflow"]["output_schema"].update(additionalProperties=True),
        lambda d: d["role_workflows"]["planning"]["workflow"]["request_result_exchange"].update(mode="one_way"),
        lambda d: d["role_workflows"]["build"]["workflow"]["request_result_exchange"].update(
            build_admission_precedes_execution=False
        ),
        lambda d: d["host_workflows"].pop("structural_gap_analysis"),
        lambda d: d["host_workflows"]["structural_gap_analysis"]["input_contracts"].remove("candidate_specification"),
        lambda d: d["host_workflows"]["structural_gap_analysis"]["required_work"].remove("run_walking_skeleton"),
        lambda d: d["host_workflows"]["structural_gap_analysis"]["completion"].update(
            known_critical_gap_detection_rate=0.5
        ),
        lambda d: d["host_workflows"]["structural_gap_analysis"]["correction"].update(
            rerun_all_passes_before_scanner=False
        ),
        lambda d: d["execution"]["research_to_planning"].remove("structural_gap_analysis"),
        lambda d: d["execution"]["on_structural_gap_failure"].update(scanner_blocked_until_valid=False),
    ],
)
def test_invalid_contract_is_rejected(tmp_path: Path, edit) -> None:
    with pytest.raises(LoaderError):
        load_workflow_bundle(_bad_contract(tmp_path, edit))


def test_duplicate_workflow_key_rejected(tmp_path: Path) -> None:
    source = CONTRACT.read_text()
    target = tmp_path / "duplicate.yaml"
    target.write_text(source.replace("  role_order:", "  role_order: []\n  role_order:", 1))
    with pytest.raises(LoaderError, match="duplicate"):
        load_workflow_bundle(target)


def test_research_is_information_gathering_and_builder_execution_only() -> None:
    research = load_stage_workflow(CONTRACT, "research")["workflow"]
    assert "Gather" in research["success_contract"]["success_meaning"]
    assert research["completion"]["successful_result"]["diagnostic_status_is_not_a_completion_gate"]
    assert research["request_result_exchange"]["returns_result_to"] == "input_request.respond_to"

    build = load_stage_workflow(CONTRACT, "build")["workflow"]
    assert "new_design" in build["request_result_exchange"]["prohibits"]
    assert build["request_result_exchange"]["preflight_and_effect_gate"] == "host_owned"
    assert build["request_result_exchange"]["move_action"] == "single_admitted_action_declaring_source_and_destination"


def test_structural_gap_workflow_declares_every_runtime_input() -> None:
    gap = load_workflow_bundle(CONTRACT)["host_workflows"]["structural_gap_analysis"]
    assert set(gap["input_contracts"]) == {
        "candidate_specification",
        "workflow_contract_bundle",
        "registry_snapshot_set",
        "workflow_trace",
        "concern_matrix",
        "gap_backtest_corpus",
        "source_grounded_analysis",
        "comparable_system_analysis",
    }
    assert gap["completion"]["successful_result"] == {
        "execution_status": "completed",
        "diagnostic_status": "valid",
    }
    assert gap["completion"]["invalid_result"] == {
        "execution_status": "failed",
        "diagnostic_status": "not_valid",
    }
