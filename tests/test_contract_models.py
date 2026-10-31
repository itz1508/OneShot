#!/usr/bin/env python3
"""Tests for Pydantic contract models and dual-layer compatibility."""
from __future__ import annotations
import copy, sys, unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
# Import via sys.path so Pydantic resolves forward refs correctly
sys.path.insert(0, str(REPO / "agent" / "contracts"))
import models as models

def _refs():
    s=set()
    def r(v): s.add(v); return v
    return s, r

def _mk_r():
    s, r = _refs()
    b = dict(task_id="t1", revision=2, status="complete", updated_at="2026-10-30T03:00:00Z",
             progress_log=[{"at":"x","r":"d"}], decision_log=[{"at":"x","w":"s"}])
    cp = dict(action_id="a1", action_state="completed", action_receipt_ref=r("action"),
              retry_disposition="not_applicable", source_snapshot_ref=r("snapshot"))
    return s, dict(b, kind="research", record_id="r1", checkpoint=cp,
        purpose={"user_outcome":"count","accepted_requirements":[dict(id="R1",statement="c",scope="in_scope",authority_ref=r("req"))]},
        search={"todo_search_ref":r("todo"),"sources":[dict(id="S1",location="s.py",revision_or_hash="sha",evidence_ref=r("sr"))],
                "findings":[dict(id="F1",claim="c",assessment="supported",evidence_refs=[r("src")])],"contradictions":[],"uncertainties":[]},
        outputs=dict(candidate_plan_ref=r("cand"),fixture_refs=[r("fix")],success_criteria_refs=[r("crit")],
                     requirement_trace=[dict(requirement_id="R1",finding_ids=["F1"],fixture_ids=["f1"],criterion_ids=["c1"])]),
        review=dict(coverage="sufficient",evidence_grounding="passed",disposition="ready_for_plan",
                    unsupported_claims=[],blockers=[],unresolved_issues=[],review_receipt_ref=r("rev")),
        handoff=dict(to="plan",ready=True,artifact_manifest_ref=r("rm"),validation_receipt_ref=r("rv")))

def _mk_p():
    s, r = _refs()
    b = dict(task_id="t1", revision=2, status="complete", updated_at="2026-10-30T03:00:00Z",
             progress_log=[{"at":"x","r":"d"}], decision_log=[{"at":"x","w":"s"}])
    cp = dict(action_id="a1", action_state="completed", action_receipt_ref=r("action"),
              retry_disposition="not_applicable", source_snapshot_ref=r("snapshot"))
    return s, dict(b, kind="plan", record_id="p1", checkpoint=cp,
        research_input=dict(record_ref=r("rr"),record_id="r1",record_revision=2,
                            artifact_manifest_ref="rm",accepted_requirement_ids=["R1"]),
        purpose=dict(user_outcome="count",acceptance_criteria=[dict(id="c1",requirement_id="R1",expected_result="3",oracle_ref=r("ora"))]),
        implementation=dict(proposed_final_tree_ref=r("tree"),command_environment_ref=r("env"),rollback_or_recovery="rerun",
                            milestones=[dict(id="m1",goal="g",steps=["s"],expected_observations=["o"])]),
        gap_analysis=dict(status="resolved",scanner_calls=[dict(outcome="passed",input_revision=2,tool_ref=r("st"),
                        scope_ref=r("ss"),receipt_ref=r("sr"),findings_ref=r("sf"))],findings=[],unresolved_critical_ids=[]),
        fixture_validation_chaos=dict(status="passed",fixture_refs=["fix"],oracle_evidence_refs=[r("oe")],
                                      chaos_applicability="required",chaos_case_refs=[r("ch")],
                                      prebuild_validation_receipt_refs=[r("fv")],coverage_gaps=[]),
        handoff=dict(to="build",ready=True,plan_artifact_ref=r("ep"),artifact_manifest_ref=r("pm"),validation_receipt_ref=r("pv")))

