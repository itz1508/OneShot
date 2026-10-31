"""Validate OneShot Research/Plan/Build records and their handoffs.

This is a library/CLI for checking existing task records, not a controller,
Scanner, host hook, or persistence implementation. No writes or tool calls.
Python 3.11+. Runtime YAML input requires PyYAML; JSON also works without it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

Record = dict[str, Any]
EvidenceCheck = Callable[[str], bool]


def _filled(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and not value.strip().startswith("<")


def _ids(rows: Any) -> list[str]:
    return [row.get("id") for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _index(rows: Any, key: str = "id") -> dict[str, dict[str, Any]]:
    return {r[key]: r for r in rows if isinstance(r, dict) and isinstance(r.get(key), str)}


def _utc_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return stamp.tzinfo is not None and stamp.utcoffset() == timezone.utc.utcoffset(stamp)
    except ValueError:
        return False


def _require(errors: list[str], condition: bool, name: str) -> None:
    if not condition:
        errors.append(name)


def _unique(errors: list[str], rows: Any, name: str) -> None:
    ids = _ids(rows)
    _require(errors, len(ids) == len(set(ids)) and len(ids) == len(rows), f"{name}: missing/duplicate IDs")


def _ref(errors: list[str], value: Any, name: str, resolve: EvidenceCheck | None) -> None:
    if not _filled(value):
        errors.append(f"{name}: missing reference")
    elif resolve is None:
        errors.append(f"{name}: no evidence resolver configured")
    elif not resolve(value):
        errors.append(f"{name}: unresolved or stale evidence {value!r}")


def _all_refs(errors: list[str], rows: Any, name: str, resolve: EvidenceCheck | None) -> None:
    for i, ref in enumerate(rows):
        _ref(errors, ref, f"{name}[{i}]", resolve)


def _checkpoint(errors: list[str], record: Record, stage: str, resolve: EvidenceCheck | None) -> None:
    cp = record.get("checkpoint", {})
    state = cp.get("action_state")
    disposition = cp.get("retry_disposition")
    if state == "uncertain" and disposition not in ("reconcile_first", "blocked"):
        errors.append(f"{stage}: uncertain action must be reconciled before retry")
    if state == "completed":
        _require(errors, _filled(cp.get("action_id")), f"{stage}: completed action lacks ID")
        _ref(errors, cp.get("action_receipt_ref"), f"{stage}.checkpoint.action_receipt_ref", resolve)
    if record.get("handoff", {}).get("ready") is True:
        _require(errors, state not in ("pending", "uncertain"), f"{stage}: unfinished checkpoint")
        _ref(errors, cp.get("source_snapshot_ref"), f"{stage}.checkpoint.source_snapshot_ref", resolve)


def _safe_get(record: Any, *keys: str, default: Any = None) -> Any:
    """Safely traverse nested dict keys, returning default on any non-dict encountered."""
    val: Any = record
    for key in keys:
        if not isinstance(val, dict):
            return default
        val = val.get(key, default)
    return val


def _base(errors: list[str], record: Record, stage: str, resolve: EvidenceCheck | None,
          preflight: bool = False) -> bool:
    if not isinstance(record, dict):
        errors.append(f"{stage}: not an object")
        return False
    if record.get("kind") != stage:
        errors.append(f"{stage}: kind mismatch")
    _require(errors, _filled(record.get("task_id")), f"{stage}: missing task_id")
    _require(errors, _filled(record.get("record_id")), f"{stage}: missing record_id")
    _require(errors, type(record.get("revision")) is int and record["revision"] > 0,
             f"{stage}: invalid revision")
    _require(errors, record.get("status") in {"draft", "in_progress", "failed", "blocked", "complete"},
             f"{stage}: invalid status")
    ready = record.get("handoff", {}).get("ready")
    _require(errors, isinstance(ready, bool), f"{stage}: handoff.ready must be boolean")
    required_sections = {
        "research": ("purpose", "search", "outputs", "review"),
        "plan": ("research_input", "purpose", "implementation", "gap_analysis", "fixture_validation_chaos"),
        "build": ("plan_input", "execution", "implementation_validation", "post_build_e2e", "issues_and_corrections", "outcome"),
    }
    missing = [name for name in required_sections[stage] if not isinstance(record.get(name), dict)]
    for name in missing:
        errors.append(f"{stage}: missing or malformed {name} section")
    if record.get("status") == "complete" or ready is True:
        _require(errors, ready is True and record.get("status") == "complete",
                 f"{stage}: complete and handoff.ready must agree")
        _require(errors, _utc_date(record.get("updated_at")), f"{stage}: missing UTC updated_at")
        _require(errors, bool(record.get("progress_log")), f"{stage}: no progress log")
        _require(errors, bool(record.get("decision_log")), f"{stage}: no decision log")
        if not preflight:
            _ref(errors, record.get("handoff", {}).get("validation_receipt_ref"),
                 f"{stage}.handoff.validation_receipt_ref", resolve)
        _checkpoint(errors, record, stage, resolve)
        return not missing
    _checkpoint(errors, record, stage, resolve)
    return False


def validate_records(research: Record, plan: Record, build: Record,
                     resolve: EvidenceCheck | None = None) -> list[str]:
    """Return specific invariant violations; no model judgment or tool execution.

    ``resolve`` must independently verify artifact references through the host
    store or an on-disk SHA-256 evidence index. Passing ``None`` fails closed
    for completed records. This cannot prove semantic quality of Research.
    """
    errors: list[str] = []
    records = {"research": research, "plan": plan, "build": build}
    complete = {k: _base(errors, v, k, resolve) for k, v in records.items()}
    for kind, record in records.items():
        _require(errors, record.get("handoff", {}).get("to") == {
            "research": "plan", "plan": "build", "build": "complete"
        }[kind], f"{kind}: invalid handoff destination")
    if len({r.get("task_id") for r in records.values()}) != 1:
        errors.append("task_id mismatch across records")
    if not complete["research"] and (complete["plan"] or complete["build"]):
        errors.append("downstream complete while Research not ready")
    if not complete["plan"] and complete["build"]:
        errors.append("Build complete while Plan not ready")

    if complete["research"]:
        p, s, outputs, review = (research[k] for k in ("purpose", "search", "outputs", "review"))
        reqs = [r for r in p["accepted_requirements"] if r.get("scope") == "in_scope"]
        _require(errors, bool(reqs), "research: no accepted in-scope requirements")
        _unique(errors, p["accepted_requirements"], "research.requirements")
        _unique(errors, s["findings"], "research.findings")
        for r in reqs:
            _ref(errors, r.get("authority_ref"), f"research.requirement.{r.get('id')}.authority", resolve)
        _require(errors, bool(s["sources"]), "research: no inspected sources")
        for src in s["sources"]:
            _require(errors, _filled(src.get("revision_or_hash")) and _filled(src.get("location")),
                     f"research: source lacks identity {src.get('id')}")
            _ref(errors, src.get("evidence_ref"), f"research.source.{src.get('id')}.evidence", resolve)
        for conflict in s.get("contradictions", []):
            _require(errors, conflict.get("disposition") == "resolved",
                     f"research: unresolved contradiction {conflict.get('id')}")
            if conflict.get("disposition") == "resolved":
                _ref(errors, conflict.get("resolution_ref"), f"research.contradiction.{conflict.get('id')}", resolve)
        _require(errors, not any(i.get("blocking") and i.get("resolution") != "resolved"
                                for i in s.get("uncertainties", [])),
                 "research: unresolved blocking uncertainty")
        _require(errors, review["coverage"] == "sufficient" and review["evidence_grounding"] == "passed"
                 and review["disposition"] == "ready_for_plan", "research: review not ready")
        _require(errors, not review["unsupported_claims"] and not review["blockers"],
                 "research: unsupported claims or blockers remain")
        _require(errors, all(not i.get("blocking") for i in review["unresolved_issues"]),
                 "research: blocking unresolved issues")
        findings = _index(s["findings"])
        traces = _index(outputs["requirement_trace"], "requirement_id")
        _require(errors, set(traces) == {r["id"] for r in reqs}, "research: requirement trace coverage mismatch")
        for r in reqs:
            t = traces.get(r["id"], {})
            _require(errors, bool(t.get("finding_ids")) and bool(t.get("fixture_ids")) and bool(t.get("criterion_ids")),
                     f"research: incomplete trace for {r['id']}")
            for fid in t.get("finding_ids", []):
                finding = findings.get(fid)
                _require(errors, bool(finding) and finding.get("assessment") == "supported"
                         and bool(finding.get("evidence_refs")), f"research: unsupported finding {fid}")
                if finding:
                    _all_refs(errors, finding.get("evidence_refs", []), f"research.finding.{fid}.evidence", resolve)
        for k in ("todo_search_ref",):
            _ref(errors, s.get(k), f"research.search.{k}", resolve)
        _ref(errors, review.get("review_receipt_ref"), "research.review.receipt", resolve)
        _ref(errors, outputs.get("candidate_plan_ref"), "research.candidate_plan", resolve)
        _all_refs(errors, outputs.get("fixture_refs", []), "research.fixtures", resolve)
        _all_refs(errors, outputs.get("success_criteria_refs", []), "research.criteria", resolve)
        _require(errors, bool(outputs["fixture_refs"]) and bool(outputs["success_criteria_refs"]),
                 "research: no fixture/criteria references")
        _ref(errors, research["handoff"].get("artifact_manifest_ref"), "research.manifest", resolve)

    if complete["plan"] and complete["research"]:
        ri, p, impl, gaps, fix, h = (plan[k] for k in ("research_input", "purpose", "implementation", "gap_analysis", "fixture_validation_chaos", "handoff"))
        _ref(errors, ri.get("record_ref"), "plan.research_input.record_ref", resolve)
        _require(errors, ri.get("record_id") == research.get("record_id"), "plan: Research identity mismatch")
        _require(errors, ri.get("record_revision") == research.get("revision"), "plan: stale Research revision")
        _require(errors, ri.get("artifact_manifest_ref") == research["handoff"].get("artifact_manifest_ref"),
                 "plan: Research manifest changed")
        required = {r["id"] for r in research["purpose"]["accepted_requirements"] if r.get("scope") == "in_scope"}
        _require(errors, set(ri["accepted_requirement_ids"]) == required, "plan: accepted requirements drift")
        _require(errors, p["user_outcome"] == research["purpose"]["user_outcome"], "plan: user outcome drift")
        _unique(errors, p["acceptance_criteria"], "plan.criteria")
        _require(errors, required <= {c.get("requirement_id") for c in p["acceptance_criteria"]},
                 "plan: missing success criteria")
        for criterion in p["acceptance_criteria"]:
            _require(errors, _filled(criterion.get("expected_result")), f"plan: missing expectation {criterion.get('id')}")
            _ref(errors, criterion.get("oracle_ref"), f"plan.oracle.{criterion.get('id')}", resolve)
        _require(errors, bool(impl["milestones"]), "plan: no executable milestones")
        _unique(errors, impl["milestones"], "plan.milestones")
        for m in impl["milestones"]:
            _require(errors, bool(m.get("steps")) and bool(m.get("expected_observations")),
                     f"plan: unexecutable milestone {m.get('id')}")
        _ref(errors, impl.get("proposed_final_tree_ref"), "plan.final_tree", resolve)
        _ref(errors, impl.get("command_environment_ref"), "plan.command_environment", resolve)
        _require(errors, _filled(impl.get("rollback_or_recovery")), "plan: missing recovery guidance")
        _require(errors, gaps["status"] == "resolved", "plan: gap analysis incomplete")
        _require(errors, bool(gaps["scanner_calls"]), "plan: Scanner was not invoked")
        _unique(errors, gaps["findings"], "plan.gap_findings")
        for call in gaps["scanner_calls"]:
            _require(errors, call.get("outcome") == "passed", "plan: Scanner call did not succeed")
            _ref(errors, call.get("tool_ref"), "plan.scanner.tool", resolve)
            _ref(errors, call.get("scope_ref"), "plan.scanner.scope", resolve)
            _ref(errors, call.get("receipt_ref"), "plan.scanner.receipt", resolve)
            _ref(errors, call.get("findings_ref"), "plan.scanner.findings", resolve)
        last = gaps["scanner_calls"][-1] if gaps["scanner_calls"] else {}
        _require(errors, last.get("input_revision") == plan["revision"], "plan: Scanner result stale after revision")
        _require(errors, not gaps["unresolved_critical_ids"], "plan: unresolved critical gaps")
        for f in gaps["findings"]:
            st, severity = f.get("status"), f.get("severity")
            _require(errors, st in ("resolved", "false_positive", "deferred"),
                     f"plan: unresolved finding {f.get('id')}")
            _require(errors, st != "deferred" or severity != "critical", f"plan: critical finding deferred {f.get('id')}")
            if st == "resolved":
                _ref(errors, f.get("fix_receipt_ref"), f"plan.finding.{f.get('id')}.fix", resolve)
                _ref(errors, f.get("recheck_ref"), f"plan.finding.{f.get('id')}.recheck", resolve)
            elif st == "false_positive":
                _require(errors, _filled(f.get("disposition_reason")) and bool(f.get("evidence_refs")),
                         f"plan: unjustified false positive {f.get('id')}")
            elif st == "deferred":
                _ref(errors, f.get("approval_ref"), f"plan.finding.{f.get('id')}.approval", resolve)
                _require(errors, _filled(f.get("disposition_reason")), f"plan: missing deferral reason {f.get('id')}")
        if gaps["findings"]:
            _ref(errors, gaps.get("last_recheck_ref"), "plan.last_recheck", resolve)
        _require(errors, fix["status"] == "passed", "plan: fixture validation not passed")
        _require(errors, bool(fix["fixture_refs"]) and bool(fix["oracle_evidence_refs"])
                 and bool(fix["prebuild_validation_receipt_refs"]), "plan: fixtures/oracles not independently prevalidated")
        _all_refs(errors, fix["fixture_refs"] + fix["oracle_evidence_refs"] + fix["prebuild_validation_receipt_refs"],
                  "plan.fixture_validation", resolve)
        _require(errors, set(research["outputs"]["fixture_refs"]) <= set(fix["fixture_refs"]),
                 "plan: Research fixtures dropped")
        if fix["chaos_applicability"] == "required":
            _require(errors, bool(fix["chaos_case_refs"]), "plan: missing required chaos cases")
            _all_refs(errors, fix["chaos_case_refs"], "plan.chaos", resolve)
        elif fix["chaos_applicability"] == "not_applicable":
            _require(errors, _filled(fix.get("chaos_exclusion_reason")), "plan: chaos exclusion not justified")
        else:
            errors.append("plan: chaos applicability not decided")
        _require(errors, all(not x.get("blocking") for x in fix["coverage_gaps"]),
                 "plan: blocking fixture/chaos coverage gaps")
        _ref(errors, h.get("plan_artifact_ref"), "plan.execplan", resolve)
        _ref(errors, h.get("artifact_manifest_ref"), "plan.manifest", resolve)

    if complete["build"] and complete["plan"] and complete["research"]:
        pi, execution, iv, e2e, issues, outcome, h = (build[k] for k in ("plan_input", "execution", "implementation_validation", "post_build_e2e", "issues_and_corrections", "outcome", "handoff"))
        _ref(errors, pi.get("record_ref"), "build.plan_ref", resolve)
        _require(errors, pi.get("record_id") == plan.get("record_id"), "build: Plan identity mismatch")
        _require(errors, pi.get("record_revision") == plan.get("revision"), "build: stale Plan revision")
        _require(errors, pi.get("artifact_manifest_ref") == plan["handoff"].get("artifact_manifest_ref"),
                 "build: Plan manifest changed")
        milestones = set(_ids(plan["implementation"]["milestones"]))
        criteria = set(_ids(plan["purpose"]["acceptance_criteria"]))
        _require(errors, set(pi["accepted_milestone_ids"]) == milestones and bool(milestones),
                 "build: milestone coverage drift")
        _require(errors, set(pi["accepted_criterion_ids"]) == criteria and bool(criteria),
                 "build: criterion coverage drift")
        _require(errors, set(_ids(execution["milestone_results"])) == milestones, "build: missing milestone results")
        _require(errors, all(r.get("status") == "passed" and (r.get("command_receipts") or r.get("artifact_refs"))
                            for r in execution["milestone_results"]), "build: incomplete or unevidenced milestone")
        for name in ("workspace_snapshot_ref", "environment_ref", "artifact_manifest_ref"):
            _ref(errors, execution.get(name), f"build.execution.{name}", resolve)
        _require(errors, _utc_date(execution.get("finished_at")), "build: invalid finish timestamp")
        _require(errors, bool(execution["command_receipts"]), "build: no executed command receipts")
        _unique(errors, execution["command_receipts"], "build.command_receipts")
        for r in execution["command_receipts"]:
            _require(errors, type(r.get("exit_code")) is int and _filled(r.get("cwd"))
                     and _filled(r.get("command")), "build: incomplete command receipt")
            _ref(errors, r.get("receipt_ref"), f"build.command.{r.get('id')}.receipt", resolve)
        for mr in execution["milestone_results"]:
            _all_refs(errors, mr.get("artifact_refs", []), f"build.milestone.{mr.get('id')}.artifacts", resolve)
            _require(errors, set(mr.get("command_receipts", [])) <= set(_ids(execution["command_receipts"])),
                     f"build.milestone.{mr.get('id')}: command IDs not in execution receipts")
        _require(errors, iv["status"] == "passed", "build: implementation validation not passed")
        _require(errors, set(r.get("criterion_id") for r in iv["checks"]) >= criteria and
                 all(c.get("status") == "passed" for c in iv["checks"]),
                 "build: implementation checks missing or failing")
        for c in iv["checks"]:
            _ref(errors, c.get("receipt_ref"), "build.implementation.check.receipt", resolve)
        _require(errors, e2e["status"] == "passed", "build: post-Build E2E not passed")
        for name in ("real_entrypoint_ref", "environment_ref"):
            _ref(errors, e2e.get(name), f"build.e2e.{name}", resolve)
        _require(errors, bool(e2e["cases"]) and all(c.get("status") == "passed" for c in e2e["cases"]),
                 "build: missing/failing real E2E cases")
        _require(errors, set(plan["fixture_validation_chaos"]["fixture_refs"]) <= {c.get("fixture_ref") for c in e2e["cases"]},
                 "build: planned fixtures not covered by post-Build E2E")
        for c in e2e["cases"]:
            for name in ("fixture_ref", "expected_ref", "observed_ref", "receipt_ref"):
                _ref(errors, c.get(name), f"build.e2e.case.{name}", resolve)
        _require(errors, set(c.get("criterion_id") for c in e2e["independent_result_checks"]) >= criteria
                 and all(c.get("status") == "passed" for c in e2e["independent_result_checks"]),
                 "build: actual user result not independently validated")
        for c in e2e["independent_result_checks"]:
            for name in ("expected_ref", "observed_ref", "receipt_ref"):
                _ref(errors, c.get(name), f"build.e2e.actual.{name}", resolve)
        if plan["fixture_validation_chaos"]["chaos_applicability"] == "required":
            planned = set(plan["fixture_validation_chaos"]["chaos_case_refs"])
            _require(errors, planned <= {c.get("chaos_ref") for c in e2e["chaos_cases"]},
                     "build: missing planned chaos coverage")
            _require(errors, all(c.get("status") == "passed" for c in e2e["chaos_cases"]),
                     "build: failed chaos recovery")
            for c in e2e["chaos_cases"]:
                for name in ("chaos_ref", "observed_ref", "receipt_ref"):
                    _ref(errors, c.get(name), f"build.e2e.chaos.{name}", resolve)
        _require(errors, all(not x.get("blocking") for x in e2e["coverage_gaps"]),
                 "build: blocking E2E coverage gaps")
        _require(errors, not issues["blockers"], "build: unresolved blockers")
        for f in issues["findings"]:
            _require(errors, f.get("status") == "resolved" or
                     (f.get("status") == "deferred" and f.get("severity") != "critical" and _filled(f.get("approval_ref"))),
                     f"build: open gap {f.get('id')}")
            if f.get("status") == "resolved":
                _ref(errors, f.get("fix_receipt_ref"), f"build.gap.{f.get('id')}.fix", resolve)
                _ref(errors, f.get("revalidation_ref"), f"build.gap.{f.get('id')}.revalidation", resolve)
        _require(errors, outcome["status"] == "verified", "build: outcome not verified")
        _require(errors, set(r.get("criterion_id") for r in outcome["criterion_results"]) == criteria
                 and all(r.get("status") == "passed" for r in outcome["criterion_results"]),
                 "build: outcome missing independent criteria")
        for r in outcome["criterion_results"]:
            _ref(errors, r.get("evidence_ref"), "build.outcome.criterion_evidence", resolve)
        _ref(errors, outcome.get("user_visible_result_ref"), "build.user_result", resolve)
        _ref(errors, h.get("completion_receipt_ref"), "build.completion_receipt", resolve)
    return errors




def validate_research(research: Record, resolve: EvidenceCheck | None = None,
                        preflight: bool = False) -> list[str]:
    """Validate a Research record independently, before Plan exists.

    Returns invariant violations. Uses ``preflight=True`` to skip the
    validation_receipt_ref requirement (two-step receipt protocol step 1).
    """
    errors: list[str] = []
    complete = _base(errors, research, "research", resolve, preflight=preflight)
    if not isinstance(research, dict):
        return errors
    _require(errors, research.get("handoff", {}).get("to") == "plan",
             "research: invalid handoff destination")
    if not complete:
        return errors
    p, s, outputs, review = (_safe_get(research, k, default={}) for k in ("purpose", "search", "outputs", "review"))
    reqs = [r for r in p.get("accepted_requirements", []) if isinstance(r, dict) and r.get("scope") == "in_scope"]
    _require(errors, bool(reqs), "research: no accepted in-scope requirements")
    _unique(errors, p.get("accepted_requirements", []), "research.requirements")
    _unique(errors, s.get("findings", []), "research.findings")
    for r in reqs:
        _ref(errors, r.get("authority_ref"), f"research.requirement.{r.get('id')}.authority", resolve)
    _require(errors, bool(s.get("sources")), "research: no inspected sources")
    for src in s.get("sources", []):
        if not isinstance(src, dict):
            errors.append("research: source is not an object")
            continue
        _require(errors, _filled(src.get("revision_or_hash")) and _filled(src.get("location")),
                 f"research: source lacks identity {src.get('id')}")
        _ref(errors, src.get("evidence_ref"), f"research.source.{src.get('id')}.evidence", resolve)
    for conflict in s.get("contradictions", []):
        if not isinstance(conflict, dict):
            continue
        _require(errors, conflict.get("disposition") == "resolved",
                 f"research: unresolved contradiction {conflict.get('id')}")
        if conflict.get("disposition") == "resolved":
            _ref(errors, conflict.get("resolution_ref"), f"research.contradiction.{conflict.get('id')}", resolve)
    _require(errors, not any(isinstance(i, dict) and i.get("blocking") and i.get("resolution") != "resolved"
                            for i in s.get("uncertainties", [])),
             "research: unresolved blocking uncertainty")
    _require(errors, review.get("coverage") == "sufficient" and review.get("evidence_grounding") == "passed"
             and review.get("disposition") == "ready_for_plan", "research: review not ready")
    _require(errors, not review.get("unsupported_claims") and not review.get("blockers"),
             "research: unsupported claims or blockers remain")
    _require(errors, all(not (isinstance(i, dict) and i.get("blocking")) for i in review.get("unresolved_issues", [])),
             "research: blocking unresolved issues")
    findings = _index(s.get("findings", []))
    traces = _index(outputs.get("requirement_trace", []), "requirement_id")
    _require(errors, set(traces) == {r["id"] for r in reqs if isinstance(r, dict) and "id" in r},
             "research: requirement trace coverage mismatch")
    for r in reqs:
        t = traces.get(r.get("id", ""), {})
        _require(errors, bool(t.get("finding_ids")) and bool(t.get("fixture_ids")) and bool(t.get("criterion_ids")),
                 f"research: incomplete trace for {r.get('id')}")
        for fid in t.get("finding_ids", []):
            finding = findings.get(fid)
            _require(errors, bool(finding) and finding.get("assessment") == "supported"
                     and bool(finding.get("evidence_refs")), f"research: unsupported finding {fid}")
            if finding:
                _all_refs(errors, finding.get("evidence_refs", []), f"research.finding.{fid}.evidence", resolve)
    for k in ("todo_search_ref",):
        _ref(errors, s.get(k), f"research.search.{k}", resolve)
    _ref(errors, review.get("review_receipt_ref"), "research.review.receipt", resolve)
    _ref(errors, outputs.get("candidate_plan_ref"), "research.candidate_plan", resolve)
    _all_refs(errors, outputs.get("fixture_refs", []), "research.fixtures", resolve)
    _all_refs(errors, outputs.get("success_criteria_refs", []), "research.criteria", resolve)
    _require(errors, bool(outputs.get("fixture_refs")) and bool(outputs.get("success_criteria_refs")),
             "research: no fixture/criteria references")
    _ref(errors, research.get("handoff", {}).get("artifact_manifest_ref"), "research.manifest", resolve)
    return errors


def validate_plan(plan: Record, research: Record | None = None,
                   resolve: EvidenceCheck | None = None,
                   preflight: bool = False) -> list[str]:
    """Validate a Plan record, optionally given an accepted Research record."""
    errors: list[str] = []
    complete = _base(errors, plan, "plan", resolve, preflight=preflight)
    if not isinstance(plan, dict):
        return errors
    _require(errors, plan.get("handoff", {}).get("to") == "build",
             "plan: invalid handoff destination")
    if not complete:
        return errors
    ri = _safe_get(plan, "research_input", default={})
    p = _safe_get(plan, "purpose", default={})
    impl = _safe_get(plan, "implementation", default={})
    gaps = _safe_get(plan, "gap_analysis", default={})
    fix = _safe_get(plan, "fixture_validation_chaos", default={})
    h = _safe_get(plan, "handoff", default={})
    if research is not None and isinstance(research, dict):
        _ref(errors, ri.get("record_ref"), "plan.research_input.record_ref", resolve)
        _require(errors, ri.get("record_id") == research.get("record_id"), "plan: Research identity mismatch")
        _require(errors, ri.get("record_revision") == research.get("revision"), "plan: stale Research revision")
        _require(errors, ri.get("artifact_manifest_ref") == research.get("handoff", {}).get("artifact_manifest_ref"),
                 "plan: Research manifest changed")
        required = {r["id"] for r in research.get("purpose", {}).get("accepted_requirements", [])
                    if isinstance(r, dict) and r.get("scope") == "in_scope"}
        _require(errors, set(ri.get("accepted_requirement_ids", [])) == required, "plan: accepted requirements drift")
        _require(errors, p.get("user_outcome") == research.get("purpose", {}).get("user_outcome"),
                 "plan: user outcome drift")
    else:
        required = set(ri.get("accepted_requirement_ids", []))
    _unique(errors, p.get("acceptance_criteria", []), "plan.criteria")
    _require(errors, required <= {c.get("requirement_id") for c in p.get("acceptance_criteria", []) if isinstance(c, dict)},
             "plan: missing success criteria")
    for criterion in p.get("acceptance_criteria", []):
        if not isinstance(criterion, dict):
            continue
        _require(errors, _filled(criterion.get("expected_result")), f"plan: missing expectation {criterion.get('id')}")
        _ref(errors, criterion.get("oracle_ref"), f"plan.oracle.{criterion.get('id')}", resolve)
    _require(errors, bool(impl.get("milestones")), "plan: no executable milestones")
    _unique(errors, impl.get("milestones", []), "plan.milestones")
    for m in impl.get("milestones", []):
        if not isinstance(m, dict):
            continue
        _require(errors, bool(m.get("steps")) and bool(m.get("expected_observations")),
                 f"plan: unexecutable milestone {m.get('id')}")
    _ref(errors, impl.get("proposed_final_tree_ref"), "plan.final_tree", resolve)
    _ref(errors, impl.get("command_environment_ref"), "plan.command_environment", resolve)
    _require(errors, _filled(impl.get("rollback_or_recovery")), "plan: missing recovery guidance")
    _require(errors, gaps.get("status") == "resolved", "plan: gap analysis incomplete")
    _require(errors, bool(gaps.get("scanner_calls")), "plan: Scanner was not invoked")
    _unique(errors, gaps.get("findings", []), "plan.gap_findings")
    for call in gaps.get("scanner_calls", []):
        if not isinstance(call, dict):
            continue
        _require(errors, call.get("outcome") == "passed", "plan: Scanner call did not succeed")
        _ref(errors, call.get("tool_ref"), "plan.scanner.tool", resolve)
        _ref(errors, call.get("scope_ref"), "plan.scanner.scope", resolve)
        _ref(errors, call.get("receipt_ref"), "plan.scanner.receipt", resolve)
        _ref(errors, call.get("findings_ref"), "plan.scanner.findings", resolve)
    last = gaps.get("scanner_calls", [{}])[-1] if gaps.get("scanner_calls") else {}
    _require(errors, isinstance(last, dict) and last.get("input_revision") == plan.get("revision"),
             "plan: Scanner result stale after revision")
    _require(errors, not gaps.get("unresolved_critical_ids"), "plan: unresolved critical gaps")
    for f in gaps.get("findings", []):
        if not isinstance(f, dict):
            continue
        st, severity = f.get("status"), f.get("severity")
        _require(errors, st in ("resolved", "false_positive", "deferred"),
                 f"plan: unresolved finding {f.get('id')}")
        _require(errors, st != "deferred" or severity != "critical", f"plan: critical finding deferred {f.get('id')}")
        if st == "resolved":
            _ref(errors, f.get("fix_receipt_ref"), f"plan.finding.{f.get('id')}.fix", resolve)
            _ref(errors, f.get("recheck_ref"), f"plan.finding.{f.get('id')}.recheck", resolve)
        elif st == "false_positive":
            _require(errors, _filled(f.get("disposition_reason")) and bool(f.get("evidence_refs")),
                     f"plan: unjustified false positive {f.get('id')}")
        elif st == "deferred":
            _ref(errors, f.get("approval_ref"), f"plan.finding.{f.get('id')}.approval", resolve)
            _require(errors, _filled(f.get("disposition_reason")), f"plan: missing deferral reason {f.get('id')}")
    if gaps.get("findings"):
        _ref(errors, gaps.get("last_recheck_ref"), "plan.last_recheck", resolve)
    _require(errors, fix.get("status") == "passed", "plan: fixture validation not passed")
    _require(errors, bool(fix.get("fixture_refs")) and bool(fix.get("oracle_evidence_refs"))
             and bool(fix.get("prebuild_validation_receipt_refs")), "plan: fixtures/oracles not independently prevalidated")
    _all_refs(errors, (fix.get("fixture_refs", []) + fix.get("oracle_evidence_refs", []) + fix.get("prebuild_validation_receipt_refs", [])),
              "plan.fixture_validation", resolve)
    if research is not None and isinstance(research, dict):
        _require(errors, set(research.get("outputs", {}).get("fixture_refs", [])) <= set(fix.get("fixture_refs", [])),
                 "plan: Research fixtures dropped")
    if fix.get("chaos_applicability") == "required":
        _require(errors, bool(fix.get("chaos_case_refs")), "plan: missing required chaos cases")
        _all_refs(errors, fix.get("chaos_case_refs", []), "plan.chaos", resolve)
    elif fix.get("chaos_applicability") == "not_applicable":
        _require(errors, _filled(fix.get("chaos_exclusion_reason")), "plan: chaos exclusion not justified")
    else:
        errors.append("plan: chaos applicability not decided")
    _require(errors, all(not (isinstance(x, dict) and x.get("blocking")) for x in fix.get("coverage_gaps", [])),
             "plan: blocking fixture/chaos coverage gaps")
    _ref(errors, h.get("plan_artifact_ref"), "plan.execplan", resolve)
    _ref(errors, h.get("artifact_manifest_ref"), "plan.manifest", resolve)
    return errors


def validate_build(build: Record, plan: Record | None = None,
                    research: Record | None = None,
                    resolve: EvidenceCheck | None = None,
                    preflight: bool = False) -> list[str]:
    """Validate a Build record, optionally given accepted Research and Plan."""
    errors: list[str] = []
    complete = _base(errors, build, "build", resolve, preflight=preflight)
    if not isinstance(build, dict):
        return errors
    _require(errors, build.get("handoff", {}).get("to") == "complete",
             "build: invalid handoff destination")
    if not complete or plan is None or not isinstance(plan, dict):
        return errors
    pi = _safe_get(build, "plan_input", default={})
    execution = _safe_get(build, "execution", default={})
    iv = _safe_get(build, "implementation_validation", default={})
    e2e = _safe_get(build, "post_build_e2e", default={})
    issues = _safe_get(build, "issues_and_corrections", default={})
    outcome = _safe_get(build, "outcome", default={})
    h = _safe_get(build, "handoff", default={})
    _ref(errors, pi.get("record_ref"), "build.plan_ref", resolve)
    _require(errors, pi.get("record_id") == plan.get("record_id"), "build: Plan identity mismatch")
    _require(errors, pi.get("record_revision") == plan.get("revision"), "build: stale Plan revision")
    _require(errors, pi.get("artifact_manifest_ref") == plan.get("handoff", {}).get("artifact_manifest_ref"),
             "build: Plan manifest changed")
    milestones = set(_ids(plan.get("implementation", {}).get("milestones", [])))
    criteria = set(_ids(plan.get("purpose", {}).get("acceptance_criteria", [])))
    _require(errors, set(pi.get("accepted_milestone_ids", [])) == milestones and bool(milestones),
             "build: milestone coverage drift")
    _require(errors, set(pi.get("accepted_criterion_ids", [])) == criteria and bool(criteria),
             "build: criterion coverage drift")
    _require(errors, set(_ids(execution.get("milestone_results", []))) == milestones, "build: missing milestone results")
    _require(errors, all(isinstance(r, dict) and r.get("status") == "passed" and (r.get("command_receipts") or r.get("artifact_refs"))
                        for r in execution.get("milestone_results", [])), "build: incomplete or unevidenced milestone")
    for name in ("workspace_snapshot_ref", "environment_ref", "artifact_manifest_ref"):
        _ref(errors, execution.get(name), f"build.execution.{name}", resolve)
    _require(errors, _utc_date(execution.get("finished_at")), "build: invalid finish timestamp")
    _require(errors, bool(execution.get("command_receipts")), "build: no executed command receipts")
    _unique(errors, execution.get("command_receipts", []), "build.command_receipts")
    for r in execution.get("command_receipts", []):
        if not isinstance(r, dict):
            continue
        _require(errors, type(r.get("exit_code")) is int and _filled(r.get("cwd"))
                 and _filled(r.get("command")), "build: incomplete command receipt")
        _ref(errors, r.get("receipt_ref"), f"build.command.{r.get('id')}.receipt", resolve)
    for mr in execution.get("milestone_results", []):
        if not isinstance(mr, dict):
            continue
        _all_refs(errors, mr.get("artifact_refs", []), f"build.milestone.{mr.get('id')}.artifacts", resolve)
        _require(errors, set(mr.get("command_receipts", [])) <= set(_ids(execution.get("command_receipts", []))),
                 f"build.milestone.{mr.get('id')}: command IDs not in execution receipts")
    _require(errors, iv.get("status") == "passed", "build: implementation validation not passed")
    _require(errors, set(r.get("criterion_id") for r in iv.get("checks", []) if isinstance(r, dict)) >= criteria and
             all(isinstance(c, dict) and c.get("status") == "passed" for c in iv.get("checks", [])),
             "build: implementation checks missing or failing")
    for c in iv.get("checks", []):
        if not isinstance(c, dict):
            continue
        _ref(errors, c.get("receipt_ref"), "build.implementation.check.receipt", resolve)
    _require(errors, e2e.get("status") == "passed", "build: post-Build E2E not passed")
    for name in ("real_entrypoint_ref", "environment_ref"):
        _ref(errors, e2e.get(name), f"build.e2e.{name}", resolve)
    _require(errors, bool(e2e.get("cases")) and all(isinstance(c, dict) and c.get("status") == "passed" for c in e2e.get("cases", [])),
             "build: missing/failing real E2E cases")
    _require(errors, set(plan.get("fixture_validation_chaos", {}).get("fixture_refs", [])) <= {c.get("fixture_ref") for c in e2e.get("cases", []) if isinstance(c, dict)},
             "build: planned fixtures not covered by post-Build E2E")
    for c in e2e.get("cases", []):
        if not isinstance(c, dict):
            continue
        for name in ("fixture_ref", "expected_ref", "observed_ref", "receipt_ref"):
            _ref(errors, c.get(name), f"build.e2e.case.{name}", resolve)
    _require(errors, set(c.get("criterion_id") for c in e2e.get("independent_result_checks", []) if isinstance(c, dict)) >= criteria
             and all(isinstance(c, dict) and c.get("status") == "passed" for c in e2e.get("independent_result_checks", [])),
             "build: actual user result not independently validated")
    for c in e2e.get("independent_result_checks", []):
        if not isinstance(c, dict):
            continue
        for name in ("expected_ref", "observed_ref", "receipt_ref"):
            _ref(errors, c.get(name), f"build.e2e.actual.{name}", resolve)
    if plan.get("fixture_validation_chaos", {}).get("chaos_applicability") == "required":
        planned = set(plan.get("fixture_validation_chaos", {}).get("chaos_case_refs", []))
        _require(errors, planned <= {c.get("chaos_ref") for c in e2e.get("chaos_cases", []) if isinstance(c, dict)},
                 "build: missing planned chaos coverage")
        _require(errors, all(isinstance(c, dict) and c.get("status") == "passed" for c in e2e.get("chaos_cases", [])),
                 "build: failed chaos recovery")
        for c in e2e.get("chaos_cases", []):
            if not isinstance(c, dict):
                continue
            for name in ("chaos_ref", "observed_ref", "receipt_ref"):
                _ref(errors, c.get(name), f"build.e2e.chaos.{name}", resolve)
    _require(errors, all(not (isinstance(x, dict) and x.get("blocking")) for x in e2e.get("coverage_gaps", [])),
             "build: blocking E2E coverage gaps")
    _require(errors, not issues.get("blockers"), "build: unresolved blockers")
    for f in issues.get("findings", []):
        if not isinstance(f, dict):
            continue
        _require(errors, f.get("status") == "resolved" or
                 (f.get("status") == "deferred" and f.get("severity") != "critical" and _filled(f.get("approval_ref"))),
                 f"build: open gap {f.get('id')}")
        if f.get("status") == "resolved":
            _ref(errors, f.get("fix_receipt_ref"), f"build.gap.{f.get('id')}.fix", resolve)
            _ref(errors, f.get("revalidation_ref"), f"build.gap.{f.get('id')}.revalidation", resolve)
    _require(errors, outcome.get("status") == "verified", "build: outcome not verified")
    _require(errors, set(r.get("criterion_id") for r in outcome.get("criterion_results", []) if isinstance(r, dict)) == criteria
             and all(isinstance(r, dict) and r.get("status") == "passed" for r in outcome.get("criterion_results", [])),
             "build: outcome missing independent criteria")
    for r in outcome.get("criterion_results", []):
        if not isinstance(r, dict):
            continue
        _ref(errors, r.get("evidence_ref"), "build.outcome.criterion_evidence", resolve)
    _ref(errors, outcome.get("user_visible_result_ref"), "build.user_result", resolve)
    _ref(errors, h.get("completion_receipt_ref"), "build.completion_receipt", resolve)
    return errors


def preflight_check(record: Record, stage: str, resolve: EvidenceCheck | None = None) -> list[str]:
    """Step 1 of the two-step receipt protocol: validate substantive evidence
    without requiring the validation_receipt_ref (which is created by this step).

    Returns errors. An empty list means the record is substantively ready;
    the host should then persist a signed/hashed validation receipt and call
    the full per-stage validator to revalidate including the receipt (step 2).
    """
    if stage == "research":
        return validate_research(record, resolve, preflight=True)
    elif stage == "plan":
        return validate_plan(record, resolve=resolve, preflight=True)
    elif stage == "build":
        return validate_build(record, resolve=resolve, preflight=True)
    else:
        return [f"unknown stage: {stage}"]


def evidence_index_resolver(index: dict[str, dict[str, str]], root: Path) -> EvidenceCheck:
    """Verify a file-backed artifact reference against independent SHA-256.

    Opaque artifact-store IDs require the host's own resolver instead.
    References may only resolve to files under ``root``.
    """
    base = root.resolve()

    def resolve(ref: str) -> bool:
        item = index.get(ref)
        if not isinstance(item, dict):
            return False
        sha = item.get("sha256", "")
        path = item.get("path", "")
        if not isinstance(sha, str) or len(sha) != 64 or not isinstance(path, str):
            return False
        raw = base / path
        target = raw.resolve()
        if not target.is_relative_to(base) or not target.is_file():
            return False
        # Reject a symlink at any path component even if it resolves inside root.
        if raw.is_symlink() or any(parent.is_symlink() for parent in raw.parents if parent != base and parent.is_relative_to(base)):
            return False
        return hashlib.sha256(target.read_bytes()).hexdigest() == sha

    return resolve


def _load(path: Path) -> Record:
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as e:
            raise RuntimeError("YAML input requires an already-installed PyYAML; JSON input needs no extra dependency") from e
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    raise ValueError(f"Unsupported record type: {path.suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate OneShot contract records (read-only)")
    parser.add_argument("--stage", choices=["research", "plan", "build", "all"], default="all",
                        help="Validate a single stage or all three (default: all)")
    parser.add_argument("research", type=Path, nargs="?", help="Research record (required)")
    parser.add_argument("plan", type=Path, nargs="?", help="Plan record (required for stage=plan or all)")
    parser.add_argument("build", type=Path, nargs="?", help="Build record (required for stage=build or all)")
    parser.add_argument("--evidence-index", type=Path, help="JSON {ref: {path, sha256}} from actual artifact store export")
    parser.add_argument("--evidence-root", type=Path, help="Root for paths in evidence index")
    parser.add_argument("--preflight", action="store_true", help="Skip validation_receipt_ref (step 1 of receipt protocol)")
    args = parser.parse_args()

    if args.evidence_index:
        if args.evidence_root is None:
            parser.error("--evidence-root is required with --evidence-index")
        resolver = evidence_index_resolver(_load(args.evidence_index), args.evidence_root)
    else:
        resolver = None

    if args.stage == "all":
        if not args.research or not args.plan or not args.build:
            parser.error("stage=all requires research, plan, and build arguments")
        findings = validate_records(_load(args.research), _load(args.plan), _load(args.build), resolver)
    elif args.stage == "research":
        if not args.research:
            parser.error("stage=research requires a research record argument")
        findings = validate_research(_load(args.research), resolver, preflight=args.preflight)
    elif args.stage == "plan":
        if not args.plan:
            parser.error("stage=plan requires a plan record argument")
        research = _load(args.research) if args.research else None
        findings = validate_plan(_load(args.plan), research, resolver, preflight=args.preflight)
    elif args.stage == "build":
        if not args.build:
            parser.error("stage=build requires a build record argument")
        research = _load(args.research) if args.research else None
        plan = _load(args.plan) if args.plan else None
        findings = validate_build(_load(args.build), plan, research, resolver, preflight=args.preflight)

    for issue in findings:
        print("FAIL:", issue)
    print("PASS: contract invariant checks" if not findings else f"FAILED: {len(findings)} invariant(s)")
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())