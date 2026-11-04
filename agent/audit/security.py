"""Find security-sensitive source patterns as candidates, not confirmed exploits."""

from __future__ import annotations

import ast
from pathlib import Path

from agent.audit.core import Finding, evidence, python_files

DANGEROUS = {("subprocess", "run"), ("subprocess", "Popen"), ("os", "system")}


def scan_security(root: Path, scope: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in python_files(root, scope):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            f = node.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and (f.value.id, f.attr) in DANGEROUS:
                findings.append(
                    evidence(
                        root,
                        path,
                        node.lineno,
                        "COMMAND_EXECUTION_REVIEW",
                        "security",
                        "medium",
                        "Command execution call site requires trust-boundary review.",
                    )
                )
            if any(
                kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True
                for kw in node.keywords
            ):
                findings.append(
                    evidence(
                        root,
                        path,
                        node.lineno,
                        "SHELL_TRUE_REVIEW",
                        "security",
                        "high",
                        "shell=True call site requires injection review.",
                    )
                )
    return findings
