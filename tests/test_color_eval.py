#!/usr/bin/env python3
"""Tests for Color Eval — executable evidence-based evaluator."""
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from color_eval import ColorEvaluator, Color, EvalResult


class TestColorEval:
    def setup_method(self):
        self.evaluator = ColorEvaluator()

    def test_research_green_all_grounded(self):
        findings = [{"id": "f1", "provenance": [{"file": "AGENTS.md"}], "validation_value": "ok"}]
        result = self.evaluator.evaluate_research(findings, [])
        assert result.overall_color == Color.GREEN.value
        assert result.passed_count == 3

    def test_research_red_ungrounded(self):
        findings = [{"id": "f1", "provenance": [], "validation_value": "ok"}]
        result = self.evaluator.evaluate_research(findings, [])
        assert result.overall_color == Color.RED.value
        assert len(result.critical_failures) > 0

    def test_research_yellow_contradictions(self):
        findings = [{"id": "f1", "provenance": [{"file": "AGENTS.md"}], "validation_value": "ok"}]
        result = self.evaluator.evaluate_research(findings, [{"id": "c1"}])
        assert result.overall_color == Color.YELLOW.value

    def test_build_green_all_pass(self):
        result = self.evaluator.evaluate_build(
            [{"path": "out.py", "sha256": "abc123"}],
            {"all_pass": True}, []
        )
        assert result.overall_color == Color.GREEN.value

    def test_build_red_no_artifacts(self):
        result = self.evaluator.evaluate_build([], {"all_pass": True}, [])
        assert result.overall_color == Color.RED.value

    def test_build_red_fixture_failure(self):
        result = self.evaluator.evaluate_build(
            [{"path": "out.py", "sha256": "abc"}],
            {"all_pass": False}, []
        )
        assert result.overall_color == Color.RED.value

    def test_e2e_all_pass(self):
        result = self.evaluator.evaluate_e2e(True, True, True, True)
        assert result.overall_color == Color.GREEN.value
        assert result.passed_count == 4

    def test_e2e_any_fail_is_red(self):
        result = self.evaluator.evaluate_e2e(True, False, True, True)
        assert result.overall_color == Color.RED.value
        assert "restart_recovery" in result.critical_failures

    def test_eval_produces_evidence_not_just_labels(self):
        findings = [{"id": "f1", "provenance": [{"file": "AGENTS.md"}], "validation_value": "ok"}]
        result = self.evaluator.evaluate_research(findings, [])
        assert result.evidence_count > 0
        assert all(c.evidence for c in result.checks)
        assert all(c.name for c in result.checks)
