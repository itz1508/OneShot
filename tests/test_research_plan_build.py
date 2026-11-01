#!/usr/bin/env python3
"""Behavioural tests for the live `tools/` primitives: search_sources,
fixtures, build_executor.

Historical note. This module originally covered the retired numbered-
prompt set (research_output, research_review, plan_review, approval).
Those files were consolidated into `agent/main.py` by commit d90b655;
per PR #8 review item D2 we kept the test classes marked
`@pytest.mark.skip` so coverage status stays visible rather than hidden.

Kept and running:  TestSearchSources, TestFixtures, TestBuildExecutor.
Skipped (D2):      TestResearchOutput, TestResearchReview, TestPlanReview, TestApproval.
"""

from pathlib import Path

import pytest

# conftest.py adds tools/ to sys.path.
from build_executor import BuildExecutor
from fixtures import create_default_fixtures
from search_sources import SearchSources

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Retired modules — importable only if someone restores them under ExecPlan D2.
# Classes that reference these names are decorated with @pytest.mark.skip so
# collection still succeeds and the gap is visible rather than hidden.
# ---------------------------------------------------------------------------
try:
    from research_output import ResearchOutput, ResearchOutputBuilder  # noqa: F401
except ImportError:
    ResearchOutputBuilder = ResearchOutput = None  # type: ignore[assignment]
try:
    from research_review import ColorEval, ResearchReview  # noqa: F401
except ImportError:
    ResearchReview = ColorEval = None  # type: ignore[assignment]
try:
    from plan_review import PlanReview  # noqa: F401
except ImportError:
    PlanReview = None  # type: ignore[assignment]
try:
    from approval import AuthorizationGate  # noqa: F401
except ImportError:
    AuthorizationGate = None  # type: ignore[assignment]


class TestSearchSources:
    """`tools.search_sources.SearchSources` — repository file inventory."""

    def setup_method(self):
        self.search = SearchSources(repo_path=str(REPO_ROOT))

    def test_list_files_includes_agents(self):
        files = self.search.list_files()
        assert "AGENTS.md" in files

    def test_search_by_pattern_finds_agent_dir(self):
        results = self.search.search_by_pattern("agent")
        assert len(results) > 0

    def test_search_by_extension_finds_python(self):
        results = self.search.search_by_extension(".py")
        assert len(results) > 0

    def test_build_inventory_has_file_info(self):
        inventory = self.search.build_inventory()
        assert len(inventory) > 0
        first = inventory[0]
        assert first.path
        assert first.file_type
        assert first.size >= 0


@pytest.mark.skip(
    reason="D2: tools/research_output.py retired by d90b655 — ExecPlan D2 decision pending."
)
class TestResearchOutput:
    """Retired: research_output was consolidated into agent/main.py (D2)."""

    def setup_method(self):
        self.builder = ResearchOutputBuilder(repo_path=str(REPO_ROOT))
        self.output = ResearchOutput()

    def test_create_provenance_has_commit_sha(self):
        prov = self.builder.create_provenance("AGENTS.md", 1, 10)
        assert prov.file_path == "AGENTS.md"
        assert len(prov.commit_sha) == 40

    def test_add_finding_with_provenance(self):
        prov = self.builder.create_provenance("AGENTS.md", 1, 10)
        self.builder.add_finding(
            self.output, "f1", "Test finding", [prov.__dict__], "expected_value"
        )
        assert len(self.output.findings) == 1
        assert self.output.findings[0].validation_value == "expected_value"

    def test_add_contradiction(self):
        prov = self.builder.create_provenance("AGENTS.md", 1, 10)
        self.builder.add_contradiction(self.output, "c1", "Contradiction", [prov.__dict__])
        assert len(self.output.contradictions) == 1
        assert self.output.contradictions[0].is_contradiction is True

    def test_add_open_question(self):
        self.builder.add_open_question(self.output, "What framework?", "Need to decide")
        assert len(self.output.open_questions) == 1

    def test_finalize_sets_commit_sha(self):
        result = self.builder.finalize(self.output)
        assert len(result.commit_sha) == 40


@pytest.mark.skip(
    reason="D2: tools/research_review.py retired by d90b655 — ExecPlan D2 decision pending."
)
class TestResearchReview:
    """Retired: research_review was consolidated into agent/main.py (D2)."""

    def setup_method(self):
        self.review = ResearchReview()

    def test_green_when_all_findings_grounded(self):
        output = {
            "findings": [
                {"id": "f1", "provenance": [{"file_path": "AGENTS.md"}], "validation_value": "ok"}
            ],
            "contradictions": [],
        }
        result = self.review.review(output)
        assert result.color == ColorEval.GREEN.value

    def test_red_when_findings_lack_provenance(self):
        output = {
            "findings": [{"id": "f1", "provenance": [], "validation_value": "ok"}],
            "contradictions": [],
        }
        result = self.review.review(output)
        assert result.color == ColorEval.RED.value
        assert result.findings_without_provenance == 1

    def test_yellow_when_contradictions_exist(self):
        output = {
            "findings": [
                {"id": "f1", "provenance": [{"file_path": "AGENTS.md"}], "validation_value": "ok"}
            ],
            "contradictions": [{"id": "c1", "description": "Conflict"}],
        }
        result = self.review.review(output)
        assert result.color == ColorEval.YELLOW.value
        assert result.contradictions_found == 1


