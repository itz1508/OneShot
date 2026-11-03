"""Research-only Pydantic boundary tests (Plan/Build unchanged)."""

import copy
import json

import pytest
from pydantic import ValidationError

from agent.contracts.models import PlanRecord, ResearchRecord
from agent.output_registry import SchemaRegistry


def sample():
    return {
        "kind": "research",
        "task_id": "task-001",
        "record_id": "research-001",
        "revision": 1,
        "purpose": {
            "user_outcome": "Inspect source",
            "accepted_requirements": [{"id": "R1", "statement": "Inspect"}],
        },
        "search": {
            "sources": [{"id": "S1", "location": "AGENTS.md", "revision_or_hash": "abc"}],
            "findings": [{"id": "F1", "claim": "Inspected", "assessment": "supported"}],
        },
        "outputs": {"requirement_trace": [{"requirement_id": "R1", "finding_ids": ["F1"]}]},
        "handoff": {"to": "plan", "ready": False},
    }


def test_json_roundtrip():
    record = ResearchRecord.model_validate_json(json.dumps(sample()), strict=True)
    assert ResearchRecord.model_validate_json(record.model_dump_json(), strict=True) == record


@pytest.mark.parametrize(
    ("path", "key"),
    [
        ((), "unknown_root"),
        (("purpose",), "unknown_purpose"),
        (("search",), "unknown_search"),
        (("outputs",), "unknown_outputs"),
        (("review",), "unknown_review"),
        (("workspace",), "unknown_workspace"),
        (("handoff",), "unknown_handoff"),
        (("checkpoint",), "unknown_checkpoint"),
        (("search", "sources", 0), "unknown_source"),
        (("purpose", "accepted_requirements", 0), "unknown_requirement"),
    ],
)
def test_unknown_field_rejected(path, key):
    data = sample()
    current = data
    for name in path:
        if name in {"review", "workspace", "checkpoint"} and name not in current:
            current[name] = {}
        current = current[name]
    current[key] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ResearchRecord.model_validate_json(json.dumps(data))


def test_revision_strict():
    data = sample()
    data["revision"] = "1"
    with pytest.raises(ValidationError):
        ResearchRecord.model_validate_json(json.dumps(data), strict=True)
    data["revision"] = True
    with pytest.raises(ValidationError):
        ResearchRecord.model_validate(data)


def test_duplicate_ids_rejected():
    data = sample()
    data["search"]["findings"].append(copy.deepcopy(data["search"]["findings"][0]))
    with pytest.raises(ValidationError, match="duplicate finding IDs"):
        ResearchRecord.model_validate(data)


def test_unknown_trace_rejected():
    data = sample()
    data["outputs"]["requirement_trace"][0]["finding_ids"] = ["F404"]
    with pytest.raises(ValidationError, match="unknown findings"):
        ResearchRecord.model_validate(data)


def test_invalid_assessment_rejected():
    data = sample()
    data["search"]["findings"][0]["assessment"] = "unknown-value"
    with pytest.raises(ValidationError):
        ResearchRecord.model_validate_json(json.dumps(data))


def test_schema_generated_by_model():
    registry = SchemaRegistry()
    schema = registry.load_schema("output_research")
    assert schema["additionalProperties"] is False
    assert "success_criteria" in schema["$defs"]["ResearchOutputs"]["properties"]
    assert registry.validate_json("output_research", json.dumps(sample())) == []


def test_registry_blocks_invalid_research():
    registry = SchemaRegistry()
    data = sample()
    data["purpose"]["unknown"] = True
    assert registry.serialize("output_research", data).errors
    assert registry.validate_json("output_research", json.dumps(data))


def test_legacy_version_remains_recognized():
    data = sample()
    data["contract_version"] = "1.1"
    assert ResearchRecord.model_validate(data).contract_version == "1.1"


def test_plan_remains_permissive():
    assert PlanRecord.model_config.get("extra") == "allow"
