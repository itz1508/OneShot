"""Connected handoff tests for the OneShot contract migration.

Covers:
- PlanningRecord (kind:planning) validates with new fields
- Legacy PlanRecord (kind:plan) still validates (backward compat)
- AuditRecord typed outcomes (SELECT/UPDATE/BLOCK/REJECT)
- AuditRecord with open blocker findings cannot produce SELECT
- BuildAdmission rejects BLOCK/REJECT dispositions
- BuildAdmission rejects unresolved blockers
- BuildAdmission rejects non-passed fixture/chaos
- BuildAdmission requires admission_receipt_ref
- Criterion ID propagation Research -> Planning in validate_pipeline
- Missing criterion IDs flagged in validate_pipeline
- Inline success_criteria field-presence validation
- Full SuccessCriteria artifact validation in validate_pipeline
- PlanningRecord accepts kind:plan for legacy compat
- AuditRecord target identity binding
- Audit rubric score threshold enforcement
"""
import sys
from pathlib import Path

_CONTRACTS = Path(__file__).resolve().parent.parent / "agent" / "contracts"
if str(_CONTRACTS) not in sys.path:
    sys.path.insert(0, str(_CONTRACTS))

import pytest
from models import (
    AuditFinding,
    AuditOutcome,
    AuditRecord,
    AuditRubric,
    AuditRubricCheck,
    AuditTarget,
    AuthorizedTool,
    BuildAdmission,
    PlanningRecord,
    PlanRecord,
    validate_pipeline,
    validate_success_criteria_artifact,
)


def _base_planning_data():
    """Minimal valid PlanningRecord dict."""
    return {
        "kind": "planning",
        "task_id": "task-001",
        "record_id": "plan-001",
        "revision": 1,
        "status": "draft",
        "updated_at": "2026-01-01T00:00:00Z",
        "research_input": {
            "record_ref": "research-001",
            "record_id": "research-001",
            "record_revision": 1,
            "artifact_manifest_ref": "agent/contracts/research.yaml",
            "accepted_requirement_ids": ["R1"],
            "accepted_criterion_ids": ["c1"],
        },
        "todos": [
            {
                "todo_id": "t1",
                "requirement_ids": ["R1"],
                "action": "implement",
                "target_paths": ["bin/context_counter.py"],
                "depends_on": [],
                "criterion_ids": ["c1"],
                "validation": {"method": "e2e", "expected": "counts match"},
            }
        ],
        "purpose": {
            "user_outcome": "count characters",
            "acceptance_criteria": [
                {"id": "c1", "requirement_id": "R1", "expected_result": "counts", "oracle_ref": "AGENTS.md"}
            ],
            "assumptions": [],
            "constraints": [],
        },
        "implementation": {
            "proposed_final_tree_ref": None,
            "file_actions": [],
            "milestones": [
                {"id": "m1", "goal": "build", "files": ["bin/context_counter.py"], "steps": ["implement"], "commands": [], "expected_observations": ["3"], "status": "not_started"}
            ],
            "dependencies": [],
            "command_environment_ref": None,
            "rollback_or_recovery": "revert to last commit",
        },
        "gap_analysis": {
            "status": "resolved",
            "scanner_calls": [{"at": "2026-01-01T00:00:00Z", "tool_ref": "scanner", "scope_ref": "AGENTS.md", "input_revision": 1, "findings_ref": None, "receipt_ref": "AGENTS.md", "outcome": "passed", "scanner_identity": "a" * 64}],
            "findings": [],
            "unresolved_critical_ids": [],
            "last_recheck_ref": None,
        },
        "fixture_validation_chaos": {
            "status": "passed",
            "fixture_refs": ["bin/context_counter.py"],
            "oracle_evidence_refs": ["AGENTS.md"],
            "chaos_applicability": "not_applicable",
            "chaos_case_refs": [],
            "chaos_exclusion_reason": "deterministic",
            "prebuild_validation_receipt_refs": ["AGENTS.md"],
            "coverage_gaps": [],
        },
        "build_admission": None,
        "claim_decisions": [],
        "progress_log": [],
        "decision_log": [],
        "checkpoint": {
            "last_completed_step": None,
            "next_step": None,
            "action_id": None,
            "action_state": "none",
            "action_receipt_ref": None,
            "retry_disposition": "not_applicable",
            "source_snapshot_ref": None,
            "resume_notes": None,
        },
        "handoff": {"to": "build", "ready": False},
    }


