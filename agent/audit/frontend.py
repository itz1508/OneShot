"""Read-only frontend integration observations against the existing Research API."""

from __future__ import annotations

import re
from pathlib import Path

from agent.audit.core import Finding, evidence


def scan_frontend(root: Path, scope: Path) -> list[Finding]:
    source = root / "web" / "src" / "main.jsx"
    api = root / "mvp" / "api.py"
    if not source.is_file() or not api.is_file():
        return []
    if scope != root and not source.is_relative_to(scope) and not api.is_relative_to(scope):
        return []
    ui = source.read_text(encoding="utf-8")
    backend = api.read_text(encoding="utf-8")
    findings: list[Finding] = []
    literal_call = any(marker in ui for marker in ("'/research'", '"/research"', "`/research`"))
    dynamic_route = re.search(r"const\s+(\w+)\s*=\s*[^\n;]*['\"]research['\"]", ui)
    dynamic_call = bool(
        dynamic_route
        and "fetch('/api/tasks/'" in ui
        and re.search(r"\+\s*['\"]\/['\"]\s*\+\s*" + dynamic_route.group(1) + r"\b", ui)
    )
    if '@app.post("/api/tasks/{task_id}/research")' in backend and not (literal_call or dynamic_call):
        findings.append(
            evidence(
                root,
                source,
                1,
                "RESEARCH_ACTION_UNWIRED",
                "frontend",
                "high",
                "Research HTTP endpoint exists, but the UI has no recognized Research invocation suffix; "
                "verify dynamic call paths before assigning a fix.",
            )
        )
    if "setEditText(task?.input_text || '')" in ui and "setActiveFile(file)" in ui:
        findings.append(
            evidence(
                root,
                source,
                1,
                "ARTIFACT_EDITOR_INPUT_ALIAS",
                "frontend",
                "medium",
                "Artifact selection initializes editor with task input rather than selected artifact content.",
            )
        )
    if "MCP integration pending" in ui:
        findings.append(
            evidence(
                root,
                source,
                1,
                "STATIC_MCP_WARNING",
                "frontend",
                "low",
                "A hardcoded pending warning may contradict actual Research completion state.",
            )
        )
    return findings
