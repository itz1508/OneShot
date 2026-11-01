"""Audit item 06.6: BuildExecutor must refuse steps without a callable
`function` instead of silently calling a no-op lambda."""

from __future__ import annotations

import unittest

from build_executor import BuildExecutor  # type: ignore[import-not-found]


class BuildExecutorAuthorizationTest(unittest.TestCase):
    def test_missing_function_is_refused(self):
        ex = BuildExecutor()
        res = ex.execute([{"tool": "write_file", "input": {"path": "x"}}])
        # No trace entry — the step never ran.
        self.assertEqual(ex.trace, [])
        # One partial failure with the specific error.
        self.assertEqual(len(res.partial_failures), 1)
        self.assertEqual(res.partial_failures[0]["step"], "write_file")
        self.assertIn("unauthorized_tool_fn", res.partial_failures[0]["error"])
        self.assertFalse(res.finalized)

    def test_non_callable_function_is_refused(self):
        ex = BuildExecutor()
        res = ex.execute([{"tool": "write_file", "input": {}, "function": "not-a-callable"}])
        self.assertEqual(ex.trace, [])
        self.assertEqual(len(res.partial_failures), 1)
        self.assertIn("unauthorized_tool_fn", res.partial_failures[0]["error"])

    def test_valid_callable_runs(self):
        calls = []

        def _tool(inp):
            calls.append(inp)
            return {"ok": True}

        ex = BuildExecutor()
        res = ex.execute([{"tool": "write_file", "input": {"x": 1}, "function": _tool}])
        self.assertEqual(calls, [{"x": 1}])
        self.assertEqual(res.partial_failures, [])


if __name__ == "__main__":
    unittest.main()
