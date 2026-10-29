"""Independent expectations for transport and mutually exclusive typed output."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from input.main import InputRejected, accept_input
from output.main import OutputRejected, validate_output

ROOT = Path(__file__).resolve().parents[1]

RESEARCH = {
    "type": "research", "id": "r-1", "request_id": "req-1",
    "findings": [{"statement": "Policy says 7 days", "source_refs": ["source-1:0-20"]}],
}
PLAN = {
    "type": "plan", "id": "p-1", "request_id": "req-1",
    "research_id": "r-1", "actions": [{"description": "Resolve retention conflict"}],
}
BUILD = {
    "type": "build", "id": "b-1", "request_id": "req-1", "plan_id": "p-1",
    "execution": {"outcome": "succeeded", "artifact_refs": ["artifact-1"]},
    "verification": {"outcome": "valid", "evidence_refs": ["proof-1"]},
    "cleanup": {"outcome": "completed", "remaining_refs": []},
}


def run_module(module: str, value: object, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", module],
        input=json.dumps(value), text=True, capture_output=True,
        cwd=str(cwd or ROOT), env=env, check=False,
    )


@pytest.mark.parametrize("value", [RESEARCH, PLAN, BUILD])
def test_stage_result_validates_only_under_its_declared_schema(value: dict) -> None:
    assert validate_output(value) == value
    for name in ("research", "plan", "build"):
        schema = json.loads((ROOT / "output" / "schema" / (name + ".json")).read_text())
        Draft202012Validator.check_schema(schema)
        errors = list(Draft202012Validator(schema).iter_errors(value))
        assert not errors if name == value["type"] else bool(errors)


@pytest.mark.parametrize("value", [RESEARCH, PLAN, BUILD])
def test_real_output_cli_accepts_correct_result(value: dict) -> None:
    run = run_module("output.main", value)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == value
    assert not run.stderr


def test_real_input_cli_accepts_without_executing_action(tmp_path: Path) -> None:
    value = {"request_id": "req-1", "action": "build", "payload": {"path": str(tmp_path / "would_run")}}
    run = run_module("input.main", value)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == value
    assert not (tmp_path / "would_run").exists()


@pytest.mark.parametrize("change", [
    lambda v: {**v, "type": "unknown"},
    lambda v: {**v, "type": "plan"},
    lambda v: {**v, "id": ""},
    lambda v: {**v, "unauthorized": True},
    lambda v: {**v, "findings": [{"statement": "no evidence", "source_refs": "not an array"}]},
])
def test_invalid_or_misidentified_research_rejected(change) -> None:
    with pytest.raises(OutputRejected):
        validate_output(change(RESEARCH))


def test_build_cannot_omit_cleanup_receipt() -> None:
    result = {k: v for k, v in BUILD.items() if k != "cleanup"}
    with pytest.raises(OutputRejected):
        validate_output(result)


def test_build_reports_incomplete_cleanup_without_false_success() -> None:
    result = {**BUILD, "cleanup": {"outcome": "incomplete", "remaining_refs": ["tmp-1"]}}
    assert validate_output(result)["cleanup"]["outcome"] == "incomplete"


def test_plan_not_treated_as_build_approval() -> None:
    assert "authorization" not in validate_output(PLAN)
    with pytest.raises(OutputRejected):
        validate_output({**PLAN, "type": "build"})


def test_invalid_input_rejected() -> None:
    for v in ([], {"request_id": "1", "action": "build"},
              {"request_id": "1", "action": "BUILD", "payload": {}},
              {"request_id": "1", "action": "build", "payload": {}, "approved": True}):
        with pytest.raises(InputRejected):
            accept_input(v)


def test_invalid_output_cli_no_execution(tmp_path: Path) -> None:
    result = {**BUILD, "cleanup": {"outcome": "not-really-done"}}
    before = set(tmp_path.iterdir())
    run = run_module("output.main", result, cwd=ROOT)
    assert run.returncode == 2
    assert run.stdout == ""
    assert json.loads(run.stderr)["valid"] is False
    assert set(tmp_path.iterdir()) == before


def test_output_cli_rejects_schema_path_injection() -> None:
    run = run_module("output.main", {**RESEARCH, "type": "../../../../etc/passwd"})
    assert run.returncode == 2
    assert "Unknown output type" in run.stderr
