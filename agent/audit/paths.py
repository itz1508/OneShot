"""Filesystem integrity: broken symlinks and repo containment evidence."""

from __future__ import annotations

from pathlib import Path

from agent.audit.core import Finding


def scan_paths(root: Path, scope: Path) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(scope.rglob("*")):
        if any(part in {".git", ".venv", "node_modules", "__pycache__"} for part in path.relative_to(root).parts):
            continue
        if not path.is_symlink():
            continue
        target = path.resolve(strict=False)
        if not target.is_relative_to(root):
            findings.append(
                Finding(
                    "paths",
                    "PATH_OUTSIDE_REPOSITORY",
                    "verified_observation",
                    "medium",
                    path.relative_to(root).as_posix(),
                    0,
                    "Symlink target escapes audited repository; review its authorized use.",
                    "",
                )
            )
        elif not target.exists():
            findings.append(
                Finding(
                    "paths",
                    "BROKEN_SYMLINK",
                    "verified_observation",
                    "low",
                    path.relative_to(root).as_posix(),
                    0,
                    "Symlink target does not exist.",
                    "",
                )
            )
    return findings
