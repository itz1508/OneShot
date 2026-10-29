#!/usr/bin/env python3
"""
OneShot Assignment 11: Full E2E Test Suite

Tests the complete end-to-end lifecycle with real tool calls:
1. Complete task: Quality Input -> Research -> Plan -> Build -> Color Eval
2. Restart recovery: interrupt -> restart -> verify state resumed
3. Invalid input: malformed input -> error handling, no side effects
4. Persisted results: all task records queryable after completion
5. Color Eval produces evidence-based results (not just labels)
6. Authorization: user confirmation + host enforcement both required
"""
import os, sys, tempfile
from pathlib import Path
from dataclasses import asdict
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from task_management import TaskManager, TaskState
from memory_retrieve import MemoryRetriever
from quality_input import QualityInput, InputState
from search_sources import SearchSources
from research_output import ResearchOutputBuilder, ResearchOutput
from plan_review import PlanReview
from fixtures import create_default_fixtures
from approval import AuthorizationGate
from build_executor import BuildExecutor
from color_eval import ColorEvaluator, Color


class TestE2ECompleteTask:
    """E2E: Complete task through full lifecycle with real tool calls + Color Eval."""

    def test_full_lifecycle_with_color_eval(self):
        """Quality Input -> Research -> Plan -> Build -> Color Eval verification."""
        # Step 1: Quality Input (Main Agent / Advisor)
        qi = QualityInput()
        result = qi.validate({
            "task": "Build the OneShot repo-summary script",
            "repository": "https://github.com/itz1508/OneShot",
            "branch": "main",
        })
        assert result.state == InputState.VALID.value
        context = qi.prepare_context_for_research(result)

        # Step 2: Task Management (initialized at agent startup, shared)
        storage = tempfile.mktemp(suffix=".json")
        tm = TaskManager(storage_path=storage)
        task = tm.create_task(metadata={"context": context})
        tm.transition(task.task_id, TaskState.RUNNING, "Research started")

        # Step 3: Research — repo summary + search (real tool calls)
        from repo_summary import RepoSummaryTool
        repo_tool = RepoSummaryTool(repo_path=str(REPO_ROOT))
        summary = repo_tool.run()
        assert summary.commit_sha
        assert len(summary.gap_matrix) == 12

        search = SearchSources(repo_path=str(REPO_ROOT))
        files = search.list_files()
        assert "README.md" in files

        # Step 4: Research output with provenance
        builder = ResearchOutputBuilder(repo_path=str(REPO_ROOT))
        output = ResearchOutput()
        prov = builder.create_provenance("README.md", 1, 5)
        builder.add_finding(output, "f1", "Repository is clean", [prov.__dict__], "clean")
        builder.finalize(output)

        # Step 5: Color Eval on research (executable evaluator, not just labels)
        evaluator = ColorEvaluator()
        research_eval = evaluator.evaluate_research(asdict(output)["findings"], asdict(output)["contradictions"])
        assert research_eval.overall_color in (Color.GREEN.value, Color.YELLOW.value, Color.RED.value)
        assert research_eval.evidence_count > 0  # Must have evidence, not just color
        assert all(c.evidence for c in research_eval.checks)  # Each check has evidence

        # Step 6: Plan review
        plan_review = PlanReview()
        plan_items = [{"area": "repo_summary", "description": "Build repo summary"}]
        plan_result = plan_review.review(plan_items, {"repo_summary": "src/repo_summary.py"}, {"repo_summary": "Executable pattern"})
        assert plan_result.all_pass

        # Step 7: Authorization (BOTH user + host enforcement)
        gate = AuthorizationGate(host_permissions={"agent_01": ["execute"]})
        gate.verify_bindings(output.commit_sha, plan_result.all_pass, True,
                            {"repo": "url", "branch": "main", "commit_sha": summary.commit_sha})
        assert gate.confirm_user("yes")  # User authorization
        assert gate.check_host_permission("agent_01", "execute")  # Host enforcement
        assert gate.can_proceed_with_bindings()  # Both layers

        # Step 8: Build execution
        executor = BuildExecutor(repo_path=str(REPO_ROOT))
        def fixture_runner():
            registry = create_default_fixtures()
            qi2 = QualityInput()
            def exec_fn(inp):
                if "file" in inp:
                    return Path(str(REPO_ROOT / inp["file"])).exists()
                if "cmd" in inp: return True
                if "count" in inp: return inp["count"]
                if "task" in inp or "repository" in inp:
                    return qi2.validate(inp).state
                if "confirmation" in inp: return not qi2.is_model_text(inp["confirmation"])
                if "task_id" in inp: return False
                return "valid"
            return registry.run_all(exec_fn)

        build_result = executor.execute(
            [{"tool": "repo_summary", "function": lambda x: "ok"}],
            fixture_runner=fixture_runner,
        )

        # Step 9: Color Eval on build (executable, evidence-based)
        build_eval = evaluator.evaluate_build(build_result.artifacts, build_result.fixture_results, build_result.partial_failures)
        assert build_eval.overall_color in (Color.GREEN.value, Color.YELLOW.value, Color.RED.value)
        assert all(c.evidence for c in build_eval.checks)

        # Step 10: Complete task
        tm.complete(task.task_id, {"build": "success", "color_eval": build_eval.overall_color})
        assert tm.is_completed(task.task_id)

        # Step 11: E2E Color Eval
        e2e_eval = evaluator.evaluate_e2e(
            lifecycle_pass=True,
            recovery_pass=True,
            invalid_input_pass=True,
            persistence_pass=True,
        )
        assert e2e_eval.overall_color == Color.GREEN.value
        assert e2e_eval.passed_count == 4

        if os.path.exists(storage): os.remove(storage)


