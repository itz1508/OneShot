"""Tests only the record checker; these are not real Scanner/agent/E2E tests."""

from __future__ import annotations

import copy
import hashlib

# Migrated from the retired check_contracts module to the models module.
# The names used below (validate_records / validate_research / validate_plan /
# validate_build / preflight_check / evidence_index_resolver) are provided
# by agent/contracts/models.py as compatibility aliases.
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent" / "contracts"))
import models as module


class ContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.refs: set[str] = set()

        def ref(v: str) -> str:
            self.refs.add(v)
            return v

        base = {
            "task_id": "t1",
            "revision": 2,
            "status": "complete",
            "updated_at": "2026-10-30T03:00:00Z",
            "progress_log": [{"at": "2026-10-30T03:00:00Z", "result": "done"}],
            "decision_log": [{"at": "2026-10-30T03:00:00Z", "why": "source-based"}],
        }
        cp = {
            "last_completed_step": "done",
            "next_step": None,
            "action_id": "a1",
            "action_state": "completed",
            "action_receipt_ref": ref("action"),
            "retry_disposition": "not_applicable",
            "source_snapshot_ref": ref("snapshot"),
            "resume_notes": None,
        }
        self.r = dict(
            base,
            contract_version="1.1",
            kind="research",
            record_id="r1",
            checkpoint=copy.deepcopy(cp),
            purpose={
                "user_outcome": "count context",
                "accepted_requirements": [
                    {
                        "id": "R1",
                        "statement": "count",
                        "scope": "in_scope",
                        "authority_ref": ref("request"),
                    }
                ],
            },
            search={
                "todo_search_ref": ref("todo"),
                "sources": [
                    {
                        "id": "S1",
                        "location": "source.py",
                        "revision_or_hash": "sha",
                        "evidence_ref": ref("source-receipt"),
                    }
                ],
                "findings": [
                    {
                        "id": "F1",
                        "claim": "count",
                        "assessment": "supported",
                        "evidence_refs": [ref("source")],
                    }
                ],
            },
            outputs={
                "candidate_plan_ref": ref("candidate"),
                "fixture_refs": [ref("fixture")],
                "success_criteria_refs": [ref("criterion")],
                "requirement_trace": [
                    {
                        "requirement_id": "R1",
                        "finding_ids": ["F1"],
                        "fixture_ids": ["f1"],
                        "criterion_ids": ["c1"],
                    }
                ],
            },
            review={
                "coverage": "sufficient",
                "evidence_grounding": "passed",
                "disposition": "ready_for_plan",
                "unsupported_claims": [],
                "blockers": [],
                "unresolved_issues": [],
                "review_receipt_ref": ref("research-review"),
            },
            handoff={
                "to": "plan",
                "ready": True,
                "artifact_manifest_ref": ref("r-manifest"),
                "validation_receipt_ref": ref("r-validation"),
            },
        )
        self.p = dict(
            base,
            contract_version="1.1",
            kind="plan",
            record_id="p1",
            checkpoint=copy.deepcopy(cp),
            research_input={
                "record_ref": ref("r-record"),
                "record_id": "r1",
                "record_revision": 2,
                "artifact_manifest_ref": "r-manifest",
                "accepted_requirement_ids": ["R1"],
            },
            purpose={
                "user_outcome": "count context",
                "acceptance_criteria": [
                    {
                        "id": "c1",
                        "requirement_id": "R1",
                        "expected_result": "3",
                        "oracle_ref": ref("oracle"),
                    }
                ],
            },
            implementation={
                "proposed_final_tree_ref": ref("tree"),
                "command_environment_ref": ref("env"),
                "rollback_or_recovery": "rerun only after reconcile",
                "milestones": [
                    {
                        "id": "m1",
                        "goal": "counter",
                        "steps": ["implement"],
                        "expected_observations": ["three chars"],
                    }
                ],
            },
            gap_analysis={
                "status": "resolved",
                "scanner_calls": [
                    {
                        "outcome": "passed",
                        "input_revision": 2,
                        "tool_ref": ref("scanner-tool"),
                        "scope_ref": ref("scanner-scope"),
                        "receipt_ref": ref("scanner-receipt"),
                        "findings_ref": ref("scanner-findings"),
                    }
                ],
                "findings": [],
                "unresolved_critical_ids": [],
                "last_recheck_ref": None,
            },
            fixture_validation_chaos={
                "status": "passed",
                "fixture_refs": ["fixture"],
                "oracle_evidence_refs": [ref("oracle-evidence")],
                "chaos_applicability": "required",
                "chaos_case_refs": [ref("chaos")],
                "prebuild_validation_receipt_refs": [ref("fixture-validation")],
                "coverage_gaps": [],
            },
            handoff={
                "to": "build",
                "ready": True,
                "plan_artifact_ref": ref("execplan"),
                "artifact_manifest_ref": ref("p-manifest"),
                "validation_receipt_ref": ref("p-validation"),
            },
        )
        self.b = dict(
            base,
            contract_version="1.1",
            kind="build",
            record_id="b1",
            checkpoint=copy.deepcopy(cp),
            plan_input={
                "record_ref": ref("p-record"),
                "record_id": "p1",
                "record_revision": 2,
                "artifact_manifest_ref": "p-manifest",
                "accepted_milestone_ids": ["m1"],
                "accepted_criterion_ids": ["c1"],
            },
            execution={
                "milestone_results": [
                    {"id": "m1", "status": "passed", "artifact_refs": [ref("result")]}
                ],
                "command_receipts": [
                    {
                        "id": "c",
                        "command": "python counter.py",
                        "cwd": "/tmp/task",
                        "exit_code": 0,
                        "receipt_ref": ref("cmd-receipt"),
                    }
                ],
                "workspace_snapshot_ref": ref("workspace"),
                "environment_ref": "env",
                "finished_at": "2026-10-30T03:00:00Z",
                "artifact_manifest_ref": ref("b-manifest"),
            },
            implementation_validation={
                "status": "passed",
                "checks": [
                    {"criterion_id": "c1", "status": "passed", "receipt_ref": ref("unit-test")}
                ],
            },
            post_build_e2e={
                "status": "passed",
                "real_entrypoint_ref": ref("entry"),
                "environment_ref": "env",
                "cases": [
                    {
                        "fixture_ref": "fixture",
                        "expected_ref": "oracle",
                        "observed_ref": ref("observed"),
                        "receipt_ref": ref("e2e"),
                        "status": "passed",
                    }
                ],
                "chaos_cases": [
                    {
                        "chaos_ref": "chaos",
                        "observed_ref": ref("chaos-observed"),
                        "receipt_ref": ref("chaos-receipt"),
                        "status": "passed",
                    }
                ],
                "independent_result_checks": [
                    {
                        "criterion_id": "c1",
                        "expected_ref": "oracle",
                        "observed_ref": "observed",
                        "receipt_ref": ref("actual-check"),
                        "status": "passed",
                    }
                ],
                "coverage_gaps": [],
            },
            issues_and_corrections={"findings": [], "blockers": []},
            outcome={
                "status": "verified",
                "user_visible_result_ref": "result",
                "criterion_results": [
                    {"criterion_id": "c1", "status": "passed", "evidence_ref": "e2e"}
                ],
            },
            manifest_binding={
                "task_id": "t1",
                "research_revision": 2,
                "plan_revision": 2,
                "scanner_identity": "stub-identity",
                "detector_identities": {"stub": "stub-identity"},
                "fixture_oracle_sha": "0" * 64,
                "oracle_revision": 1,
                "build_receipt_sha": "0" * 64,
            },
            handoff={
                "to": "complete",
                "ready": True,
                "completion_receipt_ref": ref("complete"),
                "validation_receipt_ref": ref("b-validation"),
            },
        )

    def check(self):
        return module.validate_records(self.r, self.p, self.b, self.refs.__contains__)

    def test_complete_records_with_external_evidence_resolver(self):
        self.assertEqual(self.check(), [])

    def test_no_resolver_fails_closed(self):
        self.assertTrue(
            any(
                "no evidence resolver" in e for e in module.validate_records(self.r, self.p, self.b)
            )
        )

    def test_empty_research_cannot_handoff(self):
        self.r["outputs"]["requirement_trace"] = []
        self.assertTrue(any("trace coverage" in e for e in self.check()))

    def test_unsupported_research_finding(self):
        self.r["search"]["findings"][0]["assessment"] = "uncertain"
        self.assertTrue(any("unsupported finding" in e for e in self.check()))

    def test_cross_stage_record_identity(self):
        self.p["research_input"]["record_id"] = "other"
        self.assertTrue(any("Research identity mismatch" in e for e in self.check()))

    def test_e2e_must_cover_planned_fixtures(self):
        self.p["fixture_validation_chaos"]["fixture_refs"].append("missing-fixture")
        self.assertTrue(any("planned fixtures not covered" in e for e in self.check()))

    def test_command_receipt_requires_evidence(self):
        self.b["execution"]["command_receipts"][0].pop("receipt_ref")
        self.assertTrue(any("build.command.c.receipt" in e for e in self.check()))

    def test_plan_scanner_result_stale_after_edit(self):
        self.p["revision"] = 3
        self.assertTrue(any("Scanner result stale" in e for e in self.check()))

    def test_scanner_not_called(self):
        self.p["gap_analysis"]["scanner_calls"] = []
        self.assertTrue(any("Scanner was not invoked" in e for e in self.check()))

    def test_missing_gap_fix_and_recheck(self):
        self.p["gap_analysis"]["findings"] = [
            {"id": "g1", "status": "resolved", "severity": "high"}
        ]
        messages = self.check()
        self.assertTrue(any("g1.fix" in e for e in messages))
        self.assertTrue(any("g1.recheck" in e for e in messages))

    def test_critical_deferral_forbidden(self):
        self.p["gap_analysis"]["findings"] = [
            {"id": "g1", "status": "deferred", "severity": "critical", "approval_ref": "approval"}
        ]
        self.assertTrue(any("critical finding deferred" in e for e in self.check()))

    def test_missing_chaos_preflight(self):
        self.p["fixture_validation_chaos"]["chaos_case_refs"] = []
        self.assertTrue(any("missing required chaos" in e for e in self.check()))

    def test_chaos_opt_out_requires_reason(self):
        f = self.p["fixture_validation_chaos"]
        f["chaos_applicability"] = "not_applicable"
        f["chaos_case_refs"] = []
        self.assertTrue(any("exclusion not justified" in e for e in self.check()))

    def test_no_actual_e2e(self):
        self.b["post_build_e2e"]["cases"] = []
        self.assertTrue(any("real E2E" in e for e in self.check()))

    def test_actual_user_result_not_checked(self):
        self.b["post_build_e2e"]["independent_result_checks"] = []
        self.assertTrue(any("actual user result" in e for e in self.check()))

    def test_stale_build_after_plan_change(self):
        self.p["revision"] += 1
        self.assertTrue(any("stale Plan" in e for e in self.check()))

    def test_uncertain_action_requires_reconciliation(self):
        self.b["checkpoint"]["action_state"] = "uncertain"
        self.b["checkpoint"]["retry_disposition"] = "safe_retry"
        errors = self.check()
        self.assertTrue(any("reconciled before retry" in e for e in errors))
        self.assertTrue(any("unfinished checkpoint" in e for e in errors))

    def test_stage_complete_cannot_disagree_with_handoff(self):
        self.r["handoff"]["ready"] = False
        self.assertTrue(any("must agree" in e for e in self.check()))

    def test_duplicate_requirements(self):
        self.r["purpose"]["accepted_requirements"].append(
            self.r["purpose"]["accepted_requirements"][0]
        )
        self.assertTrue(any("duplicate IDs" in e for e in self.check()))

    def test_file_evidence_sha_and_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            f = root / "receipt.txt"
            f.write_text("passed", encoding="utf-8")
            index = {
                "r": {"path": "receipt.txt", "sha256": hashlib.sha256(f.read_bytes()).hexdigest()}
            }
            resolver = module.evidence_index_resolver(index, root)
            self.assertTrue(resolver("r"))
            f.write_text("tampered", encoding="utf-8")
            self.assertFalse(resolver("r"))

    def test_file_evidence_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            digest = hashlib.sha256(b"anything").hexdigest()
            resolver = module.evidence_index_resolver(
                {"escape": {"path": "../outside", "sha256": digest}}, root
            )
            self.assertFalse(resolver("escape"))

    def test_template_draft_not_misreported_complete(self):
        # Templates parse as draft; do not count as actual execution proof.
        from_file = {
            "kind": "research",
            "contract_version": "1.1",
            "task_id": "<task_id>",
            "record_id": "<research_record_id>",
            "revision": 1,
            "status": "draft",
            "handoff": {"ready": False},
            "checkpoint": {"action_state": "none"},
        }
        errors = module.validate_records(from_file, self.p, self.b, self.refs.__contains__)
        self.assertTrue(any("missing task_id" in e or "downstream complete" in e for e in errors))


