"""Standalone read-only Audit capability CLI: python -m agent.audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent.audit.core import scan


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only OneShot capability audit (static observations only)")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Authorized repository root")
    parser.add_argument("--scope", default=".", help="Relative in-repository directory")
    parser.add_argument("--request", default="", help="User audit question, preserved without granting access")
    parser.add_argument(
        "--capability",
        action="append",
        choices=(
            "paths",
            "wiring",
            "security",
            "contracts",
            "completeness",
            "verification",
            "frontend",
            "state",
            "dependencies",
            "integration",
            "recovery",
        ),
        default=[],
    )
    args = parser.parse_args()
    try:
        result = scan(args.root, args.scope, tuple(args.capability), request=args.request)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result.to_dict(), sort_keys=True, indent=2))
    return 2 if result.disposition == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
