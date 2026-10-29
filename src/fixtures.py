#!/usr/bin/env python3
"""
OneShot Assignment 07: Fixtures with Independent Expected Results

Positive cases (known-good → expected pass) and negative cases (known-bad →
expected fail). Expected results are independent — not derived from implementation
output. Fixture data grounded in actual repository state.
"""

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class FixtureCase:
    """A single fixture case."""
    name: str
    input: dict
    expected_result: Any  # Defined BEFORE execution, independent
    expected_pass: bool  # True for positive, False for negative
    description: str = ""


class FixtureRegistry:
    """Registry of fixture cases with independent expected results."""

    def __init__(self):
        self._positive: list[FixtureCase] = []
        self._negative: list[FixtureCase] = []

    def add_positive(self, name: str, input_data: dict, expected: Any, desc: str = ""):
        """Add a positive case (known-good → expected pass)."""
        self._positive.append(FixtureCase(name, input_data, expected, True, desc))

    def add_negative(self, name: str, input_data: dict, expected: Any, desc: str = ""):
        """Add a negative case (known-bad → expected fail)."""
        self._negative.append(FixtureCase(name, input_data, expected, False, desc))

    def get_positive(self) -> list[FixtureCase]:
        return list(self._positive)

    def get_negative(self) -> list[FixtureCase]:
        return list(self._negative)

    def run_positive(self, executor: Callable) -> list[dict]:
        """Run all positive cases. Each must pass with expected result."""
        results = []
        for case in self._positive:
            actual = executor(case.input)
            passed = (actual == case.expected_result)
            results.append({
                "name": case.name, "expected_pass": True, "passed": passed,
                "expected": case.expected_result, "actual": actual,
            })
        return results

    def run_negative(self, executor: Callable) -> list[dict]:
        """Run all negative cases. Each must fail (not match expected)."""
        results = []
        for case in self._negative:
            try:
                actual = executor(case.input)
                # Negative case: execution should fail or not match expected
                passed = (actual != case.expected_result) or actual is None
            except Exception:
                passed = True  # Exception is expected for negative cases
            results.append({
                "name": case.name, "expected_pass": False, "passed": passed,
            })
        return results

    def run_all(self, executor: Callable) -> dict:
        """Run all fixtures and return summary."""
        pos_results = self.run_positive(executor)
        neg_results = self.run_negative(executor)
        all_pass = all(r["passed"] for r in pos_results + neg_results)
        return {
            "positive": pos_results,
            "negative": neg_results,
            "all_pass": all_pass,
            "positive_count": len(pos_results),
            "negative_count": len(neg_results),
        }


def create_default_fixtures() -> FixtureRegistry:
    """Create default fixtures grounded in actual OneShot repository state."""
    registry = FixtureRegistry()

    # Positive: known-good inputs with independent expected results
    registry.add_positive(
        "valid_input_proceeds",
        {"task": "Build repo-summary script", "repository": "https://github.com/itz1508/OneShot"},
        expected="valid",
        desc="Complete input should proceed without STOP"
    )
    registry.add_positive(
        "git_rev_parse_returns_sha",
        {"cmd": "git rev-parse HEAD"},
        expected=True,
        desc="git rev-parse HEAD returns valid SHA"
    )
    registry.add_positive(
        "readme_exists",
        {"file": "README.md"},
        expected=True,
        desc="README.md exists in repository"
    )
    registry.add_positive(
        "gitignore_exists",
        {"file": ".gitignore"},
        expected=True,
        desc=".gitignore exists in repository"
    )
    registry.add_positive(
        "repo_has_12_gap_areas",
        {"count": 12},
        expected=12,
        desc="Gap matrix has exactly 12 areas"
    )

    # Negative: known-bad inputs with expected failures
    registry.add_negative(
        "missing_task_stops",
        {"repository": "https://github.com/itz1508/OneShot"},
        expected="valid",
        desc="Missing task field should trigger STOP, not proceed"
    )
    registry.add_negative(
        "nonexistent_file",
        {"file": "nonexistent.py"},
        expected=True,
        desc="Nonexistent file should not be found"
    )
    registry.add_negative(
        "model_text_as_confirmation",
        {"confirmation": "As an AI, I think this is correct"},
        expected=True,
        desc="Model text should not be accepted as confirmation"
    )
    registry.add_negative(
        "empty_repo_has_no_source",
        {"pattern": "*.py"},
        expected=True,
        desc="Empty repo should not have Python source files initially"
    )
    registry.add_negative(
        "duplicate_execution_blocked",
        {"task_id": "already-completed"},
        expected=True,
        desc="Duplicate execution should be blocked"
    )

    return registry
