"""rsm CLI — thin client against the daemon HTTP transport."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import urllib.request
import urllib.error


def _request(method: str, url: str, body: Any | None = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8"))
        except Exception:
            payload = {"code": "HTTP_ERROR", "message": str(e)}
        print(json.dumps(payload), file=sys.stderr)
        raise SystemExit(2)


def _daemon_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rsm")
    parser.add_argument("--daemon", default="http://127.0.0.1:8787")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest")
    pi.add_argument("--kind", default="text", choices=["text", "pasted", "stdin"])
    pi.add_argument("--source-uri", default=None)
    pi.add_argument("file", nargs="?", help="Path to file; '-' or omit reads stdin")

    pr = sub.add_parser("read")
    pr.add_argument("bucket_id")

    pt = sub.add_parser("transition")
    pt.add_argument("bucket_id")
    pt.add_argument("to")

    args = parser.parse_args(argv)

    if args.cmd == "ingest":
        if args.file in (None, "-"):
            content = sys.stdin.read()
        else:
            with open(args.file, "r", encoding="utf-8") as f:
                content = f.read()
        out = _request(
            "POST",
            f"{args.daemon}/v1/buckets/",
            {"content": content, "source_uri": args.source_uri, "kind": args.kind},
        )
        print(json.dumps(out, indent=2))
        return 0
    if args.cmd == "read":
        out = _request("GET", f"{args.daemon}/v1/buckets/{args.bucket_id}")
        print(json.dumps(out, indent=2))
        return 0
    if args.cmd == "transition":
        out = _request(
            "POST",
            f"{args.daemon}/v1/buckets/{args.bucket_id}/transition",
            {"to": args.to},
        )
        print(json.dumps(out, indent=2))
        return 0
    return 1


from .local import main as _local_main

def main(argv: list[str] | None = None) -> int:
    """Dispatch to the local or daemon CLI.

    The *-local subcommands do not require a running daemon; all other
    subcommands continue to speak HTTP to the daemon.
    """
    import sys as _sys
    args = list(argv) if argv is not None else list(_sys.argv[1:])
    local_cmds = {"ingest-local", "replay-local", "transition-local", "events-local"}
    for tok in args:
        if tok in local_cmds:
            return _local_main(args)
    return _daemon_main(args)

if __name__ == "__main__":
    raise SystemExit(main())
