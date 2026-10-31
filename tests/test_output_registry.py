"""Tests for the OneShot Adaptive Output Schema Registry.

Covers: auto-selection by stage, multiple outputs, ambiguous matches,
missing schemas, malformed JSON, consumer
compatibility, actual output generation and persistence.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from unittest import TestCase

# Ensure agent/ is importable
_AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from output_registry import (
    OutputSchemaDescriptor,
    SchemaRegistry,
    SelectionContext,
    SerializationResult,
)


# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------

def _research_record() -> dict:
    return {
        "kind": "research",
        "task_id": "task-abc123",
        "record_id": "research-abc123",
        "revision": 1,
        "status": "complete",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "purpose": {
            "user_outcome": "Build the feature",
            "original_request_ref": "user-request",
            "accepted_requirements": [
                {"id": "R1", "statement": "Do X", "authority_ref": "AGENTS.md", "scope": "in_scope"},
            ],
            "scope": [], "constraints": [], "superseded_requirements": [],
        },
        "workspace": {"repo_root": "/repo", "git_revision": "abc123", "environment_ref": "serverless"},
        "search": {
            "todo_search_ref": "AGENTS.md",
            "questions": [],
            "sources": [
                {"id": "S1", "location": "AGENTS.md", "revision_or_hash": "abc123",
                 "authority": "accepted", "evidence_ref": "AGENTS.md"},
            ],
            "findings": [
                {"id": "F1", "claim": "Found X", "evidence_refs": ["AGENTS.md"],
                 "assessment": "supported"},
            ],
            "contradictions": [], "uncertainties": [],
        },
        "outputs": {
            "evidence_refs": ["AGENTS.md"],
            "candidate_plan_ref": "agent/templates/execplan.md",
            "fixture_refs": ["bin/context_counter.py"],
            "success_criteria_refs": ["agent/contracts/build.yaml"],
            "requirement_trace": [
                {"requirement_id": "R1", "finding_ids": ["F1"],
                 "fixture_ids": ["bin/context_counter.py"],
                 "criterion_ids": ["agent/contracts/build.yaml"], "disposition": "covered"},
            ],
        },
        "review": {
            "coverage": "sufficient", "evidence_grounding": "passed",
            "unsupported_claims": [], "unresolved_issues": [], "blockers": [],
            "disposition": "ready_for_plan", "review_receipt_ref": "AGENTS.md",
        },
        "progress_log": [{"at": "2026-01-01T00:00:00+00:00", "step": "done", "result": "ok"}],
        "decision_log": [{"at": "2026-01-01T00:00:00+00:00", "decision": "proceed", "why": "ok"}],
        "checkpoint": {"action_state": "completed", "action_id": "research-abc123"},
        "handoff": {"to": "plan", "ready": True, "artifact_manifest_ref": "AGENTS.md",
                     "validation_receipt_ref": "AGENTS.md"},
    }


def _plan_record() -> dict:
    return {
        "kind": "plan",
        "task_id": "task-abc123",
        "record_id": "plan-001",
        "revision": 1,
        "status": "complete",
        "gap_analysis": {
            "status": "resolved",
            "scanner_calls": [
                {"at": "2026-01-01T00:00:00+00:00", "tool_ref": "agent/adapters/repository_inventory.py",
                 "scope_ref": "AGENTS.md", "input_revision": 1,
                 "findings_ref": "AGENTS.md", "receipt_ref": "AGENTS.md", "outcome": "passed"},
            ],
            "findings": [
                {"id": "gap-1", "type": "missing", "severity": "critical",
                 "evidence_refs": ["AGENTS.md"], "status": "resolved",
                 "fix_receipt_ref": "AGENTS.md", "recheck_ref": "AGENTS.md"},
            ],
            "unresolved_critical_ids": [],
            "last_recheck_ref": "AGENTS.md",
        },
    }


def _build_record() -> dict:
    return {
        "kind": "build",
        "task_id": "task-abc123",
        "record_id": "build-001",
        "revision": 1,
        "status": "complete",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "plan_input": {
            "record_ref": "plan-001", "record_id": "plan-001", "record_revision": 1,
            "accepted_milestone_ids": ["m1"], "accepted_criterion_ids": ["c1"],
        },
        "execution": {
            "workspace_snapshot_ref": "AGENTS.md", "environment_ref": "serverless",
            "started_at": "2026-01-01T00:00:00+00:00", "finished_at": "2026-01-01T00:00:00+00:00",
            "milestone_results": [{"id": "m1", "status": "passed", "changed_files": [],
                                    "command_receipts": ["e2e-1"], "artifact_refs": ["bin/context_counter.py"]}],
            "command_receipts": [
                {"id": "e2e-1", "command": "python counter", "cwd": "/repo",
                 "exit_code": 0, "receipt_ref": "AGENTS.md"},
            ],
            "artifact_manifest_ref": "agent/contracts/build.yaml", "changes": [], "cleanup": [],
        },
        "implementation_validation": {
            "status": "passed",
            "checks": [{"criterion_id": "c1", "status": "passed", "receipt_ref": "AGENTS.md"}],
            "regressions": [],
        },
        "post_build_e2e": {
            "status": "passed", "real_entrypoint_ref": "bin/context_counter.py",
            "environment_ref": "serverless",
            "cases": [{"fixture_ref": "bin/context_counter.py", "expected_ref": "AGENTS.md",
                       "observed_ref": "AGENTS.md", "receipt_ref": "AGENTS.md", "status": "passed"}],
            "chaos_cases": [],
            "independent_result_checks": [
                {"criterion_id": "c1", "expected_ref": "AGENTS.md", "observed_ref": "AGENTS.md",
                 "receipt_ref": "AGENTS.md", "status": "passed"},
            ],
            "coverage_gaps": [],
        },
        "issues_and_corrections": {"findings": [], "gap_fix_receipt_refs": [],
                                    "revalidation_receipt_refs": [], "blockers": []},
        "outcome": {
            "status": "verified", "user_visible_result_ref": "bin/context_counter.py",
            "criterion_results": [{"criterion_id": "c1", "status": "passed", "evidence_ref": "AGENTS.md"}],
            "remaining_limitations": [], "summary": "All passed",
        },
        "progress_log": [{"at": "2026-01-01T00:00:00+00:00", "step": "e2e", "result": "done"}],
        "decision_log": [{"at": "2026-01-01T00:00:00+00:00", "decision": "done", "why": "e2e"}],
        "checkpoint": {"action_state": "completed", "action_id": "build-001"},
        "handoff": {"to": "complete", "ready": True,
                     "completion_receipt_ref": "AGENTS.md", "validation_receipt_ref": "AGENTS.md"},
    }


def _repo_summary_dict() -> dict:
    return {
        "repository": "https://github.com/itz1508/OneShot",
        "branch": "main",
        "commit_sha": "abc123def456",
        "working_tree_clean": False,
        "files": ["AGENTS.md", "pyproject.toml"],
        "gap_matrix": [
            {"area": "00 — Authority", "requirement": "ground decisions",
             "current_state": "Implemented", "action": "adapt",
             "evidence": "Files: ['AGENTS.md']", "color_eval": "GREEN"},
        ],
        "available_tools": ["git", "python3.12", "pytest"],
        "color_eval_baseline": "GREEN",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRegistryConstruction(TestCase):
    """Registry initialisation and default schema registration."""

    def test_default_registry_has_four_schemas(self):
        reg = SchemaRegistry()
        names = {s.name for s in reg.list_schemas()}
        self.assertEqual(names, {
            "output_research", "output_gap_analysis",
            "output_built", "output_repo_summary",
        })

    def test_get_returns_descriptor(self):
        reg = SchemaRegistry()
        desc = reg.get("output_research")
        self.assertIsNotNone(desc)
        self.assertEqual(desc.stage, "research")

    def test_get_missing_returns_none(self):
        reg = SchemaRegistry()
        self.assertIsNone(reg.get("nonexistent"))

    def test_duplicate_registration_is_idempotent(self):
        reg = SchemaRegistry()
        desc = OutputSchemaDescriptor(
            name="output_research", schema_file="output_research.json",
            stage="research", contract_ref="x",
        )
        reg.register(desc)  # should not raise


class TestSchemaSelection(TestCase):
    """Automatic schema selection by stage, material, and request."""

    def test_select_by_stage_research(self):
        reg = SchemaRegistry()
        ctx = SelectionContext(stage="research")
        result = reg.select(ctx)
        self.assertFalse(result.errors)
        names = [d.name for d in result.selected]
        self.assertIn("output_research", names)
        self.assertIn("output_repo_summary", names)  # stage=any
        self.assertNotIn("output_built", names)
        self.assertNotIn("output_gap_analysis", names)

    def test_select_by_stage_plan(self):
        reg = SchemaRegistry()
        result = reg.select(SelectionContext(stage="plan"))
        names = [d.name for d in result.selected]
        self.assertIn("output_gap_analysis", names)
        self.assertIn("output_repo_summary", names)
        self.assertNotIn("output_research", names)
        self.assertNotIn("output_built", names)

    def test_select_by_stage_build(self):
        reg = SchemaRegistry()
        result = reg.select(SelectionContext(stage="build"))
        names = [d.name for d in result.selected]
        self.assertIn("output_built", names)
        self.assertIn("output_repo_summary", names)
        self.assertNotIn("output_research", names)

    def test_select_with_material_filter(self):
        reg = SchemaRegistry()
        ctx = SelectionContext(
            stage="research",
            available_material={"research_record": True, "repo_summary": False},
        )
        result = reg.select(ctx)
        names = [d.name for d in result.selected]
        self.assertIn("output_research", names)
        self.assertNotIn("output_repo_summary", names)  # material not available

    def test_select_explicit_request(self):
        reg = SchemaRegistry()
        result = reg.select(SelectionContext(requested_output="output_built"))
        self.assertFalse(result.errors)
        self.assertEqual(len(result.selected), 1)
        self.assertEqual(result.selected[0].name, "output_built")

    def test_select_explicit_request_not_found(self):
        reg = SchemaRegistry()
        result = reg.select(SelectionContext(requested_output="nonexistent"))
        self.assertTrue(result.errors)
        self.assertEqual(len(result.selected), 0)

    def test_select_no_match_returns_errors(self):
        reg = SchemaRegistry()
        ctx = SelectionContext(
            stage="research",
            available_material={"research_record": False, "repo_summary": False},
        )
        result = reg.select(ctx)
        self.assertTrue(result.errors)
        self.assertEqual(len(result.selected), 0)


class TestAmbiguousSelection(TestCase):
    """Ambiguous match detection when multiple schemas share priority."""

    def test_ambiguous_when_same_priority_same_stage(self):
        reg = SchemaRegistry()
        # Register a second plan-stage schema with same priority
        extra = OutputSchemaDescriptor(
            name="output_plan_extra", schema_file="output_gap_analysis.json",
            stage="plan", contract_ref="x",
            priority=10,
        )
        reg.register(extra)
        result = reg.select(SelectionContext(stage="plan"))
        self.assertTrue(result.ambiguous)
        self.assertTrue(any("output_plan_extra" in e for e in result.errors))

    def test_not_ambiguous_when_priorities_differ(self):
        reg = SchemaRegistry()
        extra = OutputSchemaDescriptor(
            name="output_plan_extra", schema_file="output_gap_analysis.json",
            stage="plan", contract_ref="x",
            priority=5,  # lower than output_gap_analysis (10)
        )
        reg.register(extra)
        result = reg.select(SelectionContext(stage="plan"))
        self.assertFalse(result.ambiguous)


class TestSerialization(TestCase):
    """JSON serialization of output data."""

    def test_serialize_research_record(self):
        reg = SchemaRegistry()
        data = _research_record()
        result = reg.serialize("output_research", data)
        self.assertFalse(result.errors)
        self.assertIsNotNone(result.json_str)
        parsed = json.loads(result.json_str)
        self.assertEqual(parsed["kind"], "research")
        self.assertEqual(parsed["task_id"], "task-abc123")
        self.assertEqual(parsed["status"], "complete")

    def test_serialize_build_record(self):
        reg = SchemaRegistry()
        result = reg.serialize("output_built", _build_record())
        self.assertFalse(result.errors)
        parsed = json.loads(result.json_str)
        self.assertEqual(parsed["kind"], "build")
        self.assertEqual(parsed["outcome"]["status"], "verified")

    def test_serialize_gap_analysis_from_plan_record(self):
        reg = SchemaRegistry()
        gap_data = SchemaRegistry.extract_gap_analysis(_plan_record())
        result = reg.serialize("output_gap_analysis", gap_data)
        self.assertFalse(result.errors)
        parsed = json.loads(result.json_str)
        self.assertEqual(parsed["status"], "resolved")
        self.assertEqual(parsed["task_id"], "task-abc123")
        self.assertEqual(parsed["plan_record_id"], "plan-001")
        self.assertEqual(len(parsed["findings"]), 1)

    def test_serialize_repo_summary(self):
        reg = SchemaRegistry()
        result = reg.serialize("output_repo_summary", _repo_summary_dict())
        self.assertFalse(result.errors)
        parsed = json.loads(result.json_str)
        self.assertEqual(parsed["repository"], "https://github.com/itz1508/OneShot")
        self.assertEqual(parsed["color_eval_baseline"], "GREEN")

    def test_serialize_missing_schema(self):
        reg = SchemaRegistry()
        result = reg.serialize("nonexistent", {})
        self.assertTrue(result.errors)
        self.assertIn("not found", result.errors[0])

    def test_serialize_dataclass(self):
        reg = SchemaRegistry()
        # Test with a dataclass (simulates RepoSummary)
        from dataclasses import dataclass as dc_dataclass

        @dc_dataclass
        class FakeSummary:
            repository: str
            branch: str
            commit_sha: str
            working_tree_clean: bool
            files: list
            gap_matrix: list
            available_tools: list
            color_eval_baseline: str

        summary = FakeSummary(
            repository="test", branch="main", commit_sha="abc",
            working_tree_clean=True, files=[], gap_matrix=[],
            available_tools=[], color_eval_baseline="GREEN",
        )
        result = reg.serialize("output_repo_summary", summary)
        self.assertFalse(result.errors)
        parsed = json.loads(result.json_str)
        self.assertEqual(parsed["repository"], "test")

    def test_serialize_multiple(self):
        reg = SchemaRegistry()
        sel_result = reg.select(SelectionContext(stage="build"))
        data_map = {
            "output_built": _build_record(),
            "output_repo_summary": _repo_summary_dict(),
        }
        results = reg.serialize_multiple(sel_result.selected, data_map)
        self.assertEqual(len(results), 2)
        for r in results:
            self.assertFalse(r.errors, f"Errors for {r.output_name}: {r.errors}")

    def test_serialize_multiple_missing_data(self):
        reg = SchemaRegistry()
        sel = reg.select(SelectionContext(stage="build"))
        data_map = {"output_built": _build_record()}  # missing repo_summary
        results = reg.serialize_multiple(sel.selected, data_map)
        has_error = any(r.errors for r in results)
        self.assertTrue(has_error)


class TestStructuralValidation(TestCase):
    """Lightweight JSON schema structural validation."""

    def test_valid_research_json(self):
        reg = SchemaRegistry()
        data = _research_record()
        json_str = json.dumps(data)
        errors = reg.validate_json("output_research", json_str)
        self.assertEqual(errors, [], f"Unexpected errors: {errors}")

    def test_valid_built_json(self):
        reg = SchemaRegistry()
        json_str = json.dumps(_build_record())
        errors = reg.validate_json("output_built", json_str)
        self.assertEqual(errors, [], f"Unexpected errors: {errors}")

    def test_missing_required_field(self):
        reg = SchemaRegistry()
        data = _research_record()
        del data["kind"]
        errors = reg.validate_json("output_research", json.dumps(data))
        self.assertTrue(any("kind" in e for e in errors))

    def test_wrong_const_value(self):
        reg = SchemaRegistry()
        data = _research_record()
        data["kind"] = "plan"  # should be "research"
        errors = reg.validate_json("output_research", json.dumps(data))
        self.assertTrue(any("kind" in e and "plan" in e for e in errors))

    def test_malformed_json(self):
        reg = SchemaRegistry()
        errors = reg.validate_json("output_research", "{invalid json}")
        self.assertTrue(any("Malformed" in e for e in errors))

    def test_validate_missing_schema(self):
        reg = SchemaRegistry()
        errors = reg.validate_json("nonexistent", "{}")
        self.assertTrue(any("not found" in e for e in errors))


class TestSchemaLoading(TestCase):
    """Loading JSON schema files from disk."""

    def test_load_schema_research(self):
        reg = SchemaRegistry()
        schema = reg.load_schema("output_research")
        self.assertIsNotNone(schema)
        self.assertEqual(schema["title"], "Research Output")
        self.assertIn("kind", schema["properties"])

    def test_load_schema_gap_analysis(self):
        reg = SchemaRegistry()
        schema = reg.load_schema("output_gap_analysis")
        self.assertIsNotNone(schema)
        self.assertEqual(schema["title"], "Gap Analysis Output")

    def test_load_schema_built(self):
        reg = SchemaRegistry()
        schema = reg.load_schema("output_built")
        self.assertIsNotNone(schema)
        self.assertEqual(schema["title"], "Build Output")

    def test_load_schema_repo_summary(self):
        reg = SchemaRegistry()
        schema = reg.load_schema("output_repo_summary")
        self.assertIsNotNone(schema)
        self.assertEqual(schema["title"], "Repository Summary Output")

    def test_load_schema_missing(self):
        reg = SchemaRegistry()
        self.assertIsNone(reg.load_schema("nonexistent"))


class TestConsumerCompatibility(TestCase):
    """Verify existing consumers are not broken."""

    def test_research_output_compatible_with_contract_fields(self):
        """Serialized research output must contain all expected fields."""
        reg = SchemaRegistry()
        result = reg.serialize("output_research", _research_record())
        self.assertFalse(result.errors)
        data = json.loads(result.json_str)
        for field in ["kind", "task_id", "record_id", "revision", "status",
                      "purpose", "search", "outputs", "review", "handoff"]:
            self.assertIn(field, data, f"Missing field '{field}'")

    def test_build_output_compatible_with_contract_fields(self):
        """Serialized build output must contain all expected fields."""
        reg = SchemaRegistry()
        result = reg.serialize("output_built", _build_record())
        self.assertFalse(result.errors)
        data = json.loads(result.json_str)
        for field in ["kind", "task_id", "record_id", "revision", "status",
                      "plan_input", "execution", "implementation_validation",
                      "post_build_e2e", "outcome", "handoff"]:
            self.assertIn(field, data, f"Missing field '{field}'")

    def test_gap_analysis_extracts_from_plan_correctly(self):
        """The gap_analysis extraction must preserve all expected fields."""
        reg = SchemaRegistry()
        plan = _plan_record()
        gap = SchemaRegistry.extract_gap_analysis(plan)
        for field in ["status", "scanner_calls", "findings",
                      "unresolved_critical_ids", "last_recheck_ref"]:
            self.assertIn(field, gap, f"Missing gap_analysis field '{field}'")

    def test_repo_summary_preserves_repo_summary_tool_fields(self):
        """Serialized repo summary must contain all fields from
        tools/repo_summary.py RepoSummary dataclass."""
        reg = SchemaRegistry()
        summary = _repo_summary_dict()
        result = reg.serialize("output_repo_summary", summary)
        self.assertFalse(result.errors)
        data = json.loads(result.json_str)
        for field in ["repository", "branch", "commit_sha", "working_tree_clean",
                      "files", "gap_matrix", "available_tools", "color_eval_baseline"]:
            self.assertIn(field, data, f"Missing field '{field}' from RepoSummary compatibility")


class TestOutputPersistence(TestCase):
    """Verify actual output generation and persistence to disk."""

    def test_persist_research_output(self):
        reg = SchemaRegistry()
        result = reg.serialize("output_research", _research_record())
        self.assertFalse(result.errors)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(result.json_str)
            path = f.name
        try:
            loaded = json.loads(Path(path).read_text())
            self.assertEqual(loaded["kind"], "research")
            self.assertEqual(loaded["record_id"], "research-abc123")
        finally:
            os.unlink(path)

    def test_persist_all_four_outputs(self):
        reg = SchemaRegistry()
        outputs = {
            "output_research": _research_record(),
            "output_gap_analysis": SchemaRegistry.extract_gap_analysis(_plan_record()),
            "output_built": _build_record(),
            "output_repo_summary": _repo_summary_dict(),
        }
        for name, data in outputs.items():
            result = reg.serialize(name, data)
            self.assertFalse(result.errors, f"Failed to serialize {name}: {result.errors}")
            # Verify the JSON can be round-tripped
            parsed = json.loads(result.json_str)
            self.assertIsInstance(parsed, dict)
            # Verify structural validation passes
            errors = reg.validate_json(name, result.json_str)
            self.assertEqual(errors, [], f"Structural validation errors for {name}: {errors}")

    def test_persist_multiple_outputs_to_disk(self):
        reg = SchemaRegistry()
        sel = reg.select(SelectionContext(stage="build"))
        data_map = {
            "output_built": _build_record(),
            "output_repo_summary": _repo_summary_dict(),
        }
        results = reg.serialize_multiple(sel.selected, data_map)
        with tempfile.TemporaryDirectory() as tmpdir:
            for r in results:
                self.assertFalse(r.errors)
                path = Path(tmpdir) / f"{r.output_name}.json"
                path.write_text(r.json_str)
                # Verify it can be read back
                loaded = json.loads(path.read_text())
                self.assertIsInstance(loaded, dict)


class TestIntegrationWithWorkflow(TestCase):
    """Integration: use the registry alongside the workflow controller outputs."""

    def test_full_workflow_output_generation(self):
        """Simulate a full workflow: select and serialize outputs for each stage."""
        reg = SchemaRegistry()

        # Stage 1: Research
        r_sel = reg.select(SelectionContext(stage="research"))
        self.assertFalse(r_sel.errors)
        r_data = {"output_research": _research_record()}
        r_results = reg.serialize_multiple(r_sel.selected, r_data)
        # repo_summary not available, so it should error (expected)
        r_ok = [r for r in r_results if not r.errors]
        self.assertTrue(any(r.output_name == "output_research" for r in r_ok))

        # Stage 2: Plan (gap analysis)
        p_sel = reg.select(SelectionContext(stage="plan"))
        p_data = {
            "output_gap_analysis": SchemaRegistry.extract_gap_analysis(_plan_record()),
        }
        p_results = reg.serialize_multiple(p_sel.selected, p_data)
        p_ok = [r for r in p_results if not r.errors]
        self.assertTrue(any(r.output_name == "output_gap_analysis" for r in p_ok))

        # Stage 3: Build
        b_sel = reg.select(SelectionContext(stage="build"))
        b_data = {"output_built": _build_record()}
        b_results = reg.serialize_multiple(b_sel.selected, b_data)
        b_ok = [r for r in b_results if not r.errors]
        self.assertTrue(any(r.output_name == "output_built" for r in b_ok))

    def test_all_outputs_available_selects_all(self):
        """When all material is available, all outputs can be selected."""
        reg = SchemaRegistry()
        ctx = SelectionContext(
            available_material={
                "research_record": True,
                "gap_analysis": True,
                "build_record": True,
                "repo_summary": True,
            }
        )
        result = reg.select(ctx)
        self.assertFalse(result.errors)
        names = {d.name for d in result.selected}
        self.assertEqual(names, {
            "output_research", "output_gap_analysis",
            "output_built", "output_repo_summary",
        })

    def test_cross_stage_repo_summary_always_selectable(self):
        """repo_summary (stage='any') is selectable at every stage."""
        reg = SchemaRegistry()
        for stage in ["research", "plan", "build", "complete"]:
            result = reg.select(SelectionContext(
                stage=stage,
                available_material={"repo_summary": True},
            ))
            names = {d.name for d in result.selected}
            self.assertIn("output_repo_summary", names, f"repo_summary not selected at stage={stage}")


class TestRegistryDoesNotDuplicateOwnership(TestCase):
    """Verify the registry doesn't duplicate validation or controller ownership."""

    def test_registry_does_not_execute_tools(self):
        """Serialization should work with plain dicts, no tool execution."""
        reg = SchemaRegistry()
        result = reg.serialize("output_research", _research_record())
        self.assertFalse(result.errors)
        self.assertIsNotNone(result.json_str)

    def test_registry_validate_json_is_structural_only(self):
        """The registry's validate_json is structural only, not invariant validation."""
        reg = SchemaRegistry()
        # A research record with bad evidence refs will pass structural validation
        # (validate_json doesn't check evidence resolution)
        data = _research_record()
        data["search"]["sources"][0]["evidence_ref"] = "nonexistent-file"
        errors = reg.validate_json("output_research", json.dumps(data))
        # Structural validation passes (field exists, is a string)
        self.assertEqual(errors, [])
