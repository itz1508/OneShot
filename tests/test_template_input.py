"""Runtime-free template loading and quality-input validation tests.

The module checks declared structure, not task applicability, factual provenance,
or host authorization. The host chooses the template ID explicitly.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from workflow_templates import TemplateRejected, list_templates, load_template, validate_quality_input

ROOT = Path(__file__).resolve().parents[1]


def quality_input(stage: str) -> dict:
    return {
        "template_id": stage,
        "task_id": "task-01",
        "request_id": "request-01",
        "original_request": "Review the user-supplied source and preserve supported facts",
        "context_refs": ["source:test/fixture.txt#sha256:abc"],
        "accepted_decision_refs": [],
        "unknowns": [],
        "readiness": "ready",
    }


def test_single_catalog_is_packaged_and_resolves_three_explicit_templates() -> None:
    catalog = json.loads((ROOT / "templates/catalog.json").read_text(encoding="utf-8"))
    assert set(catalog) == {"schema_version", "input_contract", "templates"}
    assert set(catalog["templates"]) == set(list_templates()) == {"research", "plan", "build"}
    for stage, entry in catalog["templates"].items():
        template = load_template(stage)
        assert template["output_contract"] == f"output/schema/{stage}.json"
        assert f"output/schema/{stage}.json" in template["instructions"]
        assert "No automatic next stage" in template["instructions"] or "no automatic next stage" in template["instructions"]
        assert template["applicability"]
        assert (ROOT / template["output_contract"]).is_file()
        assert (ROOT / "templates" / entry["instructions"]).is_file()


def test_input_schema_is_draft_2020_12_and_rejects_incorrect_stage() -> None:
    schema = json.loads((ROOT / "templates/schema/input.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    for stage in list_templates():
        doc = quality_input(stage)
        if stage == "build":
            doc.update(plan_id="plan-1", approval_ref="operator:grant-1")
        assert validate_quality_input(stage, doc) is doc
        with pytest.raises(TemplateRejected, match="mismatch"):
            validate_quality_input("research" if stage != "research" else "plan", doc)
    with pytest.raises(TemplateRejected, match="Unknown template"):
        load_template("../build")


def test_blocked_inputs_retain_missing_fields_without_guessing() -> None:
    doc = quality_input("build")
    doc["readiness"] = "blocked"
    doc["unknowns"] = [{"field": "plan_id", "reason": "No accepted Plan record", "blocking": True}]
    assert validate_quality_input("build", doc) == doc
    assert "plan_id" not in doc and "approval_ref" not in doc
    # A blocked input must explain at least one genuinely blocking unknown.
    doc["unknowns"] = []
    with pytest.raises(TemplateRejected):
        validate_quality_input("build", doc)


def test_ready_inputs_cannot_hide_blocking_unknowns() -> None:
    doc = quality_input("plan")
    doc["unknowns"] = [{"field": "scope", "reason": "User did not specify target", "blocking": True}]
    with pytest.raises(TemplateRejected):
        validate_quality_input("plan", doc)
    doc["unknowns"][0]["blocking"] = False
    assert validate_quality_input("plan", doc) == doc


def test_ready_build_needs_plan_reference_and_approval_reference() -> None:
    doc = quality_input("build")
    with pytest.raises(TemplateRejected):
        validate_quality_input("build", doc)
    doc["plan_id"] = "plan-1"
    with pytest.raises(TemplateRejected):
        validate_quality_input("build", doc)
    doc["approval_ref"] = "host:operator-grant"
    assert validate_quality_input("build", doc) == doc
    # A string reference is metadata; independently enforced BuildPolicy is still required.


def test_unknown_or_fabricated_fields_rejected_without_modifying_input() -> None:
    doc = quality_input("research")
    snapshot = copy.deepcopy(doc)
    doc["predicted_expected"] = "hallucinated"
    with pytest.raises(TemplateRejected):
        validate_quality_input("research", doc)
    assert {k: v for k, v in doc.items() if k != "predicted_expected"} == snapshot
    doc.pop("predicted_expected")
    doc.pop("original_request")
    with pytest.raises(TemplateRejected):
        validate_quality_input("research", doc)


def test_plan_without_research_remains_ready_when_original_request_is_sufficient() -> None:
    doc = quality_input("plan")
    doc["context_refs"] = []
    assert validate_quality_input("plan", doc) == doc
    assert "research_id" not in doc