def _mk_b():
    s, r = _refs()
    b = dict(task_id="t1", revision=2, status="complete", updated_at="2026-10-30T03:00:00Z",
             progress_log=[{"at":"x","r":"d"}], decision_log=[{"at":"x","w":"s"}])
    cp = dict(action_id="a1", action_state="completed", action_receipt_ref=r("action"),
              retry_disposition="not_applicable", source_snapshot_ref=r("snapshot"))
    return s, dict(b, kind="build", record_id="b1", checkpoint=cp,
        plan_input=dict(record_ref=r("pr"),record_id="p1",record_revision=2,artifact_manifest_ref="pm",
                        accepted_milestone_ids=["m1"],accepted_criterion_ids=["c1"]),
        execution=dict(milestone_results=[dict(id="m1",status="passed",artifact_refs=[r("res")])],
                       command_receipts=[dict(id="c",command="py",cwd="/tmp",exit_code=0,receipt_ref=r("cr"))],
                       workspace_snapshot_ref=r("ws"),environment_ref=r("env"),finished_at="2026-10-30T03:00:00Z",
                       artifact_manifest_ref=r("bm")),
        implementation_validation=dict(status="passed",checks=[dict(criterion_id="c1",status="passed",receipt_ref=r("ut"))]),
        post_build_e2e=dict(status="passed",real_entrypoint_ref=r("ent"),environment_ref=r("env"),
                            cases=[dict(fixture_ref="fix",expected_ref="ora",observed_ref=r("obs"),receipt_ref=r("e2e"),status="passed")],
                            chaos_cases=[dict(chaos_ref="ch",observed_ref=r("co"),receipt_ref=r("crec"),status="passed")],
                            independent_result_checks=[dict(criterion_id="c1",expected_ref="ora",observed_ref="obs",
                                                            receipt_ref=r("ac"),status="passed")],coverage_gaps=[]),
        issues_and_corrections=dict(findings=[],blockers=[]),
        outcome=dict(status="verified",user_visible_result_ref=r("result"),
                     criterion_results=[dict(criterion_id="c1",status="passed",evidence_ref=r("e2e"))]),
        handoff=dict(to="complete",ready=True,completion_receipt_ref=r("comp"),validation_receipt_ref=r("bv")))


class TestResearchModel(unittest.TestCase):
    def test_valid_research_parses(self):
        _, r = _mk_r()
        m = models.ResearchRecord.model_validate(r)
        self.assertEqual(m.task_id, "t1")

    def test_placeholder_task_id_rejected(self):
        _, r = _mk_r(); r["task_id"] = "<task_id>"
        with self.assertRaises(Exception): models.ResearchRecord.model_validate(r)

    def test_zero_revision_rejected(self):
        _, r = _mk_r(); r["revision"] = 0
        with self.assertRaises(Exception): models.ResearchRecord.model_validate(r)

    def test_complete_without_progress_log_fails(self):
        _, r = _mk_r(); r["progress_log"] = []
        with self.assertRaises(Exception): models.ResearchRecord.model_validate(r)

    def test_invalid_kind_rejected(self):
        _, r = _mk_r(); r["kind"] = "plan"
        with self.assertRaises(Exception): models.ResearchRecord.model_validate(r)

    def test_extra_fields_allowed(self):
        _, r = _mk_r(); r["custom"] = "x"
        m = models.ResearchRecord.model_validate(r)
        self.assertEqual(m.task_id, "t1")


class TestPlanModel(unittest.TestCase):
    def test_valid_plan_parses(self):
        _, p = _mk_p()
        m = models.PlanRecord.model_validate(p)
        self.assertEqual(m.record_id, "p1")

    def test_milestone_without_steps_fails(self):
        _, p = _mk_p(); p["implementation"]["milestones"][0]["steps"] = []
        with self.assertRaises(Exception): models.PlanRecord.model_validate(p)

    def test_no_milestones_fails(self):
        _, p = _mk_p(); p["implementation"]["milestones"] = []
        with self.assertRaises(Exception): models.PlanRecord.model_validate(p)

    def test_missing_rollback_fails(self):
        _, p = _mk_p(); p["implementation"]["rollback_or_recovery"] = None
        with self.assertRaises(Exception): models.PlanRecord.model_validate(p)

    def test_gap_not_resolved_fails(self):
        _, p = _mk_p(); p["gap_analysis"]["status"] = "findings_open"
        with self.assertRaises(Exception): models.PlanRecord.model_validate(p)

    def test_no_scanner_calls_fails(self):
        _, p = _mk_p(); p["gap_analysis"]["scanner_calls"] = []
        with self.assertRaises(Exception): models.PlanRecord.model_validate(p)

    def test_critical_deferral_fails(self):
        _, p = _mk_p()
        p["gap_analysis"]["findings"] = [dict(id="g1",status="deferred",severity="critical",approval_ref="a",disposition_reason="")]
        with self.assertRaises(Exception): models.PlanRecord.model_validate(p)

    def test_chaos_required_without_cases_fails(self):
        _, p = _mk_p(); p["fixture_validation_chaos"]["chaos_case_refs"] = []
        with self.assertRaises(Exception): models.PlanRecord.model_validate(p)

    def test_chaos_not_checked_fails(self):
        _, p = _mk_p(); p["fixture_validation_chaos"]["chaos_applicability"] = "not_checked"
        with self.assertRaises(Exception): models.PlanRecord.model_validate(p)