@pytest.mark.skip(
    reason="D2: tools/plan_review.py retired by d90b655 — ExecPlan D2 decision pending."
)
class TestPlanReview:
    """Retired: plan_review was consolidated into agent/main.py (D2)."""

    def setup_method(self):
        self.review = PlanReview()

    def test_pass1_grounding_with_code(self):
        items = [{"area": "color_eval", "description": "Build color eval"}]
        code = {"color_eval": "tools/color_eval.py"}
        results = self.review.pass1_grounding(items, code)
        assert results[0].status == "pass"

    def test_pass1_grounding_without_code(self):
        items = [{"area": "nonexistent", "description": "Nothing"}]
        code = {}
        results = self.review.pass1_grounding(items, code)
        assert results[0].status == "fail"

    def test_pass2_calls_for_help_when_no_practice(self):
        items = [{"area": "unknown_area", "description": "Unknown"}]
        practices = {}
        results = self.review.pass2_best_practice(items, practices)
        assert results[0].status == "call_for_help"

    def test_review_returns_all_pass_when_grounded(self):
        items = [{"area": "color_eval", "description": "Build color eval"}]
        code = {"color_eval": "tools/color_eval.py"}
        practices = {"color_eval": "Executable script pattern"}
        result = self.review.review(items, code, practices)
        assert result.all_pass is True
        assert result.gaps_remaining == 0


class TestFixtures:
    """`tools.fixtures.FixtureRegistry` — G03 independent expected results."""

    def test_default_fixtures_have_5_positive(self):
        registry = create_default_fixtures()
        assert len(registry.get_positive()) >= 5

    def test_default_fixtures_have_5_negative(self):
        registry = create_default_fixtures()
        assert len(registry.get_negative()) >= 5

    def test_expected_results_independent(self):
        registry = create_default_fixtures()
        for case in registry.get_positive():
            assert case.expected_result is not None

    def test_run_positive_with_executor(self):
        registry = create_default_fixtures()

        def executor(inp):
            if inp.get("file") in ("AGENTS.md", ".gitignore"):
                return True
            if inp.get("cmd") == "git rev-parse HEAD":
                return True
            if inp.get("count") == 12:
                return 12
            return "valid"

        results = registry.run_positive(executor)
        assert all(r["passed"] for r in results)


@pytest.mark.skip(
    reason=(
        "D2: tools/approval.py retired by d90b655 — see "
        "tests/test_authorization.py for the migrated user-approval surface."
    )
)
class TestApproval:
    """Retired: approval was consolidated into agent/main.py (D2)."""

    def test_model_text_rejected(self):
        gate = AuthorizationGate(host_permissions={"a": ["execute"]})
        assert not gate.confirm_user("As an AI, I think you should proceed")
        assert gate.state.model_text_rejected

    def test_explicit_user_confirmation_accepted(self):
        gate = AuthorizationGate(host_permissions={"a": ["execute"]})
        assert gate.confirm_user("yes")
        gate.check_host_permission("a", "execute")
        assert gate.can_proceed()

    def test_no_confirmation_blocks(self):
        gate = AuthorizationGate(host_permissions={"a": ["execute"]})
        assert not gate.can_proceed()

    def test_host_permission_denied(self):
        gate = AuthorizationGate(host_permissions={"guest": ["read"]})
        assert not gate.check_host_permission("guest", "execute")

    def test_verify_bindings_all_present(self):
        gate = AuthorizationGate(host_permissions={"a": ["execute"]})
        result = gate.verify_bindings(
            "abc123", True, True, {"repo": "url", "branch": "main", "commit_sha": "sha"}
        )
        assert result["all_present"]


class TestBuildExecutor:
    """`tools.build_executor.BuildExecutor` — artifact hashing + Agent/Tool/Result tracing."""

    def test_call_tool_traces_execution(self):
        executor = BuildExecutor(repo_path=str(REPO_ROOT))
        result = executor.call_tool("test_tool", {"input": 1}, lambda x: x["input"] + 1)
        assert result == 2
        assert len(executor.trace) == 1
        assert executor.trace[0].tool == "test_tool"

    def test_capture_artifact_hashes_file(self):
        executor = BuildExecutor(repo_path=str(REPO_ROOT))
        artifact = executor.capture_artifact("AGENTS.md")
        assert len(artifact.sha256) == 64
        assert artifact.size > 0

    def test_partial_failures_preserved(self):
        executor = BuildExecutor(repo_path=str(REPO_ROOT))
        steps = [
            {"tool": "good", "function": lambda x: "ok"},
            {"tool": "bad", "function": lambda x: (_ for _ in []).throw(ValueError("fail"))},
        ]
        result = executor.execute(steps)
        assert len(result.partial_failures) == 1

    def test_finalize_only_when_all_pass(self):
        executor = BuildExecutor(repo_path=str(REPO_ROOT))
        result = executor.execute([], fixture_runner=lambda: {"all_pass": True})
        assert result.finalized is True

