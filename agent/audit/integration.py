"""Inspect whether Audit is exposed inside the existing Research path."""

from __future__ import annotations

import re
from pathlib import Path

from agent.audit.core import Finding, evidence


def scan_integration(root: Path, scope: Path) -> list[Finding]:
    ui = root / "web" / "src" / "main.jsx"
    host = root / "mvp" / "research_host.py"
    if scope != root and not any(path.is_relative_to(scope) for path in (ui, host)):
        return []
    findings: list[Finding] = []
    if ui.is_file():
        text = ui.read_text(encoding="utf-8")
        selector = re.search(r"""(?i)(?:['"]audit['"]|>\s*audit\s*<|audit_mode|auditMode)""", text)
        if selector is None:
            findings.append(
                evidence(
                    root,
                    ui,
                    1,
                    "AUDIT_SELECTOR_NOT_EXPOSED",
                    "integration",
                    "medium",
                    "Checked-in Research UI does not expose a recognizable Audit mode selector.",
                )
            )
    if host.is_file():
        text = host.read_text(encoding="utf-8")
        if "agent.audit" not in text and "audit_guidance" not in text:
            findings.append(
                evidence(
                    root,
                    host,
                    1,
                    "AUDIT_HOST_INVOCATION_UNWIRED",
                    "integration",
                    "medium",
                    "Research host has no recognizable invocation of the Audit capability package.",
                )
            )
    return findings
