"""Tightened negative-case rule for FixtureRegistry (audit item 05.3).

The old behaviour accepted ANY mismatching result or ANY exception as
a passing negative case. The new behaviour requires an
`expected_rejection` shape that pins the specific safety boundary.

These tests exercise both the strict rule and the backward-compatible
loose rule's warning so a future contributor can tell what is deprecated.
"""

from __future__ import annotations

import unittest

from fixtures import FixtureRegistry  # type: ignore[import-not-found]


class StrictNegativeShapeTest(unittest.TestCase):
    def test_exception_shape_fires(self):
        reg = FixtureRegistry()
        reg.add_negative(
            "zero_division_expected",
            {"n": 0},
            expected=None,
            expected_rejection={"exception_type": "ZeroDivisionError"},
        )

        def executor(inp):
            return 1 / inp["n"]  # raises ZeroDivisionError

        [r] = reg.run_negative(executor)
        self.assertTrue(r["passed"])
        self.assertEqual(r["rejection_kind"], "exception")
        self.assertEqual(r["observed_exception"], "ZeroDivisionError")
        self.assertIsNone(r["warning"])

    def test_exception_shape_unrelated_failure_rejected(self):
        """An unrelated exception no longer passes a negative case."""
        reg = FixtureRegistry()
        reg.add_negative(
            "expect_zero_division",
            {"n": 0},
            expected=None,
            expected_rejection={"exception_type": "ZeroDivisionError"},
        )

        def executor(inp):
            raise OSError("unrelated failure")

        [r] = reg.run_negative(executor)
        self.assertFalse(r["passed"])
        self.assertEqual(r["observed_exception"], "OSError")

    def test_result_shape_fires(self):
        reg = FixtureRegistry()
        reg.add_negative(
            "returns_error_dict",
            {"x": "bad"},
            expected=None,
            expected_rejection={"expected_result": {"error": "invalid_input", "code": 400}},
        )

        def executor(inp):
            return {"error": "invalid_input", "code": 400}

        [r] = reg.run_negative(executor)
        self.assertTrue(r["passed"])
        self.assertEqual(r["rejection_kind"], "result")
        self.assertIsNone(r["observed_exception"])
        self.assertIsNone(r["warning"])

    def test_result_shape_mismatch_fails(self):
        """Returning *something else* (even an unrelated error) does NOT pass."""
        reg = FixtureRegistry()
        reg.add_negative(
            "wants_specific_error",
            {"x": "bad"},
            expected=None,
            expected_rejection={"expected_result": {"error": "invalid_input", "code": 400}},
        )

        def executor(inp):
            return {"error": "something_else", "code": 500}

        [r] = reg.run_negative(executor)
        self.assertFalse(r["passed"])


class LegacyNegativeShapeTest(unittest.TestCase):
    """Backward-compat path: when expected_rejection is omitted the loose
    rule still applies but attaches a `warning` so callers can migrate."""

    def test_legacy_rule_still_passes_but_warns(self):
        reg = FixtureRegistry()
        reg.add_negative("legacy", {"x": 1}, expected={"ok": True}, desc="legacy call")

        def executor(inp):
            raise OSError("ok even though unrelated")

        [r] = reg.run_negative(executor)
        self.assertTrue(r["passed"])
        self.assertIn("legacy negative-case rule", r["warning"])


if __name__ == "__main__":
    unittest.main()
