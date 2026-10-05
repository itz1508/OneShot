#!/usr/bin/env python3
"""PyMuPDF import gate (Spec §6, gate 3 + ADR 0007).

FAILS if:
  - any .py under oneshot/backend/src/rsm imports `fitz` (as a module name), OR
  - pyproject.toml declares `fitz` as a dependency.

The accepted install is `pymupdf`; `import pymupdf` is the only form permitted.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "oneshot" / "backend" / "src" / "rsm"
PYPROJECT = ROOT / "oneshot" / "backend" / "pyproject.toml"


def _bad_import(path: Path) -> list[str]:
    hits: list[str] = []
    try:
        tree = ast.parse(path.read_text("utf-8"))
    except SyntaxError:
        return hits
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "fitz" or alias.name.startswith("fitz."):
                    hits.append(f"{path.relative_to(ROOT)}: 'import {alias.name}' is forbidden; use pymupdf")
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "fitz" or node.module.startswith("fitz.")):
                hits.append(f"{path.relative_to(ROOT)}: 'from {node.module} import ...' is forbidden; use pymupdf")
    return hits


def main() -> int:
    violations: list[str] = []
    for p in SRC.rglob("*.py"):
        violations.extend(_bad_import(p))

    if PYPROJECT.exists():
        text = PYPROJECT.read_text("utf-8")
        # Simple textual check in dependency list
        if re.search(r'(^|[\s"\'])fitz(\s*[<>=!~]|["\']|$)', text, re.MULTILINE):
            violations.append("pyproject.toml declares 'fitz' as a dependency; use 'pymupdf'")

    if violations:
        print("PYMUPDF/FITZ VIOLATIONS:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print("pymupdf-import gate OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