def _base_audit_data():
    """Minimal valid AuditRecord dict."""
    return {
        "kind": "audit",
        "task_id": "task-001",
        "audit_id": "audit-001",
        "audit_revision": 1,
        "status": "complete",
        "updated_at": "2026-01-01T00:00:00Z",
        "target": {
            "output_id": "out-001",
            "source_output_id": "src-001",
            "input_id": "in-001",
            "target_kind": "research",
            "target_record_id": "research-001",
            "target_revision": 1,
            "source_snapshot_ref": "AGENTS.md",
        },
        "rubric": {
            "version": "1.0",
            "checks": [
                {"check_id": "ck1", "description": "coverage", "weight": 1.0, "required": True, "evidence_type": "validation"}
            ],
            "score_range": {"min": 0, "max": 100},
            "selection_threshold": 80,
            "required_checks": ["ck1"],
        },
        "findings": [],
        "outcome": "SELECT",
        "outcome_reason": "all checks passed",
        "outcome_score": 95,
        "receipts": [{"ref": "AGENTS.md", "type": "validation", "sha256": "a" * 64, "at": "2026-01-01T00:00:00Z"}],
        "auditor_ref": "auditor-agent",
        "audit_receipt_ref": "AGENTS.md",
        "progress_log": [],
    }


# --- PlanningRecord tests ---

class TestPlanningRecord:
    def test_valid_planning_record(self):
        data = _base_planning_data()
        rec = PlanningRecord.model_validate(data)
        assert rec.kind == "planning"
        assert len(rec.todos) == 1
        assert rec.todos[0].criterion_ids == ["c1"]

    def test_legacy_kind_plan_accepted(self):
        data = _base_planning_data()
        data["kind"] = "plan"
        rec = PlanningRecord.model_validate(data)
        assert rec.kind == "plan"

    def test_build_admission_valid(self):
        data = _base_planning_data()
        data["build_admission"] = {
            "receipt_ref": "receipt-001",
            "accepted_plan_revision": 1,
            "audit_disposition": "SELECT",
            "fixture_chaos_status": "passed",
            "unresolved_blockers": [],
            "authorized_tools": [{"tool_id": "shell", "version": "1.0", "allowed_paths": ["bin/"]}],
            "accepted_criterion_ids": ["c1"],
            "admission_receipt_ref": "admission-001",
        }
        rec = PlanningRecord.model_validate(data)
        assert rec.build_admission is not None
        assert rec.build_admission.audit_disposition == "SELECT"

    def test_build_admission_rejects_block(self):
        data = _base_planning_data()
        data["build_admission"] = {
            "accepted_plan_revision": 1,
            "audit_disposition": "BLOCK",
            "fixture_chaos_status": "passed",
            "unresolved_blockers": [],
            "admission_receipt_ref": "adm-001",
        }
        with pytest.raises(Exception, match="BLOCK"):
            PlanningRecord.model_validate(data)

    def test_build_admission_rejects_unresolved_blockers(self):
        data = _base_planning_data()
        data["build_admission"] = {
            "accepted_plan_revision": 1,
            "audit_disposition": "SELECT",
            "fixture_chaos_status": "passed",
            "unresolved_blockers": ["gap-001"],
            "admission_receipt_ref": "adm-001",
        }
        with pytest.raises(Exception, match="unresolved blockers"):
            PlanningRecord.model_validate(data)

    def test_build_admission_rejects_failed_fixture(self):
        data = _base_planning_data()
        data["build_admission"] = {
            "accepted_plan_revision": 1,
            "audit_disposition": "SELECT",
            "fixture_chaos_status": "failed",
            "unresolved_blockers": [],
            "admission_receipt_ref": "adm-001",
        }
        with pytest.raises(Exception, match="fixture/chaos"):
            PlanningRecord.model_validate(data)

    def test_build_admission_requires_receipt_ref(self):
        data = _base_planning_data()
        data["build_admission"] = {
            "accepted_plan_revision": 1,
            "audit_disposition": "SELECT",
            "fixture_chaos_status": "passed",
            "unresolved_blockers": [],
            "admission_receipt_ref": None,
        }
        with pytest.raises(Exception, match="admission_receipt_ref"):
            PlanningRecord.model_validate(data)


# --- AuditRecord tests ---

