#!/usr/bin/env python3
"""Package-boundary gate (Spec §6, gate 1).

Rules:
  - rsm.bucket.*         must not import cli | api | mcp_server | daemon | transports | extraction
  - rsm.lifecycle.*      must not import anything outside rsm.bucket + stdlib
  - rsm.transports.*     must not import daemon | cli | api | mcp_server
  - rsm.classification.* must not import cli | api | daemon | mcp_server | transports | extraction
  - rsm.execution.*      must not import cli | api | daemon | mcp_server | transports | extraction
  - rsm.replay.*         must not import cli | api | daemon | mcp_server
  - rsm.normalization.*  must not import cli | api | daemon | mcp_server | transports
  - rsm.snapshot.*       must not import cli | api | daemon | mcp_server | transports
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "oneshot" / "backend" / "src" / "rsm"

FORBIDDEN = {
    "rsm.bucket":         {"rsm.cli", "rsm.api", "rsm.mcp_server", "rsm.daemon", "rsm.transports", "rsm.extraction", "rsm.interaction"},
    "rsm.lifecycle":      {"rsm.cli", "rsm.api", "rsm.mcp_server", "rsm.daemon", "rsm.transports", "rsm.extraction", "rsm.provenance", "rsm.integrity", "rsm.config", "rsm.classification", "rsm.execution", "rsm.replay", "rsm.normalization", "rsm.snapshot", "rsm.interaction", "rsm.reader"},
    "rsm.transports":     {"rsm.daemon", "rsm.cli", "rsm.api", "rsm.mcp_server", "rsm.interaction"},
    "rsm.classification": {"rsm.cli", "rsm.api", "rsm.daemon", "rsm.mcp_server", "rsm.transports", "rsm.extraction", "rsm.interaction"},
    "rsm.execution":      {"rsm.cli", "rsm.api", "rsm.daemon", "rsm.mcp_server", "rsm.transports", "rsm.extraction", "rsm.interaction"},
    "rsm.replay":         {"rsm.cli", "rsm.api", "rsm.daemon", "rsm.mcp_server", "rsm.interaction"},
    "rsm.normalization":  {"rsm.cli", "rsm.api", "rsm.daemon", "rsm.mcp_server", "rsm.transports", "rsm.interaction"},
    "rsm.snapshot":       {"rsm.cli", "rsm.api", "rsm.daemon", "rsm.mcp_server", "rsm.transports", "rsm.interaction"},
    # V3: rsm.interaction is a daemon-side auxiliary record (same discipline as
    # classification/execution). It depends only on stdlib + pydantic.
    "rsm.interaction":    {"rsm.cli", "rsm.api", "rsm.daemon", "rsm.mcp_server", "rsm.transports", "rsm.extraction", "rsm.bucket", "rsm.snapshot", "rsm.replay", "rsm.normalization", "rsm.classification", "rsm.execution", "rsm.lifecycle", "rsm.integrity", "rsm.provenance", "rsm.config"},
    # V3 Reader architecture: rsm.reader is a pure observation module over a
    # frozen Bucket. It depends only on stdlib + pydantic + rsm.bucket.
    # V3 Vision architecture: rsm.vision is a small, framework-independent
    # Vision capability. It uses only stdlib + pydantic — NO other rsm.*
    # module is imported. Consumers (reader/agent) depend on the capability,
    # not the other way round.
    "rsm.vision":         {"rsm.cli", "rsm.api", "rsm.daemon", "rsm.mcp_server", "rsm.transports", "rsm.extraction", "rsm.snapshot", "rsm.replay", "rsm.normalization", "rsm.classification", "rsm.execution", "rsm.lifecycle", "rsm.integrity", "rsm.provenance", "rsm.config", "rsm.interaction", "rsm.reader", "rsm.bucket"},
    "rsm.reader":         {"rsm.cli", "rsm.api", "rsm.daemon", "rsm.mcp_server", "rsm.transports", "rsm.extraction", "rsm.snapshot", "rsm.replay", "rsm.normalization", "rsm.classification", "rsm.execution", "rsm.lifecycle", "rsm.integrity", "rsm.provenance", "rsm.config", "rsm.interaction"},
    # V3 Source Assessment: pure, read-only, framework-independent.
    # Uses only stdlib + pydantic + rsm.bucket + rsm.reader.
    "rsm.assessment":     {"rsm.cli", "rsm.api", "rsm.daemon", "rsm.mcp_server", "rsm.transports", "rsm.extraction", "rsm.snapshot", "rsm.replay", "rsm.normalization", "rsm.classification", "rsm.execution", "rsm.lifecycle", "rsm.integrity", "rsm.provenance", "rsm.config", "rsm.interaction", "rsm.vision"},
    # V3 Prepared Representation: typed envelope at the Processor→Replay
    # boundary. Composes existing stable DTOs; depends on bucket + reader
    # + snapshot + replay + assessment. Must not import api/daemon/cli/mcp.
    "rsm.prepared":       {"rsm.cli", "rsm.api", "rsm.daemon", "rsm.mcp_server", "rsm.transports", "rsm.extraction", "rsm.normalization", "rsm.classification", "rsm.execution", "rsm.lifecycle", "rsm.integrity", "rsm.provenance", "rsm.config", "rsm.interaction", "rsm.vision"},
    # V6 Loading: attachment/runtime dirs + archive enumerator. stdlib only.
    "rsm.loading":        {"rsm.cli", "rsm.api", "rsm.daemon", "rsm.mcp_server", "rsm.transports", "rsm.extraction", "rsm.snapshot", "rsm.replay", "rsm.normalization", "rsm.classification", "rsm.execution", "rsm.lifecycle", "rsm.integrity", "rsm.provenance", "rsm.config", "rsm.interaction", "rsm.vision", "rsm.reader", "rsm.assessment", "rsm.prepared", "rsm.bucket"},
}


def _module_for(path: Path) -> str:
    rel = path.relative_to(ROOT.parents[0]).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _package_for(module: str, prefixes: list[str]) -> str | None:
    for p in prefixes:
        if module == p or module.startswith(p + "."):
            return p
    return None


def _imports_in(path: Path) -> list[str]:
    tree = ast.parse(path.read_text("utf-8"))
    seen: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                seen.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                seen.append(node.module)
            elif node.level and node.module:
                pkg = _module_for(path).rsplit(".", node.level)[0]
                seen.append(f"{pkg}.{node.module}" if pkg else node.module)
            elif node.level:
                seen.append(_module_for(path).rsplit(".", node.level)[0])
    return seen


def main() -> int:
    violations: list[str] = []
    prefixes = list(FORBIDDEN.keys())
    for dirpath, _dirs, filenames in os.walk(ROOT):
        for name in filenames:
            if not name.endswith(".py"):
                continue
            p = Path(dirpath) / name
            mod = _module_for(p)
            pkg = _package_for(mod, prefixes)
            if pkg is None:
                continue
            forbid = FORBIDDEN[pkg]
            for imp in _imports_in(p):
                for banned in forbid:
                    if imp == banned or imp.startswith(banned + "."):
                        violations.append(
                            f"{mod} imports {imp} (forbidden: {pkg} may not import {banned})"
                        )

    if violations:
        print("BOUNDARY VIOLATIONS:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1
    print("boundary gate OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