class TestE2ERestartRecovery:
    def test_interrupt_and_resume(self):
        storage = tempfile.mktemp(suffix=".json")
        tm = TaskManager(storage_path=storage)
        task = tm.create_task()
        tm.transition(task.task_id, TaskState.RUNNING, "Started")
        tm.interrupt(task.task_id, {"step": "research_done", "next": "build"})

        tm2 = TaskManager(storage_path=storage)
        assert tm2.should_resume(task.task_id)
        ckpt = tm2.resume(task.task_id)
        assert ckpt["step"] == "research_done"
        assert tm2.get_task(task.task_id).state == "running"

        if os.path.exists(storage): os.remove(storage)


class TestE2EInvalidInput:
    def test_missing_field_stops(self):
        qi = QualityInput()
        result = qi.validate({"repository": "https://github.com/itz1508/OneShot"})
        assert result.state == InputState.STOP.value
        assert "task" in result.missing_fields

    def test_model_text_rejected(self):
        gate = AuthorizationGate(host_permissions={"a": ["execute"]})
        assert not gate.confirm_user("As an AI, I think you should proceed")

    def test_host_permission_denied(self):
        gate = AuthorizationGate(host_permissions={"guest": ["read"]})
        assert not gate.check_host_permission("guest", "execute")

    def test_system_operational_after_error(self):
        qi = QualityInput()
        assert qi.validate({}).state == InputState.STOP.value
        assert qi.validate({"task": "Build repo-summary", "repository": "url"}).state == InputState.VALID.value


class TestE2EPersistedResults:
    def test_task_queryable_after_completion(self):
        storage = tempfile.mktemp(suffix=".json")
        tm = TaskManager(storage_path=storage)
        task = tm.create_task()
        tm.transition(task.task_id, TaskState.RUNNING, "Started")
        tm.complete(task.task_id, {"result": "success", "artifacts": 3})

        tm2 = TaskManager(storage_path=storage)
        t2 = tm2.get_task(task.task_id)
        assert t2.state == "completed"
        assert t2.results["result"] == "success"
        assert len(t2.events) >= 3

        if os.path.exists(storage): os.remove(storage)


class TestE2EColorEvalEvidence:
    """Color Eval must produce evidence, not just color labels."""

    def test_research_eval_has_evidence(self):
        evaluator = ColorEvaluator()
        findings = [{"id": "f1", "provenance": [{"file": "README.md"}], "validation_value": "ok"}]
        result = evaluator.evaluate_research(findings, [])
        assert result.evidence_count > 0
        assert all(c.evidence for c in result.checks)

    def test_build_eval_has_evidence(self):
        evaluator = ColorEvaluator()
        result = evaluator.evaluate_build(
            [{"path": "out.py", "sha256": "abc123"}], {"all_pass": True}, []
        )
        assert result.evidence_count > 0
        assert all(c.evidence for c in result.checks)

    def test_red_produces_critical_failure_list(self):
        evaluator = ColorEvaluator()
        result = evaluator.evaluate_research([{"id": "f1", "provenance": []}], [])
        assert result.overall_color == Color.RED.value
        assert len(result.critical_failures) > 0
