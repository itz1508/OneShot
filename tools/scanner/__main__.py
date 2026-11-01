"""JSON-stdin CLI for Scanner operations.

python -m tools.scanner match|change|write|filesystems --repo-root PATH [--apply]
"""

from __future__ import annotations

import argparse
import json
import sys

from . import ScanError, scan_edit_change, scan_edit_write, scan_filesystems, scan_match_variable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OneShot Scanner operations")
    parser.add_argument("operation", choices=["match", "change", "write", "filesystems"])
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--apply", action="store_true", help="explicitly authorize effectful write")
    args = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ScanError("JSON payload must be an object")
        if args.operation == "match":
            result = scan_match_variable(
                args.repo_root, payload["rules"], paths=payload.get("paths"),
                include_untracked=payload.get("include_untracked", False),
            )
        elif args.operation == "change":
            result = scan_edit_change(
                args.repo_root, payload["rules"], paths=payload.get("paths"),
                include_untracked=payload.get("include_untracked", False),
            )
        elif args.operation == "write":
            result = scan_edit_write(
                args.repo_root, payload["changes"],
                allowed_paths=payload.get("allowed_paths", []), authorized=args.apply,
            )
        else:
            result = scan_filesystems(
                args.repo_root, include_untracked=payload.get("include_untracked", False),
            )
        print(json.dumps({"ok": True, "result": result}, sort_keys=True))
        return 0
    except (ScanError, KeyError, ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
