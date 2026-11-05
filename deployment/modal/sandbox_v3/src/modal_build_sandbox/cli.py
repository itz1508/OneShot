"""Explicit standalone actions; never infer authorization from CLI or candidate data."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .contracts import SandboxExecutionRequest
from .modal_runtime import ModalRuntime
from .recovery import AttemptStore
from .runner import StandaloneRunner, preflight


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Standalone Modal Sandbox v3")
    sub = parser.add_subparsers(dest="cmd", required=True)
    verify = sub.add_parser("validate", help="validate admission-bound bundle and snapshot without Modal")
    verify.add_argument("request", type=Path)
    execute = sub.add_parser("execute", help="execute against a configured Modal App and immutable image")
    execute.add_argument("request", type=Path)
    execute.add_argument("--app", required=True, help="existing Modal App to reuse")
    execute.add_argument("--create-app", action="store_true", help="explicitly allow creating app if absent")
    execute.add_argument("--state", type=Path, default=Path(".state/attempts.sqlite"))
    execute.add_argument("--output", type=Path, default=Path(".outputs"))
    missing = sub.add_parser("unresolved", help="list unreconciled attempt metadata")
    missing.add_argument("--state", type=Path, default=Path(".state/attempts.sqlite"))
    inspect = sub.add_parser("inspect", help="read-only inspect an uncertain Modal attempt")
    inspect.add_argument("operation_id")
    inspect.add_argument("attempt_id")
    inspect.add_argument("--app", required=True)
    inspect.add_argument("--state", type=Path, default=Path(".state/attempts.sqlite"))
    args = parser.parse_args(argv)
    try:
        if args.cmd == "unresolved":
            for record in AttemptStore(args.state).unresolved():
                print(
                    json.dumps(
                        {
                            key: record[key]
                            for key in ("operation_id", "attempt_id", "state", "sandbox_name", "sandbox_id")
                        }
                    )
                )
            return 0
        if args.cmd == "inspect":
            if not (os.environ.get("MODAL_TOKEN_ID") and os.environ.get("MODAL_TOKEN_SECRET")):
                print("BLOCKED: Modal credentials absent", file=sys.stderr)
                return 2
            runner = StandaloneRunner(ModalRuntime(args.app), AttemptStore(args.state), Path(".outputs"))
            print(json.dumps(runner.inspect_attempt(args.operation_id, args.attempt_id), indent=2))
            return 0
        req = SandboxExecutionRequest.model_validate_json(args.request.read_text(encoding="utf-8"))
        if args.cmd == "validate":
            preflight(req)
            print("VALID: offline source, candidate, policy and command-plan checks completed")
            return 0
        if not (os.environ.get("MODAL_TOKEN_ID") and os.environ.get("MODAL_TOKEN_SECRET")):
            print("BLOCKED: Modal credentials absent in this process", file=sys.stderr)
            return 2
        result = StandaloneRunner(
            ModalRuntime(args.app, create_app=args.create_app), AttemptStore(args.state), args.output
        ).execute(req)
        print(result.model_dump_json(indent=2))
        return 0 if result.execution_status == "completed" and result.cleanup_state == "confirmed" else 1
    except Exception as exc:
        print(f"BLOCKED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
