#!/usr/bin/env python3
"""Fixture registry with independent expected results (G03 contract).

Positive cases carry a known-good input + an expected result pinned
BEFORE execution. Negative cases carry an `expected_rejection` shape
that pins the exact failure identity: either
  * `{"exception_type": "<ClassName>"}` — the executor must raise an
    exception whose class name matches, or
  * `{"expected_result": <value>}` — the executor must return exactly
    that value (useful for structured error dicts, None, "", etc.).

The shape is the G03 reopen fix: a non-matching exception or a
non-matching result both count as failure, closing the gap where any
exception was previously treated as pass. The legacy "any exception
counts" behaviour remains available when `expected_rejection` is
omitted, but is marked for retirement.

Used by `tools.build_executor.BuildExecutor` and exercised by
`tests/scenarios/test_fixtures_negative_shape.py`.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class FixtureCase:
    """A single fixture case.

    For NEGATIVE cases, prefer `expected_rejection` to pin the shape of the
    expected failure. Two shapes are supported:
      * `{"exception_type": "<ClassName>"}` — the executor must raise an
        exception whose qualified or unqualified class name equals the
        given name.
      * `{"expected_result": <value>}` — the executor must return exactly
        the given value (e.g. a specific error dict / None / "" and NOT
        any mismatching value).
    When `expected_rejection` is omitted the historical rule applies:
    any exception OR any result != `expected_result` counts as pass; this
    is retained only for backward compatibility and SHOULD NOT be relied
    on by new tests.
    """

    name: str
    input: dict
    expected_result: Any  # Defined BEFORE execution, independent
    expected_pass: bool  # True for positive, False for negative
    description: str = ""
    expected_rejection: dict | None = None


class FixtureRegistry:
    """Registry of fixture cases with independent expected results."""

    def __init__(self):
        self._positive: list[FixtureCase] = []
        self._negative: list[FixtureCase] = []

    def add_positive(self, name: str, input_data: dict, expected: Any, desc: str = ""):
        """Add a positive case (known-good → expected pass)."""
        self._positive.append(FixtureCase(name, input_data, expected, True, desc))

    def add_negative(
        self,
        name: str,
        input_data: dict,
        expected: Any,
        desc: str = "",
        expected_rejection: dict | None = None,
    ):
        """Add a negative case (known-bad → expected fail).

        See FixtureCase for the `expected_rejection` shape. New callers
        SHOULD pass `expected_rejection` to make the negative case assert
        the specific safety boundary that must fire.
        """
        self._negative.append(
            FixtureCase(name, input_data, expected, False, desc, expected_rejection)
        )

    def get_positive(self) -> list[FixtureCase]:
        return list(self._positive)

    def get_negative(self) -> list[FixtureCase]:
        return list(self._negative)

    def run_positive(self, executor: Callable) -> list[dict]:
        """Run all positive cases. Each must pass with expected result."""
        results = []
        for case in self._positive:
            actual = executor(case.input)
            passed = actual == case.expected_result
            results.append(
                {
                    "name": case.name,
                    "expected_pass": True,
                    "passed": passed,
                    "expected": case.expected_result,
                    "actual": actual,
                }
            )
        return results

    def run_negative(self, executor: Callable) -> list[dict]:
        """Run all negative cases.

        When `case.expected_rejection` is set, the specific rejection shape
        must match; a mismatched or unrelated failure fails the case. When
        it is absent, backwards-compat applies (any exception OR a result
        != `expected_result` passes), with a `warning` field reporting
        the loose rule used.
        """
        results = []
        for case in self._negative:
            observed_exc: Exception | None = None
            actual: Any = None
            try:
                actual = executor(case.input)
            except Exception as e:  # noqa: BLE001 — we classify below
                observed_exc = e

            exp = case.expected_rejection
            warning: str | None = None
            if exp:
                if "exception_type" in exp:
                    want = exp["exception_type"]
                    passed = observed_exc is not None and (
                        type(observed_exc).__qualname__ == want
                        or type(observed_exc).__name__ == want
                    )
                    rejection_kind = "exception"
                elif "expected_result" in exp:
                    passed = observed_exc is None and actual == exp["expected_result"]
                    rejection_kind = "result"
                else:
                    passed = False
                    rejection_kind = "misconfigured"
                    warning = (
                        "expected_rejection must contain 'exception_type' or 'expected_result'"
                    )
            else:
                # Backwards-compatible loose rule — flagged with a warning.
                passed = (
                    observed_exc is not None or actual != case.expected_result or actual is None
                )
                rejection_kind = "exception" if observed_exc is not None else "result_mismatch"
                warning = (
                    "legacy negative-case rule in use; set expected_rejection "
                    "to pin the required rejection shape"
                )

            results.append(
                {
                    "name": case.name,
                    "expected_pass": False,
                    "passed": passed,
                    "rejection_kind": rejection_kind,
                    "observed_exception": (type(observed_exc).__name__ if observed_exc else None),
                    "observed_result": actual,
                    "warning": warning,
                }
            )
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
        desc="Complete input should proceed without STOP",
    )
    registry.add_positive(
        "git_rev_parse_returns_sha",
        {"cmd": "git rev-parse HEAD"},
        expected=True,
        desc="git rev-parse HEAD returns valid SHA",
    )
    registry.add_positive(
        "gitignore_exists",
        {"file": ".gitignore"},
        expected=True,
        desc=".gitignore exists in repository",
    )
    registry.add_positive(
        "repo_has_12_gap_areas", {"count": 12}, expected=12, desc="Gap matrix has exactly 12 areas"
    )
    registry.add_positive(
        "agents_md_exists",
        {"file": "AGENTS.md"},
        expected=True,
        desc="AGENTS.md exists in repository",
    )

    # Negative: known-bad inputs with expected failures
    registry.add_negative(
        "missing_task_stops",
        {"repository": "https://github.com/itz1508/OneShot"},
        expected="valid",
        desc="Missing task field should trigger STOP, not proceed",
    )
    registry.add_negative(
        "nonexistent_file",
        {"file": "nonexistent.py"},
        expected=True,
        desc="Nonexistent file should not be found",
    )
    registry.add_negative(
        "model_text_as_confirmation",
        {"confirmation": "As an AI, I think this is correct"},
        expected=True,
        desc="Model text should not be accepted as confirmation",
    )
    registry.add_negative(
        "empty_repo_has_no_source",
        {"pattern": "*.py"},
        expected=True,
        desc="Empty repo should not have Python source files initially",
    )
    registry.add_negative(
        "duplicate_execution_blocked",
        {"task_id": "already-completed"},
        expected=True,
        desc="Duplicate execution should be blocked",
    )

    return registry