class TestBuildModel(unittest.TestCase):
    def test_valid_build_parses(self):
        _, b = _mk_b()
        m = models.BuildRecord.model_validate(b)
        self.assertEqual(m.record_id, "b1")

    def test_no_command_receipts_fails(self):
        _, b = _mk_b(); b["execution"]["command_receipts"] = []
        with self.assertRaises(Exception): models.BuildRecord.model_validate(b)

    def test_outcome_not_verified_fails(self):
        _, b = _mk_b(); b["outcome"]["status"] = "not_verified"
        with self.assertRaises(Exception): models.BuildRecord.model_validate(b)


class TestCheckpoint(unittest.TestCase):
    def test_uncertain_without_reconcile_fails(self):
        with self.assertRaises(Exception): models.Checkpoint(action_state="uncertain", retry_disposition="safe_retry")

    def test_completed_without_action_id_fails(self):
        with self.assertRaises(Exception): models.Checkpoint(action_state="completed", action_id=None)


class TestValidatePipeline(unittest.TestCase):
    def test_valid_pipeline_no_errors(self):
        sr, r = _mk_r(); sp, p = _mk_p(); sb, b = _mk_b()
        refs = sr | sp | sb
        errors = models.validate_pipeline(r, p, b, resolve=refs.__contains__)
        self.assertEqual(errors, [], f"Errors: {errors}")

    def test_task_id_mismatch_detected(self):
        sr, r = _mk_r(); sp, p = _mk_p(); sb, b = _mk_b()
        p["task_id"] = "different"; b["task_id"] = "different"
        refs = sr | sp | sb
        errors = models.validate_pipeline(r, p, b, resolve=refs.__contains__)
        self.assertTrue(any("task_id mismatch" in e for e in errors))

    def test_research_identity_mismatch(self):
        sr, r = _mk_r(); sp, p = _mk_p(); sb, b = _mk_b()
        p["research_input"]["record_id"] = "wrong"
        refs = sr | sp | sb
        errors = models.validate_pipeline(r, p, b, resolve=refs.__contains__)
        self.assertTrue(any("Research identity" in e for e in errors))

    def test_stale_plan_revision(self):
        sr, r = _mk_r(); sp, p = _mk_p(); sb, b = _mk_b()
        b["plan_input"]["record_revision"] = 1
        refs = sr | sp | sb
        errors = models.validate_pipeline(r, p, b, resolve=refs.__contains__)
        self.assertTrue(any("stale Plan" in e for e in errors))


class TestDualLayerCompat(unittest.TestCase):
    """Both validators must agree: pass on valid, fail on invalid."""

    def test_both_pass_valid_research(self):
        sr, r = _mk_r()
        self.assertEqual(models.validate_research(r, sr.__contains__), [])
        models.ResearchRecord.model_validate(r)  # should not raise

    def test_both_pass_valid_plan(self):
        sr, r = _mk_r(); sp, p = _mk_p()
        refs = sr | sp
        self.assertEqual(models.validate_plan(p, r, refs.__contains__), [])
        models.PlanRecord.model_validate(p)

    def test_both_pass_valid_build(self):
        sr, r = _mk_r(); sp, p = _mk_p(); sb, b = _mk_b()
        refs = sr | sp | sb
        self.assertEqual(models.validate_build(b, p, r, refs.__contains__), [])
        models.BuildRecord.model_validate(b)

    def test_both_fail_placeholder(self):
        _, r = _mk_r(); r["task_id"] = "<task_id>"
        self.assertTrue(any("missing task_id" in e for e in models.validate_research(r)))
        with self.assertRaises(Exception): models.ResearchRecord.model_validate(r)

    def test_both_fail_empty_milestone(self):
        _, p = _mk_p(); p["implementation"]["milestones"][0]["steps"] = []
        sr, r = _mk_r()
        self.assertTrue(any("unexecutable" in e for e in models.validate_plan(p, r)))
        with self.assertRaises(Exception): models.PlanRecord.model_validate(p)

    def test_both_fail_no_scanner(self):
        _, p = _mk_p(); p["gap_analysis"]["scanner_calls"] = []
        sr, r = _mk_r()
        self.assertTrue(any("Scanner was not invoked" in e for e in models.validate_plan(p, r)))
        with self.assertRaises(Exception): models.PlanRecord.model_validate(p)

    def test_both_fail_unresolved_gaps(self):
        _, p = _mk_p(); p["gap_analysis"]["status"] = "findings_open"
        sr, r = _mk_r()
        self.assertTrue(any("gap analysis incomplete" in e for e in models.validate_plan(p, r)))
        with self.assertRaises(Exception): models.PlanRecord.model_validate(p)

    def test_both_fail_uncertain_checkpoint(self):
        _, b = _mk_b()
        b["checkpoint"]["action_state"] = "uncertain"
        b["checkpoint"]["retry_disposition"] = "safe_retry"
        sr, r = _mk_r(); sp, p = _mk_p()
        refs = sr | sp
        self.assertTrue(any("reconciled" in e for e in models.validate_build(b, p, r, refs.__contains__)))
        with self.assertRaises(Exception): models.BuildRecord.model_validate(b)

    def test_both_fail_chaos_not_decided(self):
        _, p = _mk_p(); p["fixture_validation_chaos"]["chaos_applicability"] = "not_checked"
        sr, r = _mk_r()
        self.assertTrue(any("chaos applicability not decided" in e for e in models.validate_plan(p, r)))
        with self.assertRaises(Exception): models.PlanRecord.model_validate(p)

    def test_both_fail_critical_deferral(self):
        _, p = _mk_p()
        p["gap_analysis"]["findings"] = [dict(id="g1",status="deferred",severity="critical",approval_ref="a",disposition_reason="")]
        sr, r = _mk_r()
        self.assertTrue(any("critical finding deferred" in e for e in models.validate_pipeline(_mk_p()[1], p, _mk_b()[1], resolve=_refs().__contains__)))
        with self.assertRaises(Exception): models.PlanRecord.model_validate(p)

    def test_both_fail_template_draft(self):
        tpl = {"kind":"research","task_id":"<task_id>","record_id":"<rid>","revision":1,"status":"draft",
               "handoff":{"ready":False},"checkpoint":{"action_state":"none"}}
        with self.assertRaises(Exception): models.ResearchRecord.model_validate(tpl)

    def test_pipeline_matches_pydantic(self):
        sr, r = _mk_r(); sp, p = _mk_p(); sb, b = _mk_b()
        refs = sr | sp | sb
        self.assertEqual(models.validate_pipeline(r, p, b, resolve=refs.__contains__), [])


