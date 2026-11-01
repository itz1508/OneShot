"""Composition fixtures for the five-scenario acceptance suite.

Factored out of the baseline ``tests/test_workflow_contracts.ContractTest`` so
decision / scenario tests can reuse the "known-valid Research+Plan+Build triple"
WITHOUT subclassing (which would re-collect every baseline test under every
subclass and inflate the test count).
"""

from __future__ import annotations

import copy
from typing import Any


def make_valid_triple() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], set[str]]:
    """Return a fresh (research, plan, build, refs) triple that validates clean.

    The ``refs`` set is populated with every evidence reference used in the
    triple so callers can pass ``refs.__contains__`` as the resolver to
    ``validate_pipeline`` / ``validate_records``.

    All four values are independent per call — tests may mutate them freely.
    """

    refs: set[str] = set()

    def ref(v: str) -> str:
        refs.add(v)
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

    research = dict(
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

    plan = dict(
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

    build = dict(
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
            "checks": [{"criterion_id": "c1", "status": "passed", "receipt_ref": ref("unit-test")}],
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
        handoff={
            "to": "complete",
            "ready": True,
            "completion_receipt_ref": ref("complete"),
            "validation_receipt_ref": ref("b-validation"),
        },
    )

    return research, plan, build, refs
