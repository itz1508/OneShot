"""Discover verification surfaces; never claim tests were executed."""

from __future__ import annotations

from pathlib import Path

from agent.audit.core import Finding


def scan_verification(root: Path, scope: Path) -> list[Finding]:
    tests = root / "tests"
    if scope == root and (not tests.exists() or not any(tests.rglob("test_*.py"))):
        return [
            Finding(
                "verification",
                "NO_PYTHON_TESTS_DISCOVERED",
                "verified_observation",
                "medium",
                "tests",
                0,
                "No conventional Python test modules discovered; test coverage remains unverified.",
                "",
            )
        ]
    return []