class PerStageValidationTest(unittest.TestCase):
    """Tests for per-stage validation functions (M1 extension)."""

    def setUp(self) -> None:
        self.refs: set[str] = set()

        def ref(v: str) -> str:
            self.refs.add(v)
            return v

        base = {
            "task_id": "t1",
            "revision": 2,
            "status": "complete",
            "updated_at": "2026-10-30T03:00:00Z",
            "progress_log": [{"at": "2026-10-30T03:00:00Z", "result": "done"}],
            "decision_log": [{"at": "2026-10-30T03:00:00Z", "why": "source-based"}],
        }
        cp = {
            "action_id": "a1",
            "action_state": "completed",
            "action_receipt_ref": ref("action"),
            "retry_disposition": "not_applicable",
            "source_snapshot_ref": ref("snapshot"),
        }
        self.r = dict(
            base,
            contract_version="1.1",
            kind="research",
            record_id="r1",
            checkpoint=cp,
            purpose={
                "user_outcome": "count",
                "accepted_requirements": [
                    {
                        "id": "R1",
                        "statement": "count",
                        "scope": "in_scope",
                        "authority_ref": ref("request"),
                    }
                ],
            },
            search={
                "todo_search_ref": ref("todo"),
                "sources": [
                    {
                        "id": "S1",
                        "location": "src.py",
                        "revision_or_hash": "sha",
                        "evidence_ref": ref("src-receipt"),
                    }
                ],
                "findings": [
                    {
                        "id": "F1",
                        "claim": "count",
                        "assessment": "supported",
                        "evidence_refs": [ref("source")],
                    }
                ],
            },
            outputs={
                "candidate_plan_ref": ref("candidate"),
                "fixture_refs": [ref("fixture")],
                "success_criteria_refs": [ref("criterion")],
                "requirement_trace": [
                    {
                        "requirement_id": "R1",
                        "finding_ids": ["F1"],
                        "fixture_ids": ["f1"],
                        "criterion_ids": ["c1"],
                    }
                ],
            },
            review={
                "coverage": "sufficient",
                "evidence_grounding": "passed",
                "disposition": "ready_for_plan",
                "unsupported_claims": [],
                "blockers": [],
                "unresolved_issues": [],
                "review_receipt_ref": ref("review"),
            },
            handoff={
                "to": "plan",
                "ready": True,
                "artifact_manifest_ref": ref("r-manifest"),
                "validation_receipt_ref": ref("r-val"),
            },
        )
        self.p = dict(
            base,
            contract_version="1.1",
            kind="plan",
            record_id="p1",
            checkpoint=cp,
            research_input={
                "record_ref": ref("r-record"),
                "record_id": "r1",
                "record_revision": 2,
                "artifact_manifest_ref": "r-manifest",
                "accepted_requirement_ids": ["R1"],
            },
            purpose={
                "user_outcome": "count",
                "acceptance_criteria": [
                    {
                        "id": "c1",
                        "requirement_id": "R1",
                        "expected_result": "3",
                        "oracle_ref": ref("oracle"),
                    }
                ],
            },
            implementation={
                "proposed_final_tree_ref": ref("tree"),
                "command_environment_ref": ref("env"),
                "rollback_or_recovery": "rerun",
                "milestones": [
                    {
                        "id": "m1",
                        "goal": "counter",
                        "steps": ["impl"],
                        "expected_observations": ["three"],
                    }
                ],
            },
            gap_analysis={
                "status": "resolved",
                "scanner_calls": [
                    {
                        "outcome": "passed",
                        "input_revision": 2,
                        "tool_ref": ref("scan-tool"),
                        "scope_ref": ref("scan-scope"),
                        "receipt_ref": ref("scan-receipt"),
                        "findings_ref": ref("scan-findings"),
                    }
                ],
                "findings": [],
                "unresolved_critical_ids": [],
            },
            fixture_validation_chaos={
                "status": "passed",
                "fixture_refs": ["fixture"],
                "oracle_evidence_refs": [ref("oracle-ev")],
                "chaos_applicability": "required",
                "chaos_case_refs": [ref("chaos")],
                "prebuild_validation_receipt_refs": [ref("fv-receipt")],
                "coverage_gaps": [],
            },
            handoff={
                "to": "build",
                "ready": True,
                "plan_artifact_ref": ref("execplan"),
                "artifact_manifest_ref": ref("p-manifest"),
                "validation_receipt_ref": ref("p-val"),
            },
        )

    def test_validate_research_alone_passes(self):
        errors = module.validate_research(self.r, self.refs.__contains__)
        self.assertEqual(errors, [])

    def test_validate_research_draft_no_receipt(self):
        r = dict(self.r, status="draft", handoff={"to": "plan", "ready": False})
        errors = module.validate_research(r, self.refs.__contains__)
        self.assertNotIn("research.handoff.validation_receipt_ref", " ".join(errors))

    def test_validate_research_preflight_skips_receipt(self):
        r = copy.deepcopy(self.r)
        r["handoff"].pop("validation_receipt_ref")
        # Full validation fails (missing receipt)
        errors = module.validate_research(r, self.refs.__contains__)
        self.assertTrue(any("validation_receipt_ref" in e for e in errors))
        # Preflight passes (receipt not required)
        errors = module.preflight_check(r, "research", self.refs.__contains__)
        self.assertEqual(errors, [])

    def test_validate_plan_with_research_passes(self):
        errors = module.validate_plan(self.p, self.r, self.refs.__contains__)
        self.assertEqual(errors, [])

    def test_validate_plan_without_research_passes_structure(self):
        errors = module.validate_plan(self.p, resolve=self.refs.__contains__)
        self.assertEqual(errors, [])

    def test_validate_plan_stale_research_revision(self):
        self.p["research_input"]["record_revision"] = 1
        errors = module.validate_plan(self.p, self.r, self.refs.__contains__)
        self.assertTrue(any("stale Research revision" in e for e in errors))

    def test_validate_plan_preflight_skips_receipt(self):
        p = copy.deepcopy(self.p)
        p["handoff"].pop("validation_receipt_ref")
        errors = module.preflight_check(p, "plan", self.refs.__contains__)
        self.assertEqual(errors, [])

    def test_malformed_record_research(self):
        errors = module.validate_research(None)
        self.assertTrue(any("not an object" in e for e in errors))

    def test_malformed_nested_section(self):
        r = copy.deepcopy(self.r)
        r["search"] = "not a dict"
        errors = module.validate_research(r, self.refs.__contains__)
        self.assertTrue(any("missing or malformed search" in e for e in errors))

    def test_preflight_unknown_stage(self):
        errors = module.preflight_check({}, "unknown")
        self.assertTrue(any("unknown stage" in e for e in errors))

    def test_validate_records_still_works(self):
        """Backward compatibility: validate_records still works with all three."""

        def ref(v):
            self.refs.add(v)
            return v

        b = dict(
            self.r,
            contract_version="1.1",
            kind="build",
            record_id="b1",
            checkpoint={
                "action_id": "a1",
                "action_state": "completed",
                "action_receipt_ref": ref("action"),
                "retry_disposition": "not_applicable",
                "source_snapshot_ref": ref("snapshot"),
            },
            plan_input={
                "record_ref": ref("p-record"),
                "record_id": "p1",
                "record_revision": 2,
                "artifact_manifest_ref": "p-manifest",
                "accepted_milestone_ids": ["m1"],
                "accepted_criterion_ids": ["c1"],
            },
            execution={
                "milestone_results": [
                    {"id": "m1", "status": "passed", "artifact_refs": [ref("result")]}
                ],
                "command_receipts": [
                    {
                        "id": "c",
                        "command": "py",
                        "cwd": "/tmp",
                        "exit_code": 0,
                        "receipt_ref": ref("receipt"),
                    }
                ],
                "workspace_snapshot_ref": ref("ws"),
                "environment_ref": "env",
                "finished_at": "2026-10-30T03:00:00Z",
                "artifact_manifest_ref": ref("b-manifest"),
            },
            implementation_validation={
                "status": "passed",
                "checks": [{"criterion_id": "c1", "status": "passed", "receipt_ref": ref("check")}],
            },
            post_build_e2e={
                "status": "passed",
                "real_entrypoint_ref": ref("entry"),
                "environment_ref": "env",
                "cases": [
                    {
                        "fixture_ref": "fixture",
                        "expected_ref": "oracle",
                        "observed_ref": ref("obs"),
                        "receipt_ref": ref("e2e"),
                        "status": "passed",
                    }
                ],
                "chaos_cases": [
                    {
                        "chaos_ref": "chaos",
                        "observed_ref": ref("cobs"),
                        "receipt_ref": ref("crec"),
                        "status": "passed",
                    }
                ],
                "independent_result_checks": [
                    {
                        "criterion_id": "c1",
                        "expected_ref": "oracle",
                        "observed_ref": "obs",
                        "receipt_ref": ref("acheck"),
                        "status": "passed",
                    }
                ],
                "coverage_gaps": [],
            },
            issues_and_corrections={"findings": [], "blockers": []},
            outcome={
                "status": "verified",
                "user_visible_result_ref": "result",
                "criterion_results": [
                    {"criterion_id": "c1", "status": "passed", "evidence_ref": "e2e"}
                ],
            },
            manifest_binding={
                "task_id": "t1",
                "research_revision": 2,
                "plan_revision": 2,
                "scanner_identity": "stub-identity",
                "detector_identities": {"stub": "stub-identity"},
                "fixture_oracle_sha": "0" * 64,
                "oracle_revision": 1,
                "build_receipt_sha": "0" * 64,
            },
            handoff={
                "to": "complete",
                "ready": True,
                "completion_receipt_ref": ref("complete"),
                "validation_receipt_ref": ref("b-val"),
            },
        )
        errors = module.validate_records(self.r, self.p, b, self.refs.__contains__)
        self.assertEqual(errors, [])

    def test_validate_build_alone_passes(self):
        """validate_build standalone with plan+research passes."""

        def ref(v):
            self.refs.add(v)
            return v

        b = dict(
            self.r,
            contract_version="1.1",
            kind="build",
            record_id="b1",
            checkpoint=copy.deepcopy(self.r["checkpoint"]),
            plan_input={
                "record_ref": ref("p-record"),
                "record_id": "p1",
                "record_revision": 2,
                "artifact_manifest_ref": "p-manifest",
                "accepted_milestone_ids": ["m1"],
                "accepted_criterion_ids": ["c1"],
            },
            execution={
                "milestone_results": [
                    {"id": "m1", "status": "passed", "artifact_refs": [ref("result")]}
                ],
                "command_receipts": [
                    {
                        "id": "c",
                        "command": "py",
                        "cwd": "/tmp",
                        "exit_code": 0,
                        "receipt_ref": ref("receipt"),
                    }
                ],
                "workspace_snapshot_ref": ref("ws"),
                "environment_ref": "env",
                "finished_at": "2026-10-30T03:00:00Z",
                "artifact_manifest_ref": ref("b-manifest"),
            },
            implementation_validation={
                "status": "passed",
                "checks": [{"criterion_id": "c1", "status": "passed", "receipt_ref": ref("check")}],
            },
            post_build_e2e={
                "status": "passed",
                "real_entrypoint_ref": ref("entry"),
                "environment_ref": "env",
                "cases": [
                    {
                        "fixture_ref": "fixture",
                        "expected_ref": "oracle",
                        "observed_ref": ref("obs"),
                        "receipt_ref": ref("e2e"),
                        "status": "passed",
                    }
                ],
                "chaos_cases": [
                    {
                        "chaos_ref": "chaos",
                        "observed_ref": ref("cobs"),
                        "receipt_ref": ref("crec"),
                        "status": "passed",
                    }
                ],
                "independent_result_checks": [
                    {
                        "criterion_id": "c1",
                        "expected_ref": "oracle",
                        "observed_ref": "obs",
                        "receipt_ref": ref("acheck"),
                        "status": "passed",
                    }
                ],
                "coverage_gaps": [],
            },
            issues_and_corrections={"findings": [], "blockers": []},
            outcome={
                "status": "verified",
                "user_visible_result_ref": "result",
                "criterion_results": [
                    {"criterion_id": "c1", "status": "passed", "evidence_ref": "e2e"}
                ],
            },
            manifest_binding={
                "task_id": "t1",
                "research_revision": 2,
                "plan_revision": 2,
                "scanner_identity": "stub-identity",
                "detector_identities": {"stub": "stub-identity"},
                "fixture_oracle_sha": "0" * 64,
                "oracle_revision": 1,
                "build_receipt_sha": "0" * 64,
            },
            handoff={
                "to": "complete",
                "ready": True,
                "completion_receipt_ref": ref("complete"),
                "validation_receipt_ref": ref("b-val"),
            },
        )
        errors = module.validate_build(b, self.p, self.r, self.refs.__contains__)
        self.assertEqual(errors, [])

    def test_validate_build_stale_plan_revision(self):
        """validate_build detects stale Plan revision."""

        def ref(v):
            self.refs.add(v)
            return v

        b = dict(
            self.r,
            contract_version="1.1",
            kind="build",
            record_id="b1",
            checkpoint=copy.deepcopy(self.r["checkpoint"]),
            plan_input={
                "record_ref": ref("p-record"),
                "record_id": "p1",
                "record_revision": 1,  # stale!
                "artifact_manifest_ref": "p-manifest",
                "accepted_milestone_ids": ["m1"],
                "accepted_criterion_ids": ["c1"],
            },
            execution={
                "milestone_results": [
                    {"id": "m1", "status": "passed", "artifact_refs": [ref("result")]}
                ],
                "command_receipts": [
                    {
                        "id": "c",
                        "command": "py",
                        "cwd": "/tmp",
                        "exit_code": 0,
                        "receipt_ref": ref("receipt"),
                    }
                ],
                "workspace_snapshot_ref": ref("ws"),
                "environment_ref": "env",
                "finished_at": "2026-10-30T03:00:00Z",
                "artifact_manifest_ref": ref("b-manifest"),
            },
            implementation_validation={
                "status": "passed",
                "checks": [{"criterion_id": "c1", "status": "passed", "receipt_ref": ref("check")}],
            },
            post_build_e2e={
                "status": "passed",
                "real_entrypoint_ref": ref("entry"),
                "environment_ref": "env",
                "cases": [
                    {
                        "fixture_ref": "fixture",
                        "expected_ref": "oracle",
                        "observed_ref": ref("obs"),
                        "receipt_ref": ref("e2e"),
                        "status": "passed",
                    }
                ],
                "chaos_cases": [
                    {
                        "chaos_ref": "chaos",
                        "observed_ref": ref("cobs"),
                        "receipt_ref": ref("crec"),
                        "status": "passed",
                    }
                ],
                "independent_result_checks": [
                    {
                        "criterion_id": "c1",
                        "expected_ref": "oracle",
                        "observed_ref": "obs",
                        "receipt_ref": ref("acheck"),
                        "status": "passed",
                    }
                ],
                "coverage_gaps": [],
            },
            issues_and_corrections={"findings": [], "blockers": []},
            outcome={
                "status": "verified",
                "user_visible_result_ref": "result",
                "criterion_results": [
                    {"criterion_id": "c1", "status": "passed", "evidence_ref": "e2e"}
                ],
            },
            manifest_binding={
                "task_id": "t1",
                "research_revision": 2,
                "plan_revision": 2,
                "scanner_identity": "stub-identity",
                "detector_identities": {"stub": "stub-identity"},
                "fixture_oracle_sha": "0" * 64,
                "oracle_revision": 1,
                "build_receipt_sha": "0" * 64,
            },
            handoff={
                "to": "complete",
                "ready": True,
                "completion_receipt_ref": ref("complete"),
                "validation_receipt_ref": ref("b-val"),
            },
        )
        errors = module.validate_build(b, self.p, self.r, self.refs.__contains__)
        self.assertTrue(any("stale Plan revision" in e for e in errors))

    def test_validate_build_preflight_skips_receipt(self):
        """preflight_check for build skips validation_receipt_ref."""

        def ref(v):
            self.refs.add(v)
            return v

        b = dict(
            self.r,
            contract_version="1.1",
            kind="build",
            record_id="b1",
            checkpoint=copy.deepcopy(self.r["checkpoint"]),
            plan_input={
                "record_ref": ref("p-record"),
                "record_id": "p1",
                "record_revision": 2,
                "artifact_manifest_ref": "p-manifest",
                "accepted_milestone_ids": ["m1"],
                "accepted_criterion_ids": ["c1"],
            },
            execution={
                "milestone_results": [
                    {"id": "m1", "status": "passed", "artifact_refs": [ref("result")]}
                ],
                "command_receipts": [
                    {
                        "id": "c",
                        "command": "py",
                        "cwd": "/tmp",
                        "exit_code": 0,
                        "receipt_ref": ref("receipt"),
                    }
                ],
                "workspace_snapshot_ref": ref("ws"),
                "environment_ref": "env",
                "finished_at": "2026-10-30T03:00:00Z",
                "artifact_manifest_ref": ref("b-manifest"),
            },
            implementation_validation={
                "status": "passed",
                "checks": [{"criterion_id": "c1", "status": "passed", "receipt_ref": ref("check")}],
            },
            post_build_e2e={
                "status": "passed",
                "real_entrypoint_ref": ref("entry"),
                "environment_ref": "env",
                "cases": [
                    {
                        "fixture_ref": "fixture",
                        "expected_ref": "oracle",
                        "observed_ref": ref("obs"),
                        "receipt_ref": ref("e2e"),
                        "status": "passed",
                    }
                ],
                "chaos_cases": [
                    {
                        "chaos_ref": "chaos",
                        "observed_ref": ref("cobs"),
                        "receipt_ref": ref("crec"),
                        "status": "passed",
                    }
                ],
                "independent_result_checks": [
                    {
                        "criterion_id": "c1",
                        "expected_ref": "oracle",
                        "observed_ref": "obs",
                        "receipt_ref": ref("acheck"),
                        "status": "passed",
                    }
                ],
                "coverage_gaps": [],
            },
            issues_and_corrections={"findings": [], "blockers": []},
            outcome={
                "status": "verified",
                "user_visible_result_ref": "result",
                "criterion_results": [
                    {"criterion_id": "c1", "status": "passed", "evidence_ref": "e2e"}
                ],
            },
            manifest_binding={
                "task_id": "t1",
                "research_revision": 2,
                "plan_revision": 2,
                "scanner_identity": "stub-identity",
                "detector_identities": {"stub": "stub-identity"},
                "fixture_oracle_sha": "0" * 64,
                "oracle_revision": 1,
                "build_receipt_sha": "0" * 64,
            },
            handoff={"to": "complete", "ready": True, "completion_receipt_ref": ref("complete")},
        )
        # Note: no validation_receipt_ref — preflight should skip it
        errors = module.preflight_check(b, "build", self.refs.__contains__)
        self.assertEqual(errors, [])

    def test_validate_build_without_plan_returns_base_only(self):
        """validate_build without plan returns early (base checks only)."""
        errors = module.validate_build(self.r, None, None, self.refs.__contains__)
        # self.r is a research record, not a build record, so it should have kind mismatch
        self.assertTrue(any("kind mismatch" in e for e in errors))

    def test_validate_build_missing_e2e_cases(self):
        """validate_build catches missing E2E cases."""

        def ref(v):
            self.refs.add(v)
            return v

        b = dict(
            self.r,
            contract_version="1.1",
            kind="build",
            record_id="b1",
            checkpoint=copy.deepcopy(self.r["checkpoint"]),
            plan_input={
                "record_ref": ref("p-record"),
                "record_id": "p1",
                "record_revision": 2,
                "artifact_manifest_ref": "p-manifest",
                "accepted_milestone_ids": ["m1"],
                "accepted_criterion_ids": ["c1"],
            },
            execution={
                "milestone_results": [
                    {"id": "m1", "status": "passed", "artifact_refs": [ref("result")]}
                ],
                "command_receipts": [
                    {
                        "id": "c",
                        "command": "py",
                        "cwd": "/tmp",
                        "exit_code": 0,
                        "receipt_ref": ref("receipt"),
                    }
                ],
                "workspace_snapshot_ref": ref("ws"),
                "environment_ref": "env",
                "finished_at": "2026-10-30T03:00:00Z",
                "artifact_manifest_ref": ref("b-manifest"),
            },
            implementation_validation={
                "status": "passed",
                "checks": [{"criterion_id": "c1", "status": "passed", "receipt_ref": ref("check")}],
            },
            post_build_e2e={
                "status": "passed",
                "real_entrypoint_ref": ref("entry"),
                "environment_ref": "env",
                "cases": [],  # Empty — should fail
                "chaos_cases": [],
                "independent_result_checks": [],
                "coverage_gaps": [],
            },
            issues_and_corrections={"findings": [], "blockers": []},
            outcome={
                "status": "verified",
                "user_visible_result_ref": "result",
                "criterion_results": [
                    {"criterion_id": "c1", "status": "passed", "evidence_ref": "e2e"}
                ],
            },
            manifest_binding={
                "task_id": "t1",
                "research_revision": 2,
                "plan_revision": 2,
                "scanner_identity": "stub-identity",
                "detector_identities": {"stub": "stub-identity"},
                "fixture_oracle_sha": "0" * 64,
                "oracle_revision": 1,
                "build_receipt_sha": "0" * 64,
            },
            handoff={
                "to": "complete",
                "ready": True,
                "completion_receipt_ref": ref("complete"),
                "validation_receipt_ref": ref("b-val"),
            },
        )
        errors = module.validate_build(b, self.p, self.r, self.refs.__contains__)
        self.assertTrue(any("real E2E" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
