#!/usr/bin/env python3
"""
OneShot Color Eval: Evidence-Based Evaluator

An executable evaluator that runs checks against actual outputs and produces
independent evaluation results. Not merely GREEN/YELLOW/RED text labels.

Evaluates: groundedness, completeness, contradictions, critical failures.
A confirmed RED in any check makes the entire evaluation RED — no averaging.
"""

from dataclasses import dataclass, field
from enum import Enum


class Color(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"


@dataclass
class CheckResult:
    name: str
    color: str
    evidence: str
    details: str = ""


@dataclass
class EvalResult:
    overall_color: str
    checks: list = field(default_factory=list)
    critical_failures: list = field(default_factory=list)
    evidence_count: int = 0
    passed_count: int = 0


class ColorEvaluator:
    """Executable, evidence-based evaluator."""

    def evaluate_research(self, findings: list, contradictions: list) -> EvalResult:
        """Evaluate research output for groundedness and completeness."""
        checks = []
        critical = []
        evidence_count = 0
        passed_count = 0

        # Check 1: Groundedness — every finding must have provenance
        with_prov = 0
        without_prov = 0
        for f in findings:
            prov = f.get("provenance") if isinstance(f, dict) else getattr(f, "provenance", None)
            if prov:
                with_prov += 1
                evidence_count += 1
            else:
                without_prov += 1

        if without_prov == 0 and with_prov > 0:
            checks.append(
                CheckResult(
                    "groundedness", Color.GREEN.value, f"{with_prov} findings with provenance"
                )
            )
            passed_count += 1
        elif with_prov > 0:
            checks.append(
                CheckResult(
                    "groundedness", Color.RED.value, f"{without_prov} findings lack provenance"
                )
            )
            critical.append(f"{without_prov} findings without provenance")
        else:
            checks.append(
                CheckResult("groundedness", Color.RED.value, "No findings with provenance")
            )
            critical.append("No grounded findings")

        # Check 2: Completeness — every finding must have validation value
        with_val = 0
        without_val = 0
        for f in findings:
            val = (
                f.get("validation_value")
                if isinstance(f, dict)
                else getattr(f, "validation_value", None)
            )
            if val:
                with_val += 1
            else:
                without_val += 1

        if without_val == 0 and with_val > 0:
            checks.append(
                CheckResult(
                    "completeness", Color.GREEN.value, f"{with_val} findings with validation"
                )
            )
            passed_count += 1
        elif with_val > 0:
            checks.append(
                CheckResult(
                    "completeness", Color.YELLOW.value, f"{without_val} findings lack validation"
                )
            )
        else:
            checks.append(
                CheckResult("completeness", Color.RED.value, "No findings with validation")
            )
            critical.append("No validated findings")

        # Check 3: Contradictions
        if len(contradictions) == 0:
            checks.append(CheckResult("contradictions", Color.GREEN.value, "No contradictions"))
            passed_count += 1
        else:
            checks.append(
                CheckResult(
                    "contradictions",
                    Color.YELLOW.value,
                    f"{len(contradictions)} contradictions found",
                )
            )

        # Overall: critical failure = RED
        if critical:
            overall = Color.RED.value
        elif all(c.color == Color.GREEN.value for c in checks):
            overall = Color.GREEN.value
        else:
            overall = Color.YELLOW.value

        return EvalResult(
            overall_color=overall,
            checks=checks,
            critical_failures=critical,
            evidence_count=evidence_count,
            passed_count=passed_count,
        )

    def evaluate_build(
        self, artifacts: list, fixture_results: dict, partial_failures: list
    ) -> EvalResult:
        """Evaluate build output for artifacts, fixtures, and failures."""
        checks = []
        critical = []
        evidence_count = 0
        passed_count = 0

        # Check 1: Artifacts produced and hashed
        if artifacts and all(a.get("sha256") for a in artifacts):
            checks.append(
                CheckResult(
                    "artifacts", Color.GREEN.value, f"{len(artifacts)} artifacts with SHA-256"
                )
            )
            evidence_count += len(artifacts)
            passed_count += 1
        elif artifacts:
            checks.append(
                CheckResult("artifacts", Color.YELLOW.value, "Some artifacts missing hashes")
            )
        else:
            checks.append(CheckResult("artifacts", Color.RED.value, "No artifacts produced"))
            critical.append("No artifacts")

        # Check 2: Fixtures pass
        if fixture_results.get("all_pass"):
            checks.append(CheckResult("fixtures", Color.GREEN.value, "All fixtures pass"))
            passed_count += 1
        else:
            checks.append(CheckResult("fixtures", Color.RED.value, "Fixtures failed"))
            critical.append("Fixture failures")

        # Check 3: No partial failures
        if not partial_failures:
            checks.append(CheckResult("no_failures", Color.GREEN.value, "No partial failures"))
            passed_count += 1
        else:
            checks.append(
                CheckResult(
                    "no_failures", Color.RED.value, f"{len(partial_failures)} partial failures"
                )
            )
            critical.append(f"{len(partial_failures)} partial failures")

        if critical:
            overall = Color.RED.value
        elif all(c.color == Color.GREEN.value for c in checks):
            overall = Color.GREEN.value
        else:
            overall = Color.YELLOW.value

        return EvalResult(
            overall_color=overall,
            checks=checks,
            critical_failures=critical,
            evidence_count=evidence_count,
            passed_count=passed_count,
        )

    def evaluate_e2e(
        self,
        lifecycle_pass: bool,
        recovery_pass: bool,
        invalid_input_pass: bool,
        persistence_pass: bool,
    ) -> EvalResult:
        """Evaluate E2E test results."""
        checks = [
            CheckResult(
                "complete_lifecycle",
                Color.GREEN.value if lifecycle_pass else Color.RED.value,
                "Lifecycle passed" if lifecycle_pass else "Lifecycle failed",
            ),
            CheckResult(
                "restart_recovery",
                Color.GREEN.value if recovery_pass else Color.RED.value,
                "Recovery passed" if recovery_pass else "Recovery failed",
            ),
            CheckResult(
                "invalid_input",
                Color.GREEN.value if invalid_input_pass else Color.RED.value,
                "Invalid input handled" if invalid_input_pass else "Invalid input not handled",
            ),
            CheckResult(
                "persisted_results",
                Color.GREEN.value if persistence_pass else Color.RED.value,
                "Results persisted" if persistence_pass else "Results not persisted",
            ),
        ]
        critical = [c.name for c in checks if c.color == Color.RED.value]
        passed = sum(1 for c in checks if c.color == Color.GREEN.value)
        overall = Color.RED.value if critical else Color.GREEN.value

        return EvalResult(
            overall_color=overall,
            checks=checks,
            critical_failures=critical,
            evidence_count=4,
            passed_count=passed,
        )
