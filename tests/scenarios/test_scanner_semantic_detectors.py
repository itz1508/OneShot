"""Semantic Scanner detectors (G02).

Audit's central objection: duplication was represented by an added file,
contradictions by a modified file, coverage by a deleted test file. These
tests exercise the new SemanticGapAnalysis detectors that operate on the
actual semantic signal — AST-level duplication, in-source REQUIREMENT
marker conflicts, requirement-id references in tests, and
AST-level import cycles / plan-step prerequisite ordering.

Each test includes a NEGATIVE control that satisfies the surface change
(file added / modified / missing) but NOT the semantic criterion.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
for sub in ("agent",):
    sp = str(_REPO / sub)
    if sp not in sys.path:
        sys.path.insert(0, sp)

from gap_analysis import SemanticGapAnalysis  # noqa: E402


class DuplicationDetectorTest(unittest.TestCase):
    def test_two_files_same_public_callable_same_arity_flagged(self):
        sources = {
            "tools/foo.py": "def compute(a, b):\n    return a + b\n",
            "tools/bar.py": "def compute(a, b):\n    return a - b\n",
        }
        findings = SemanticGapAnalysis().detect_duplication(sources)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "duplication")
        self.assertEqual(findings[0].kind, "duplicate_callable_name")
        self.assertIn("compute", findings[0].affected_subject)

    def test_two_files_but_private_names_not_flagged(self):
        sources = {
            "tools/foo.py": "def _compute(a, b):\n    return a + b\n",
            "tools/bar.py": "def _compute(a, b):\n    return a - b\n",
        }
        self.assertEqual(SemanticGapAnalysis().detect_duplication(sources), [])

    def test_different_arity_not_flagged(self):
        sources = {
            "tools/foo.py": "def helper(a):\n    return a\n",
            "tools/bar.py": "def helper(a, b):\n    return (a, b)\n",
        }
        self.assertEqual(SemanticGapAnalysis().detect_duplication(sources), [])


class ContradictionsDetectorTest(unittest.TestCase):
    def test_conflicting_requirement_values_flagged(self):
        sources = {
            "agent/a.py": "# REQUIREMENT: R1 = 42\n",
            "agent/b.py": "# REQUIREMENT: R1 = 99\n",
        }
        findings = SemanticGapAnalysis().detect_contradictions(sources)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "contradictions")
        self.assertEqual(findings[0].kind, "conflicting_requirement_assertion")
        self.assertEqual(findings[0].affected_requirement_id, "R1")

    def test_file_modified_but_no_requirement_asserted_not_flagged(self):
        sources = {
            "agent/a.py": "# just a comment change\n",
            "agent/b.py": "# just a comment change\n",
        }
        self.assertEqual(SemanticGapAnalysis().detect_contradictions(sources), [])

    def test_agreeing_requirement_values_not_flagged(self):
        sources = {
            "agent/a.py": "# REQUIREMENT: R1 = 42\n",
            "agent/b.py": "# REQUIREMENT: R1 = 42\n",
        }
        self.assertEqual(SemanticGapAnalysis().detect_contradictions(sources), [])


class CoverageDetectorTest(unittest.TestCase):
    def test_uncovered_requirement_flagged(self):
        findings = SemanticGapAnalysis().detect_coverage(
            requirement_ids=["R_UNCOVERED"],
            test_sources={"tests/test_other.py": "assert something_unrelated()"},
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].category, "coverage")
        self.assertEqual(findings[0].kind, "uncovered_requirement")
        self.assertEqual(findings[0].affected_requirement_id, "R_UNCOVERED")

    def test_test_file_exists_but_does_not_mention_requirement_still_flagged(self):
        findings = SemanticGapAnalysis().detect_coverage(
            requirement_ids=["R_UNCOVERED"],
            test_sources={"tests/test_me.py": "def test_me(): pass"},
        )
        self.assertEqual(len(findings), 1)

    def test_requirement_referenced_in_test_not_flagged(self):
        findings = SemanticGapAnalysis().detect_coverage(
            requirement_ids=["R_COVERED"],
            test_sources={"tests/test_me.py": "# R_COVERED validated by this test\n"},
        )
        self.assertEqual(findings, [])

    def test_substring_not_counted_as_coverage(self):
        """`R_COVER` must NOT satisfy `R_COVERED` — word boundary."""
        findings = SemanticGapAnalysis().detect_coverage(
            requirement_ids=["R_COVERED"],
            test_sources={"tests/x.py": "# R_COVER something else\n"},
        )
        self.assertEqual(len(findings), 1)


class DependenciesDetectorTest(unittest.TestCase):
    def test_import_cycle_flagged(self):
        sources = {
            "tools/alpha.py": "from beta import x\n",
            "tools/beta.py": "from alpha import y\n",
        }
        findings = SemanticGapAnalysis().detect_dependency_violations(sources)
        self.assertIn("import_cycle", [f.kind for f in findings])

    def test_prerequisite_order_violation_flagged(self):
        findings = SemanticGapAnalysis().detect_dependency_violations(
            sources={}, plan_steps=[{"id": "m1", "depends_on": ["m0"]}, {"id": "m0"}]
        )
        self.assertIn("prerequisite_order_violation", [f.kind for f in findings])

    def test_missing_import_but_no_cycle_not_flagged_as_cycle(self):
        sources = {
            "tools/alpha.py": "from beta import x\n",
            "tools/gamma.py": "pass\n",
        }
        self.assertEqual(
            [f.kind for f in SemanticGapAnalysis().detect_dependency_violations(sources)],
            [],
        )


if __name__ == "__main__":
    unittest.main()


class CLIEntrypointExemptionTest(unittest.TestCase):
    """Gap-analysis review of 26cf698: the duplication detector flagged
    `main/0` across five CLI scripts (agent/main.py, bin/*.py, tools/*.py)
    as a duplicate callable. Those are per-module CLI entrypoints guarded
    by `if __name__ == "__main__":` — the project convention, not a
    duplicated responsibility.

    After the fix, `detect_duplication` recognises the `__main__` guard
    and excludes `main` / `cli` / `run` from the duplication report when
    the module is a CLI script.
    """

    _CLI_HEAD = (
        "def {name}():\n"
        "    pass\n"
        "\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit({name}())\n"
    )

    def test_cli_main_entrypoints_not_flagged(self):
        sources = {
            "bin/a.py": self._CLI_HEAD.format(name="main"),
            "bin/b.py": self._CLI_HEAD.format(name="main"),
            "tools/c.py": self._CLI_HEAD.format(name="main"),
        }
        findings = SemanticGapAnalysis().detect_duplication(sources)
        self.assertEqual(
            findings,
            [],
            f"CLI `main` entrypoints must not be flagged as duplication; got {findings}",
        )

    def test_non_cli_duplicate_main_still_flagged(self):
        """A module WITHOUT a `__main__` guard that defines `main` is not a
        CLI entrypoint — the detector must still flag it when two such
        modules share the same `main` signature."""
        sources = {
            "tools/foo.py": "def main():\n    pass\n",
            "tools/bar.py": "def main():\n    pass\n",
        }
        findings = SemanticGapAnalysis().detect_duplication(sources)
        self.assertEqual(len(findings), 1)
        self.assertIn("main", findings[0].affected_subject)

    def test_cli_other_public_name_still_flagged(self):
        """The exemption is narrow — a CLI script's other PUBLIC callable
        (not `main` / `cli` / `run`) is still a duplication finding when
        another file shares the same name/arity."""
        sources = {
            "bin/a.py": (
                "def helper(x):\n"
                "    return x\n"
                "\n"
                "def main():\n"
                "    pass\n"
                "\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
            "tools/b.py": "def helper(x):\n    return x\n",
        }
        findings = SemanticGapAnalysis().detect_duplication(sources)
        self.assertEqual(len(findings), 1)
        self.assertIn("helper", findings[0].affected_subject)
