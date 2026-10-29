#!/usr/bin/env python3
"""
Tests for OneShot Assignment 02: quality_input.py

Verifies: complete input proceeds, missing input stops, resume preserves
context, ambiguity detected, model text rejected.
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from quality_input import QualityInput, InputResult, InputState


class TestQualityInput:
    """Contract and E2E tests for quality_input.py."""

    def setup_method(self):
        self.qi = QualityInput()

    def test_complete_input_proceeds_without_stop(self):
        """Complete input with all required fields → proceeds without STOP."""
        result = self.qi.validate({
            "task": "Build the OneShot repo-summary script",
            "repository": "https://github.com/itz1508/OneShot",
            "branch": "main",
        })
        assert result.state == InputState.VALID.value
        assert len(result.missing_fields) == 0
        assert len(result.clarifications_needed) == 0

    def test_missing_required_field_triggers_stop(self):
        """Missing required field → STOP, not inference."""
        result = self.qi.validate({
            "repository": "https://github.com/itz1508/OneShot",
        })
        assert result.state == InputState.STOP.value
        assert "task" in result.missing_fields
        assert len(result.clarifications_needed) > 0
        assert result.stop_reason

    def test_resume_after_clarification_preserves_context(self):
        """Resume after clarification → preserves all prior context."""
        original = {
            "repository": "https://github.com/itz1508/OneShot",
            "branch": "main",
        }
        result = self.qi.validate(original)
        assert result.state == InputState.STOP.value

        # Provide clarification
        resumed = self.qi.resume_after_clarification(original, {"task": "Build repo-summary"})
        assert resumed.state == InputState.VALID.value
        # Verify original context preserved
        assert resumed.context["repository"] == "https://github.com/itz1508/OneShot"
        assert resumed.context["branch"] == "main"
        assert resumed.context["task"] == "Build repo-summary"

    def test_ambiguity_detected(self):
        """Ambiguous input (multiple repos) → AMBIGUOUS state."""
        result = self.qi.validate({
            "task": "Build the OneShot repo-summary script",
            "repository": "repo1, repo2, repo3",
        })
        assert result.state == InputState.AMBIGUOUS.value
        assert "repository" in result.ambiguous_fields

    def test_short_task_description_is_ambiguous(self):
        """Very short task description → AMBIGUOUS."""
        result = self.qi.validate({
            "task": "do it",
            "repository": "https://github.com/itz1508/OneShot",
        })
        assert result.state == InputState.AMBIGUOUS.value
        assert "task" in result.ambiguous_fields

    def test_model_text_not_accepted_as_confirmation(self):
        """Model text is not accepted as confirmation."""
        assert self.qi.is_model_text("As an AI, I think you should use the main branch")
        assert self.qi.is_model_text("I suggest using Python 3.12")
        assert not self.qi.is_model_text("main")
        assert not self.qi.is_model_text("https://github.com/itz1508/OneShot")

    def test_preserved_input_not_discarded(self):
        """Original input is preserved and not discarded."""
        original = {"task": "Build repo-summary", "repository": "https://github.com/itz1508/OneShot"}
        result = self.qi.validate(original)
        assert result.preserved_input == original

    def test_prepare_context_for_research(self):
        """Validated input produces context for Research."""
        result = self.qi.validate({
            "task": "Build repo-summary",
            "repository": "https://github.com/itz1508/OneShot",
            "branch": "main",
        })
        context = self.qi.prepare_context_for_research(result)
        assert context["task"] == "Build repo-summary"
        assert context["repository"] == "https://github.com/itz1508/OneShot"
        assert context["user_intent_preserved"] is True
        assert context["source_content_intact"] is True

    def test_prepare_context_rejects_invalid_state(self):
        """prepare_context_for_research raises on non-VALID state."""
        result = self.qi.validate({"repository": "https://github.com/itz1508/OneShot"})
        with pytest.raises(ValueError, match="not valid"):
            self.qi.prepare_context_for_research(result)

    def test_request_clarification_returns_structured_request(self):
        """request_clarification returns structured request, not model text."""
        result = self.qi.validate({"repository": "https://github.com/itz1508/OneShot"})
        clarification = self.qi.request_clarification(result)
        assert clarification["action"] == "request_clarification"
        assert "task" in clarification["missing_fields"]
        assert len(clarification["questions"]) > 0
        assert clarification["preserved_input"]

    def test_optional_fields_use_defaults(self):
        """Optional fields use defaults when not provided."""
        result = self.qi.validate({
            "task": "Build repo-summary script",
            "repository": "https://github.com/itz1508/OneShot",
        })
        assert result.state == InputState.VALID.value
        assert result.context.get("branch") == "main"  # Default applied