class TestAuditRecord:
    def test_valid_select_audit(self):
        rec = AuditRecord.model_validate(_base_audit_data())
        assert rec.outcome == AuditOutcome.SELECT
        assert rec.outcome_score == 95

    def test_update_outcome(self):
        data = _base_audit_data()
        data["outcome"] = "UPDATE"
        data["outcome_score"] = 60
        rec = AuditRecord.model_validate(data)
        assert rec.outcome == AuditOutcome.UPDATE

    def test_block_outcome(self):
        data = _base_audit_data()
        data["outcome"] = "BLOCK"
        data["outcome_reason"] = "critical failure"
        rec = AuditRecord.model_validate(data)
        assert rec.outcome == AuditOutcome.BLOCK

    def test_reject_outcome(self):
        data = _base_audit_data()
        data["outcome"] = "REJECT"
        data["outcome_reason"] = "invalid"
        rec = AuditRecord.model_validate(data)
        assert rec.outcome == AuditOutcome.REJECT

    def test_select_blocked_by_open_blocker_finding(self):
        data = _base_audit_data()
        data["findings"] = [
            {"id": "f1", "check_id": "ck1", "severity": "blocker", "description": "missing", "evidence_refs": [], "recommendation": "fix", "status": "open"}
        ]
        data["outcome"] = "SELECT"
        with pytest.raises(Exception, match="open blocker"):
            AuditRecord.model_validate(data)

    def test_select_below_threshold(self):
        data = _base_audit_data()
        data["outcome"] = "SELECT"
        data["outcome_score"] = 70
        data["rubric"]["selection_threshold"] = 80
        with pytest.raises(Exception, match="below selection threshold"):
            AuditRecord.model_validate(data)

    def test_select_with_resolved_blocker_ok(self):
        data = _base_audit_data()
        data["findings"] = [
            {"id": "f1", "check_id": "ck1", "severity": "blocker", "description": "was missing", "evidence_refs": [], "recommendation": "fixed", "status": "resolved"}
        ]
        data["outcome"] = "SELECT"
        data["outcome_score"] = 90
        rec = AuditRecord.model_validate(data)
        assert rec.outcome == AuditOutcome.SELECT

    def test_target_identity_binding(self):
        rec = AuditRecord.model_validate(_base_audit_data())
        assert rec.target.output_id == "out-001"
        assert rec.target.target_record_id == "research-001"
        assert rec.target.target_revision == 1

    def test_placeholder_task_id_rejected(self):
        data = _base_audit_data()
        data["task_id"] = "<task_id>"
        with pytest.raises(Exception, match="placeholder"):
            AuditRecord.model_validate(data)


# --- Criterion propagation in validate_pipeline ---

