"""Check literal internal Python import targets without importing project modules."""

from __future__ import annotations

import ast
from pathlib import Path

from agent.audit.core import Finding, evidence, python_files


def scan_contracts(root: Path, scope: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in python_files(root, scope):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: tuple[str, ...]
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = (node.module,)
            elif isinstance(node, ast.Import):
                names = tuple(alias.name for alias in node.names)
            else:
                continue
            for name in names:
                if not name.startswith(("agent.", "mvp.")):
                    continue
                if not (root / name.split(".")[0]).is_dir():
                    continue
                rel = root.joinpath(*name.split("."))
                if not rel.with_suffix(".py").is_file() and not (rel / "__init__.py").is_file():
                    findings.append(
                        evidence(
                            root,
                            path,
                            node.lineno,
                            "INTERNAL_IMPORT_MISSING",
                            "contracts",
                            "high",
                            f"Internal import target {name!r} is not present as a Python module or package.",
                        )
                    )
    return findings