if __name__ == "__main__":
    unittest.main()


class TestValidatorSafety(unittest.TestCase):
    """Lock in the two safety properties of the per-stage validators.

    Property A: a complete record with no resolver is rejected
                ("no evidence resolver configured ..."), matching
                validate_pipeline's fail-closed behavior.
    Property B: canonical-token prefixes apply only to the specific
                defect they describe. A milestone-missing-observations
                error must NOT be mis-prefixed as "unexecutable".
    """

    def test_research_complete_without_resolver_fails_closed(self):
        _, r = _mk_r()  # status="complete"
        errs = models.validate_research(r)  # no resolver
        self.assertTrue(any("no evidence resolver" in e for e in errs),
                        f"expected fail-closed, got {errs!r}")

    def test_plan_complete_without_resolver_fails_closed(self):
        _, r = _mk_r(); _, p = _mk_p()
        errs = models.validate_plan(p, r)  # no resolver
        self.assertTrue(any("no evidence resolver" in e for e in errs),
                        f"expected fail-closed, got {errs!r}")

    def test_build_complete_without_resolver_fails_closed(self):
        _, r = _mk_r(); _, p = _mk_p(); _, b = _mk_b()
        errs = models.validate_build(b, p, r)  # no resolver
        self.assertTrue(any("no evidence resolver" in e for e in errs),
                        f"expected fail-closed, got {errs!r}")

    def test_canonical_tokens_do_not_mislabel_milestone_observations(self):
        """A milestone that lacks expected_observations should NOT be
        prefixed with 'unexecutable' — that token is for empty steps /
        no-milestones only."""
        _, p = _mk_p()
        # Keep steps so "unexecutable" is NOT a correct label; drop observations.
        p["implementation"]["milestones"][0]["expected_observations"] = []
        sr, r = _mk_r()
        errs = models.validate_plan(p, r, sr.__contains__)
        # Must raise something (missing observations is still an error)
        self.assertTrue(errs, f"expected an error, got {errs!r}")
        # Must NOT be mis-prefixed with 'unexecutable'
        self.assertFalse(any(e.startswith("unexecutable:") for e in errs),
                         f"canonicalization is too broad: {errs!r}")

    def test_plan_task_id_mismatch_detected(self):
        """Cross-record invariant: task_id consistency between plan and research."""
        _, r = _mk_r(); _, p = _mk_p()
        p["task_id"] = "DIFFERENT"
        sr, _ = _mk_r()
        errs = models.validate_plan(p, r, sr.__contains__)
        self.assertTrue(any("task_id mismatch" in e for e in errs),
                        f"expected task_id mismatch, got {errs!r}")

    def test_build_stale_plan_revision_detected(self):
        """Cross-record invariant: build must pin exact plan revision."""
        _, r = _mk_r(); _, p = _mk_p(); _, b = _mk_b()
        # Tamper the plan revision stored on build; keep plan itself at its real revision.
        b["plan_input"]["record_revision"] = 999
        refs = _refs()[0]
        for s in (r, p, b):
            # Pretend every evidence ref resolves so we isolate the staleness check.
            pass
        errs = models.validate_build(b, p, r, lambda ref: True)
        self.assertTrue(any("stale Plan revision" in e for e in errs),
                        f"expected stale Plan revision, got {errs!r}")
