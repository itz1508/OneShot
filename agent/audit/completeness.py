"""Surface explicit unfinished implementation markers without inferring runtime failure."""

from __future__ import annotations

import ast
import tokenize
from pathlib import Path

from agent.audit.core import Finding, evidence, python_files


def scan_completeness(root: Path, scope: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in python_files(root, scope):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if len(node.body) != 1:
                continue
            statement = node.body[0]
            exception: ast.expr | None
            if isinstance(statement, ast.Raise) and isinstance(statement.exc, ast.Call):
                exception = statement.exc.func
            elif isinstance(statement, ast.Raise):
                exception = statement.exc
            else:
                exception = None
            if isinstance(exception, ast.Name) and exception.id == "NotImplementedError":
                findings.append(
                    evidence(
                        root,
                        path,
                        statement.lineno,
                        "NOT_IMPLEMENTED_STUB",
                        "completeness",
                        "medium",
                        "Function body raises NotImplementedError; determine if accepted behavior depends on it.",
                    )
                )
        with path.open("rb") as source:
            for token in tokenize.tokenize(source.readline):
                if token.type != tokenize.COMMENT:
                    continue
                if any(marker in token.string.upper() for marker in ("TODO", "FIXME")):
                    findings.append(
                        evidence(
                            root,
                            path,
                            token.start[0],
                            "UNRESOLVED_COMMENT",
                            "completeness",
                            "low",
                            "Source comment requests follow-up; verify relevance against accepted intent.",
                        )
                    )
    return findings
