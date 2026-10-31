#!/usr/bin/env python3
"""Tests for the gap analysis capability preflight.

The old GapAnalysisSpecialist (counterfeit detector) was removed.
All eight-category capability tests now use the real Scanner via
CapabilityPreflight. See test_capability_preflight.py for the full
coverage of all eight categories, controller integration, and repair loops.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from gap_analysis import CapabilityPreflight, CapabilityVerdict

# GapAnalysisSpecialist was removed; skip tests that depend on it.
try:
    from gap_analysis import FindingStatus, GapAnalysisSpecialist
except ImportError:
    GapAnalysisSpecialist = None
    FindingStatus = None

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

_skip_old = pytest.mark.skipif(
    GapAnalysisSpecialist is None,
    reason="GapAnalysisSpecialist removed; see test_capability_preflight.py",
)


def test_preflight_has_eight_categories():
    assert len(CapabilityPreflight.CATEGORIES) == 8
    expected = {
        "drift",
        "missing",
        "duplication",
        "contradictions",
        "coverage",
        "dependencies",
        "feasibility",
        "cli_docs",
    }
    assert set(CapabilityPreflight.CATEGORIES) == expected


def test_preflight_all_categories_valid():
    pf = CapabilityPreflight()
    result = pf.run()
    for cat in result.categories:
        assert cat.verdict == CapabilityVerdict.VALID.value, f"{cat.category}: {cat.evidence}"
    assert result.aggregate_verdict == CapabilityVerdict.VALID.value
    assert result.can_proceed is True
    assert result.coverage_complete is True


@_skip_old
class TestMissingCategory:
    """Test the missing category — missing required files and functions."""

    def test_detects_missing_required_function(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "agent").mkdir(parents=True)
            (root / "agent" / "contracts").mkdir(parents=True)
            (root / "agent" / "main.py").write_text("# stub")
            (root / "tools").mkdir(parents=True)
            (root / "tools" / "task_management.py").write_text("# stub")
            (root / "tools" / "color_eval.py").write_text("# stub")
            # Missing validate_research, validate_plan, etc.
            (root / "agent" / "contracts" / "check_contracts.py").write_text(
                "def validate_records(): pass\n"
            )
            for yf in ["research.yaml", "plan.yaml", "build.yaml"]:
                (root / "agent" / "contracts" / yf).write_text("kind: stub\n")
            specialist = GapAnalysisSpecialist(root)
            result = specialist.analyze(check_categories=["missing"])
            func_findings = [f for f in result.findings if "func" in f.id]
            assert any("validate_research" in f.id for f in func_findings)


@_skip_old
class TestDuplicationCategory:
    """Test the duplication category — real overlap vs delegation."""

    def test_detects_real_function_duplication(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "tools").mkdir(parents=True)
            (root / "tools" / "a.py").write_text("def compute():\n    return 42\n")
            (root / "tools" / "b.py").write_text("def compute():\n    return 99\n")
            specialist = GapAnalysisSpecialist(root)
            result = specialist.analyze(check_categories=["duplication"])
            dup_findings = [f for f in result.findings if f.category == "duplication"]
            assert any("compute" in f.id for f in dup_findings)

    def test_no_false_positive_for_delegation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "tools").mkdir(parents=True)
            (root / "tools" / "core.py").write_text("def shared():\n    return 1\n")
            (root / "tools" / "wrapper.py").write_text(
                "from core import shared\ndef shared():\n    return core.shared()\n"
            )
            specialist = GapAnalysisSpecialist(root)
            result = specialist.analyze(check_categories=["duplication"])
            dup_findings = [f for f in result.findings if "shared" in f.id]
            # Delegation pattern should not be flagged
            assert len(dup_findings) == 0 or all(
                f.status == FindingStatus.FALSE_POSITIVE.value for f in dup_findings
            )

    def test_no_false_positive_for_main_entry_points(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "tools").mkdir(parents=True)
            (root / "tools" / "a.py").write_text("def main():\n    pass\n")
            (root / "tools" / "b.py").write_text("def main():\n    pass\n")
            specialist = GapAnalysisSpecialist(root)
            result = specialist.analyze(check_categories=["duplication"])
            dup_findings = [f for f in result.findings if "main" in f.id]
            assert len(dup_findings) == 0

    def test_no_false_positive_for_class_methods(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "tools").mkdir(parents=True)
            (root / "tools" / "a.py").write_text("class A:\n    def review(self):\n    pass\n")
            (root / "tools" / "b.py").write_text("class B:\n    def review(self):\n    pass\n")
            specialist = GapAnalysisSpecialist(root)
            result = specialist.analyze(check_categories=["duplication"])
            dup_findings = [f for f in result.findings if "review" in f.id]
            assert len(dup_findings) == 0  # Methods, not top-level functions


@_skip_old
class TestContradictionsCategory:
    """Test the contradictions category — hardcoded results, auto-resolve."""

    def test_detects_hardcoded_green(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "tools").mkdir(parents=True)
            (root / "tools" / "repo_summary.py").write_text(
                'color_eval="GREEN"  # All start GREEN\n'
            )
            specialist = GapAnalysisSpecialist(root)
            result = specialist.analyze(check_categories=["contradictions"])
            contra_findings = [f for f in result.findings if f.category == "contradictions"]
            assert any("hardcoded" in f.id for f in contra_findings)

    def test_detects_auto_resolve_pattern(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "agent").mkdir(parents=True)
            (root / "agent" / "main.py").write_text(
                '"status": "open" if is_missing else "resolved"\n'
            )
            specialist = GapAnalysisSpecialist(root)
            result = specialist.analyze(check_categories=["contradictions"])
            contra_findings = [f for f in result.findings if f.category == "contradictions"]
            assert any("auto-resolve" in f.id for f in contra_findings)


@_skip_old
class TestCoverageCategory:
    """Test the coverage category — missing test scenarios."""

    def test_detects_missing_test_pattern(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "tests").mkdir(parents=True)
            (root / "tests" / "test_dummy.py").write_text("# no tests here\n")
            specialist = GapAnalysisSpecialist(root)
            result = specialist.analyze(check_categories=["coverage"])
            coverage_findings = [f for f in result.findings if f.category == "coverage"]
            assert len(coverage_findings) > 0


@_skip_old
class TestFeasibilityCategory:
    """Test the feasibility category — code that cannot execute."""

    def test_detects_missing_build_target(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            specialist = GapAnalysisSpecialist(root)
            result = specialist.analyze(check_categories=["feasibility"])
            feas_findings = [f for f in result.findings if f.category == "feasibility"]
            assert any("counter" in f.id.lower() for f in feas_findings)


@_skip_old
class TestRecheckFlow:
    """Test the gap→fix→recheck flow."""

    def test_recheck_marks_resolved_findings(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "agent").mkdir(parents=True)
            (root / "agent" / "main.py").write_text("# stub")
            (root / "tools").mkdir(parents=True)
            (root / "tools" / "task_management.py").write_text("# stub")
            (root / "tools" / "color_eval.py").write_text("# stub")
            (root / "agent" / "contracts").mkdir(parents=True)
            (root / "agent" / "contracts" / "check_contracts.py").write_text(
                "def validate_records(): pass\n"
                "def validate_research(): pass\n"
                "def validate_plan(): pass\n"
                "def validate_build(): pass\n"
                "def preflight_check(): pass\n"
                "def evidence_index_resolver(): pass\n"
            )
            for yf in ["research.yaml", "plan.yaml", "build.yaml"]:
                (root / "agent" / "contracts" / yf).write_text("kind: stub\n")

            # First run: missing build target
            specialist = GapAnalysisSpecialist(root)
            result1 = specialist.analyze(check_categories=["feasibility"])
            assert len(result1.open_findings) > 0

            # Fix: create the build target
            (root / "bin").mkdir(parents=True)
            (root / "bin" / "context_counter.py").write_text("# counter")

            # Recheck — runs all categories
            specialist2 = GapAnalysisSpecialist(root)
            result2 = specialist2.recheck(result1)
            # Check that the feasibility finding is resolved
            resolved = [f for f in result2.findings if f.status == FindingStatus.RESOLVED.value]
            feas_resolved = [f for f in resolved if f.category == "feasibility"]
            assert any("counter" in f.id.lower() for f in feas_resolved)


@_skip_old
class TestEndToEndOnRealRepo:
    """Run the specialist against the actual repo and verify findings."""

    def test_all_categories_checked_on_real_repo(self):
        specialist = GapAnalysisSpecialist(REPO_ROOT)
        result = specialist.analyze()
        assert len(result.categories_checked) == 8
        assert len(result.categories_skipped) == 0

    def test_real_repo_has_no_critical_open_after_fixes(self):
        specialist = GapAnalysisSpecialist(REPO_ROOT)
        result = specialist.analyze()
        # After fixing the real gaps, there should be no critical open findings
        critical = result.critical_open
        if critical:
            for f in critical:
                print(f"  CRITICAL: {f.id} — {f.evidence}")
        assert len(critical) == 0, f"Critical open findings remain: {[f.id for f in critical]}"

    def test_findings_have_source_refs(self):
        specialist = GapAnalysisSpecialist(REPO_ROOT)
        result = specialist.analyze()
        for finding in result.findings:
            assert finding.source_ref, f"Finding {finding.id} has no source_ref"
            assert finding.evidence, f"Finding {finding.id} has no evidence"
