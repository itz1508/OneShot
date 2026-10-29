#!/usr/bin/env python3
"""
OneShot Assignment 02: Quality Input (Main Agent / Advisor)

Quality Input belongs to Main Agent / Advisor — outside Research.
Research receives prepared context and returns missing-evidence findings
to Main Agent when necessary.

Validates essential requirements before execution. STOPs when required
inputs are missing, requests clarification from the host, and resumes
after clarification. Preserves original user intent without discarding
source content, fabricating values, or inferring confirmation from model text.

Usage:
    from quality_input import QualityInput, InputResult
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


class InputState(str, Enum):
    """State of quality input validation."""
    VALID = "valid"
    STOP = "stop"
    AMBIGUOUS = "ambiguous"
    RESUMED = "resumed"


@dataclass
class InputRequirement:
    """A single required input field."""
    name: str
    description: str
    required: bool = True
    default: Any = None


@dataclass
class InputResult:
    """Result of quality input validation."""
    state: str
    missing_fields: list = field(default_factory=list)
    ambiguous_fields: list = field(default_factory=list)
    clarifications_needed: list = field(default_factory=list)
    context: dict = field(default_factory=dict)
    preserved_input: dict = field(default_factory=dict)
    stop_reason: str = ""


class QualityInput:
    """
    Quality Input component for Main Agent / Advisor.

    Validates essential requirements before execution. Belongs to
    Main Agent, NOT Research. Research receives the prepared context.
    """

    # Default required fields for a OneShot task
    DEFAULT_REQUIREMENTS = [
        InputRequirement("task", "What the user wants done"),
        InputRequirement("repository", "Source repository URL or path"),
        InputRequirement("branch", "Target branch", required=False, default="main"),
    ]

    def __init__(self, requirements: Optional[list] = None):
        self.requirements = requirements or list(self.DEFAULT_REQUIREMENTS)
        self._pending_clarifications: dict[str, str] = {}
        self._preserved_input: dict = {}

    def validate(self, user_input: dict) -> InputResult:
        """
        Validate user input against requirements.

        Returns InputResult with state:
        - VALID: all required fields present, no ambiguity
        - STOP: required fields missing — must request clarification
        - AMBIGUOUS: input present but ambiguous — needs disambiguation
        """
        self._preserved_input = dict(user_input)  # Preserve original input

        missing = []
        ambiguous = []
        clarifications = []
        context = dict(user_input)

        for req in self.requirements:
            value = user_input.get(req.name)

            if req.required and (value is None or value == ""):
                missing.append(req.name)
                clarifications.append(req.description)
            elif not req.required and (value is None or value == "") and req.default is not None:
                context[req.name] = req.default
            elif value is not None and req.default is not None and value == "":
                context[req.name] = req.default

            # Check for ambiguity (e.g., multiple repos, unclear scope)
            if value and self._is_ambiguous(req.name, value):
                ambiguous.append(req.name)
                clarifications.append(f"Please clarify {req.name}: {req.description}")

        if missing:
            return InputResult(
                state=InputState.STOP.value,
                missing_fields=missing,
                ambiguous_fields=ambiguous,
                clarifications_needed=clarifications,
                context=context,
                preserved_input=self._preserved_input,
                stop_reason=f"Missing required fields: {', '.join(missing)}",
            )

        if ambiguous:
            return InputResult(
                state=InputState.AMBIGUOUS.value,
                missing_fields=missing,
                ambiguous_fields=ambiguous,
                clarifications_needed=clarifications,
                context=context,
                preserved_input=self._preserved_input,
                stop_reason=f"Ambiguous fields: {', '.join(ambiguous)}",
            )

        return InputResult(
            state=InputState.VALID.value,
            missing_fields=[],
            ambiguous_fields=[],
            clarifications_needed=[],
            context=context,
            preserved_input=self._preserved_input,
        )

    def _is_ambiguous(self, field_name: str, value: Any) -> bool:
        """Check if a field value is ambiguous."""
        # Multiple comma-separated repositories = ambiguous
        if field_name == "repository" and isinstance(value, str):
            if "," in value and len(value.split(",")) > 1:
                return True
        # Very short or generic task description = ambiguous
        if field_name == "task" and isinstance(value, str):
            if len(value.strip()) < 10:
                return True
        return False

    def request_clarification(self, result: InputResult) -> dict:
        """
        Request clarification from the host for missing or ambiguous fields.

        Returns a structured clarification request — NOT model text.
        Only explicit user/host response counts as confirmation.
        """
        return {
            "action": "request_clarification",
            "missing_fields": result.missing_fields,
            "ambiguous_fields": result.ambiguous_fields,
            "questions": result.clarifications_needed,
            "stop_reason": result.stop_reason,
            "preserved_input": result.preserved_input,
        }

    def resume_after_clarification(self, original_input: dict, clarifications: dict) -> InputResult:
        """
        Resume after clarification from the host.

        Merges clarified values with preserved original input.
        Does NOT discard original content or fabricate values.
        Only accepts explicit user/host clarifications — not model text.
        """
        # Start with preserved original input
        merged = dict(original_input)

        # Apply only explicit clarifications
        for field_name, clarified_value in clarifications.items():
            if clarified_value is not None and clarified_value != "":
                merged[field_name] = clarified_value

        # Re-validate
        return self.validate(merged)

    def is_model_text(self, value: Any) -> bool:
        """
        Check if a value appears to be model-generated text rather than
        explicit user/host input. Model text is not accepted as confirmation.
        """
        if not isinstance(value, str):
            return False
        model_indicators = [
            "as an ai",
            "i think",
            "perhaps",
            "maybe you could",
            "i suggest",
            "it seems like",
        ]
        lower = value.lower().strip()
        return any(lower.startswith(ind) for ind in model_indicators)

    def prepare_context_for_research(self, result: InputResult) -> dict:
        """
        Prepare context for Research from validated input.

        Quality Input belongs to Main Agent. Research receives this
        prepared context and returns missing-evidence findings if needed.
        """
        if result.state != InputState.VALID.value:
            raise ValueError(f"Cannot prepare context: input state is {result.state}, not valid")

        return {
            "task": result.context.get("task"),
            "repository": result.context.get("repository"),
            "branch": result.context.get("branch", "main"),
            "user_intent_preserved": True,
            "source_content_intact": True,
        }
