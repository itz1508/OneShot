"""Reproducibility checks for declared package-manager dependencies."""

from __future__ import annotations

import json
from pathlib import Path

from agent.audit.core import Finding, evidence


def scan_dependencies(root: Path, scope: Path) -> list[Finding]:
    manifest = root / "web" / "package.json"
    if not manifest.is_file() or (scope != root and not manifest.is_relative_to(scope)):
        return []
    package = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(package, dict):
        raise ValueError("frontend package manifest must be an object")
    if package.get("dependencies") or package.get("devDependencies"):
        locks = ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb")
        if not any((manifest.parent / name).is_file() for name in locks):
            return [
                evidence(
                    root,
                    manifest,
                    1,
                    "FRONTEND_LOCKFILE_MISSING",
                    "dependencies",
                    "medium",
                    "Frontend declares dependencies without a tracked lockfile; reproducible installs are unverified.",
                    status="verified_observation",
                )
            ]
    return []
