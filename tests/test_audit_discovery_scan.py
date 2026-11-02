"""Use the production Scanner API to enforce Audit Discovery naming.

Read-only scan over the actual Git-tracked checkout. Historical ownership
compatibility remains intentional; new capability identifiers must not regress.
"""

from __future__ import annotations

from pathlib import Path

from tools.scanner import (
    scan_edit_change,
    scan_filesystems,
    scan_match_variable,
)

ROOT = Path(__file__).resolve().parents[1]
OLD_ROLE = "Builder" + " Discovery"
OLD_SYMBOL = "Builder" + "Discovery"
OLD_MACHINE_ID = "builder" + "_discovery"
OLD_SLUG = "builder" + "-discovery"
OLD_ARTIFACT = "build" + "-discovery"
RULES = [
    {"name": "role", "pattern": OLD_ROLE, "replacement": "Audit Discovery"},
    {"name": "symbol", "pattern": OLD_SYMBOL, "replacement": "AuditDiscovery"},
    {"name": "machine", "pattern": OLD_MACHINE_ID, "replacement": "audit_discovery"},
    {"name": "slug", "pattern": OLD_SLUG, "replacement": "audit-discovery"},
    {"name": "artifact", "pattern": OLD_ARTIFACT, "replacement": "audit-discovery"},
]


def test_renamed_capability_has_no_active_legacy_references() -> None:
    result = scan_match_variable(ROOT, RULES)
    # Immutable historical records are not rewritten; the live code must
    # retain the two read-compatibility predicates.
    allowed = {
        "agent/prompt_authoring/author.py",
        "agent/prompt_authoring/evaluator.py",
    }
    active_matches = [
        match for match in result["matches"]
        if not match["path"].startswith("tests/")
    ]
    assert {match["path"] for match in active_matches} == allowed
    assert all(match["matched"] == OLD_MACHINE_ID for match in active_matches)
    assert len(active_matches) == 2
    for match in active_matches:
        path = ROOT / match["path"]
        line = path.read_text(encoding="utf-8").splitlines()[match["line"] - 1]
        assert "== " in line
        assert OLD_MACHINE_ID in line


def test_no_legacy_capability_artifact_filename_exists() -> None:
    inventory = scan_filesystems(ROOT)
    rejected = (OLD_ROLE.lower(), OLD_SYMBOL.lower(), OLD_MACHINE_ID, OLD_SLUG, OLD_ARTIFACT)
    assert not [
        item["path"]
        for item in inventory["files"]
        if any(part in item["path"].lower() for part in rejected)
    ]


def test_scanner_preview_reports_no_unrenamed_active_guidance() -> None:
    paths = [
        "AGENTS.md",
        "agent/prompt_authoring/README.md",
        "agent/prompt_authoring/types.py",
    ]
    plan = scan_edit_change(ROOT, RULES, paths=paths)
    assert plan["count"] == 0
    assert plan["changes"] == []
