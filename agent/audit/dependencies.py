"""Read-only dependency reproducibility checks for the selected frontend package manager."""

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
    declared = {kind: package.get(kind, {}) for kind in ("dependencies", "devDependencies")}
    if not all(isinstance(values, dict) for values in declared.values()):
        raise ValueError("frontend dependencies must be mappings")

    locks = ("package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb")
    present = [manifest.parent / name for name in locks if (manifest.parent / name).is_file()]
    if not present and any(declared.values()):
        return [
            evidence(
                root,
                manifest,
                1,
                "FRONTEND_LOCKFILE_MISSING",
                "dependencies",
                "medium",
                "Frontend declares dependencies without a lockfile; reproducible installs are unverified.",
                status="verified_observation",
            )
        ]
    findings: list[Finding] = []
    if len(present) > 1:
        findings.append(
            evidence(
                root,
                manifest,
                1,
                "MULTIPLE_FRONTEND_LOCKFILES",
                "dependencies",
                "medium",
                "Multiple package-manager lockfiles exist; verify the authoritative installation method.",
            )
        )
    for lockfile in present:
        if lockfile.name not in {"package-lock.json", "npm-shrinkwrap.json"}:
            continue
        try:
            lock = json.loads(lockfile.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            lock = None
        version = lock.get("lockfileVersion") if isinstance(lock, dict) else None
        if isinstance(version, bool) or not isinstance(version, int) or version not in (1, 2, 3):
            findings.append(
                evidence(
                    root,
                    lockfile,
                    1,
                    "INVALID_NPM_LOCKFILE",
                    "dependencies",
                    "high",
                    "npm lockfile is missing a supported lockfileVersion or contains invalid JSON.",
                    status="verified_observation",
                )
            )
            continue
        if version >= 2:
            packages = lock.get("packages")
            entry = packages.get("") if isinstance(packages, dict) else None
            if not isinstance(entry, dict) or any(
                entry.get(kind, {}) != values for kind, values in declared.items()
            ):
                findings.append(
                    evidence(
                        root,
                        lockfile,
                        1,
                        "FRONTEND_LOCKFILE_MANIFEST_MISMATCH",
                        "dependencies",
                        "high",
                        "npm root lockfile dependency declarations do not match package.json.",
                        status="verified_observation",
                    )
                )
    return findings