class TestCriterionPropagation:
    def _base_pipeline(self):
        """Minimal R/P/B dicts for validate_pipeline."""
        research = {
            "kind": "research",
            "task_id": "task-001",
            "record_id": "research-001",
            "revision": 1,
            "status": "complete",
            "updated_at": "2026-01-01T00:00:00Z",
            "input": {"task_id": "task-001", "objective": "count", "constraints": [], "assumptions": []},
            "search": {"sources": [], "findings": []},
            "purpose": {
                "user_outcome": "count chars",
                "accepted_requirements": [{"id": "R1", "scope": "in_scope", "statement": "count"}],
            },
            "outputs": {
                "evidence_refs": ["AGENTS.md"],
                "candidate_plan_ref": None,
                "fixture_refs": [],
                "success_criteria_refs": [],
                "success_criteria": [
                    {"criterion_id": "c1", "statement": "counts match", "observable_outcome": "correct", "priority": "must", "required_evidence_types": ["e2e"], "pass_condition": "match", "fail_condition": "mismatch", "insufficient_evidence_disposition": "block"}
                ],
                "requirement_trace": [{"requirement_id": "R1", "finding_ids": [], "fixture_ids": [], "criterion_ids": ["c1"], "disposition": "covered"}],
            },
            "review": {"supported_claims": [], "unsupported_claims": [], "unresolved_issues": [], "blockers": [], "disposition": "ready_for_plan", "review_receipt_ref": "AGENTS.md"},
            "progress_log": [{"at": "2026-01-01T00:00:00Z", "step": "s", "result": "ok", "evidence_ref": "AGENTS.md", "next_step": "plan"}],
            "decision_log": [{"at": "2026-01-01T00:00:00Z", "decision": "Proceed", "why": "ok", "evidence_refs": ["AGENTS.md"], "impact": "plan"}],
            "checkpoint": {"last_completed_step": "s", "next_step": "plan", "action_id": "r1", "action_state": "completed", "action_receipt_ref": "AGENTS.md", "retry_disposition": "not_applicable", "source_snapshot_ref": "AGENTS.md", "resume_notes": None},
            "handoff": {"to": "plan", "ready": True, "artifact_manifest_ref": "agent/contracts/research.yaml", "validation_receipt_ref": "AGENTS.md"},
        }
        plan = {
            "kind": "plan",
            "task_id": "task-001",
            "record_id": "plan-001",
            "revision": 1,
            "status": "complete",
            "updated_at": "2026-01-01T00:00:00Z",
            "research_input": {
                "record_ref": "research-001",
                "record_id": "research-001",
                "record_revision": 1,
                "artifact_manifest_ref": "agent/contracts/research.yaml",
                "accepted_requirement_ids": ["R1"],
                "accepted_criterion_ids": ["c1"],
            },
            "purpose": {"user_outcome": "count chars", "acceptance_criteria": [{"id": "c1", "requirement_id": "R1", "expected_result": "counts", "oracle_ref": "AGENTS.md"}], "assumptions": [], "constraints": []},
            "implementation": {"proposed_final_tree_ref": None, "file_actions": [], "milestones": [{"id": "m1", "goal": "build", "files": ["bin/context_counter.py"], "steps": ["implement"], "commands": [], "expected_observations": ["3"], "status": "complete"}], "dependencies": [], "command_environment_ref": None, "rollback_or_recovery": "revert to last commit"},
            "gap_analysis": {"status": "resolved", "scanner_calls": [{"at": "2026-01-01T00:00:00Z", "tool_ref": "scanner", "scope_ref": "AGENTS.md", "input_revision": 1, "findings_ref": None, "receipt_ref": "AGENTS.md", "outcome": "passed", "scanner_identity": "a" * 64}], "findings": [], "unresolved_critical_ids": [], "last_recheck_ref": None},
            "fixture_validation_chaos": {"status": "passed", "fixture_refs": ["bin/context_counter.py"], "oracle_evidence_refs": ["AGENTS.md"], "chaos_applicability": "not_applicable", "chaos_case_refs": [], "chaos_exclusion_reason": "deterministic", "prebuild_validation_receipt_refs": ["AGENTS.md"], "coverage_gaps": []},
            "claim_decisions": [],
            "progress_log": [{"at": "2026-01-01T00:00:00Z", "step": "p", "result": "ok", "evidence_ref": "AGENTS.md", "next_step": "build"}],
            "decision_log": [{"at": "2026-01-01T00:00:00Z", "decision": "proceed", "why": "ok", "evidence_refs": ["AGENTS.md"], "impact": "build"}],
            "checkpoint": {"last_completed_step": "p", "next_step": "build", "action_id": "p1", "action_state": "completed", "action_receipt_ref": "AGENTS.md", "retry_disposition": "not_applicable", "source_snapshot_ref": "AGENTS.md", "resume_notes": None},
            "handoff": {"to": "build", "ready": True, "plan_artifact_ref": "AGENTS.md", "artifact_manifest_ref": "agent/contracts/plan.yaml", "validation_receipt_ref": "AGENTS.md"},
        }
        build = {
            "kind": "build",
            "task_id": "task-001",
            "record_id": "build-001",
            "revision": 1,
            "status": "complete",
            "updated_at": "2026-01-01T00:00:00Z",
            "plan_input": {"record_ref": "plan-001", "record_id": "plan-001", "record_revision": 1, "artifact_manifest_ref": "agent/contracts/plan.yaml", "accepted_milestone_ids": ["m1"], "accepted_criterion_ids": ["c1"]},
            "build_admission_ref": "plan-001",
            "audit_refs": [],
            "execution": {"workspace_snapshot_ref": "AGENTS.md", "environment_ref": "serverless", "command_receipts": [{"id": "cmd1", "command": "python bin/context_counter.py", "cwd": ".", "label": "normal", "exit_code": 0, "stdout": "3", "stderr": "", "receipt_ref": "AGENTS.md", "at": "2026-01-01T00:00:00Z"}]},
            "implementation_validation": {"status": "passed", "checks": [{"criterion_id": "c1", "method": "e2e", "expected": "counts", "observed": "3", "receipt_ref": "AGENTS.md", "status": "passed"}], "regressions": []},
            "post_build_e2e": {"status": "passed", "real_entrypoint_ref": "bin/context_counter.py", "environment_ref": "serverless", "cases": [{"fixture_ref": "bin/context_counter.py", "expected_ref": "AGENTS.md", "observed_ref": "AGENTS.md", "receipt_ref": "AGENTS.md", "status": "passed"}], "chaos_cases": [], "independent_result_checks": [{"criterion_id": "c1", "expected_ref": "AGENTS.md", "observed_ref": "AGENTS.md", "receipt_ref": "AGENTS.md", "status": "passed"}]},
            "issues_and_corrections": {"status": "none", "items": []},
            "outcome": {"status": "verified", "user_visible_result_ref": "AGENTS.md", "evidence_refs": ["AGENTS.md"]},
            "manifest_binding": {"task_id": "task-001", "research_revision": 1, "plan_revision": 1, "scanner_identity": "a" * 64, "detector_identities": {"scanner": "a" * 64}, "fixture_oracle_sha": "b" * 64, "oracle_revision": 1, "build_receipt_sha": "c" * 64},
            "progress_log": [{"at": "2026-01-01T00:00:00Z", "step": "b", "result": "ok", "evidence_ref": "AGENTS.md", "next_step": "complete"}],
            "decision_log": [{"at": "2026-01-01T00:00:00Z", "decision": "done", "why": "ok", "evidence_refs": ["AGENTS.md"], "impact": "complete"}],
            "checkpoint": {"last_completed_step": "b", "next_step": "complete", "action_id": "b1", "action_state": "completed", "action_receipt_ref": "AGENTS.md", "retry_disposition": "not_applicable", "source_snapshot_ref": "AGENTS.md", "resume_notes": None},
            "handoff": {"to": "complete", "ready": True, "completion_receipt_ref": "AGENTS.md", "validation_receipt_ref": "AGENTS.md"},
        }
        return research, plan, build

    def test_criterion_propagation_valid(self):
        r, p, b = self._base_pipeline()
        errors = validate_pipeline(r, p, b, resolve=lambda ref: True)
        assert not any("criterion IDs" in e for e in errors), f"Unexpected criterion error: {errors}"

    def test_missing_criterion_ids_flagged(self):
        r, p, b = self._base_pipeline()
        p["research_input"]["accepted_criterion_ids"] = ["c2"]  # missing c1
        errors = validate_pipeline(r, p, b, resolve=lambda ref: True)
        assert any("missing criterion IDs" in e for e in errors), f"Expected criterion error: {errors}"

    def test_inline_criteria_missing_criterion_id(self):
        r, p, b = self._base_pipeline()
        r["outputs"]["success_criteria"] = [{"statement": "test", "observable_outcome": "x"}]
        errors = validate_pipeline(r, p, b, resolve=lambda ref: True)
        assert any("missing criterion_id" in e for e in errors)

    def test_inline_criteria_missing_statement(self):
        r, p, b = self._base_pipeline()
        r["outputs"]["success_criteria"] = [{"criterion_id": "cX"}]
        errors = validate_pipeline(r, p, b, resolve=lambda ref: True)
        assert any("missing statement" in e for e in errors)

    def test_planning_record_accepted_in_pipeline(self):
        r, p, b = self._base_pipeline()
        p["kind"] = "planning"
        p["todos"] = [{"todo_id": "t1", "requirement_ids": ["R1"], "criterion_ids": ["c1"], "validation": {"method": "e2e", "expected": "match"}}]
        errors = validate_pipeline(r, p, b, resolve=lambda ref: True)
        # Planning kind should not produce a 'kind' rejection error
        kind_errors = [e for e in errors if "kind" in e.lower() and "should be" in e.lower()]
        assert not kind_errors, f"Planning kind rejected: {kind_errors}"

    def test_legacy_plan_kind_still_works(self):
        r, p, b = self._base_pipeline()
        errors = validate_pipeline(r, p, b, resolve=lambda ref: True)
        kind_errors = [e for e in errors if "kind" in e.lower() and "should be" in e.lower()]
        assert not kind_errors, f"Legacy plan kind rejected: {kind_errors}"