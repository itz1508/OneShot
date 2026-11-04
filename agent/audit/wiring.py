"""Compare simple literal frontend API fetches to decorated FastAPI routes."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from agent.audit.core import Finding, evidence

_API_PREFIX = re.compile(r"/api/[\w/{}-]+")


def scan_wiring(root: Path, scope: Path) -> list[Finding]:
    # Dynamic frontend URL construction is intentionally not classified as broken.
    api = root / "mvp" / "api.py"
    if not api.is_file() or not (root / "web" / "src").is_dir():
        return []
    tree = ast.parse(api.read_text(encoding="utf-8"), filename=str(api))
    routes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in {"get", "post", "patch", "put", "delete"}
            ):
                value = decorator.args[0].value
                if isinstance(value, str):
                    routes.add(re.sub(r"\{[^}]+\}", "{}", value))
    findings: list[Finding] = []
    for file in sorted((root / "web" / "src").rglob("*.jsx")):
        if not file.is_relative_to(scope) and scope != root:
            continue
        for line_no, line in enumerate(file.read_text(encoding="utf-8").splitlines(), 1):
            for match in _API_PREFIX.finditer(line):
                value = match.group()
                if "'" not in line and '"' not in line:
                    continue
                normalized = re.sub(r"\{[^}]+\}", "{}", value).rstrip("/")
                if normalized not in routes and not any(route.startswith(normalized + "/") for route in routes):
                    findings.append(
                        evidence(
                            root,
                            file,
                            line_no,
                            "API_ROUTE_REVIEW",
                            "wiring",
                            "low",
                            f"Literal API prefix {value!r} not matched to a FastAPI route; "
                            "dynamic URLs require runtime verification.",
                        )
                    )
    return findings
