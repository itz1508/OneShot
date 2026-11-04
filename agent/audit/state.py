"""Static host ownership and receipt-binding audits, not runtime proof."""

from __future__ import annotations

import ast
from pathlib import Path

from agent.audit.core import Finding, evidence


def scan_state(root: Path, scope: Path) -> list[Finding]:
    controller = root / "agent" / "runtime" / "controller.py"
    if not controller.is_file() or (scope != root and not controller.is_relative_to(scope)):
        return []
    tree = ast.parse(controller.read_text(encoding="utf-8"), filename=str(controller))
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.name != "issue_stage_receipt":
            continue
        params = {a.arg for a in node.args.args}
        if not {"revision", "artifact_digest"} <= params:
            continue
        subject_values = [
            call.value
            for call in ast.walk(node)
            if isinstance(call, ast.Assign)
            for target in call.targets
            if isinstance(target, ast.Name) and target.id == "subject"
        ]
        references = {
            part.value.id
            for subject in subject_values
            for part in ast.walk(subject)
            if isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.Name)
        }
        missing = {"revision", "artifact_digest"} - references
        if missing:
            findings.append(
                evidence(
                    root,
                    controller,
                    node.lineno,
                    "RECEIPT_SUBJECT_UNBOUND",
                    "state",
                    "high",
                    "Stage receipt subject omits accepted identity fields: " + ", ".join(sorted(missing)) + ".",
                    status="verified_observation",
                )
            )
    return findings
