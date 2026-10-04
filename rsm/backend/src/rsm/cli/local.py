"""Phase 16 — Local-mode CLI subcommands (no daemon required).

Backed directly by :class:`rsm.daemon.service.DaemonService` with a
:class:`rsm.daemon.store.FsStore` on a chosen ``--store-root`` and a
:class:`rsm.daemon.eventlog.EventLog` on a chosen ``--eventlog-path``.

Subcommands:

* ``rsm ingest-local <path> [--kind=auto|text|markdown|pdf|opaque|folder|zip]``
* ``rsm replay-local <bucket_id>``
* ``rsm transition-local <bucket_id> <to>``
* ``rsm events-local <bucket_id>``

Each prints JSON on stdout. Failure exit code 2 with the error JSON on stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ..daemon.eventlog import EventLog
from ..daemon.service import DaemonService
from ..daemon.store import FsStore
from ..loading.runtime_dirs import (
    DEFAULT_ATTACHMENT_DIR,
    DEFAULT_STORE_DIR,
    ensure_runtime_dirs,
)


def _build_service(store_root: str, eventlog_path: str) -> DaemonService:
    store = FsStore(store_root)
    eventlog = EventLog(eventlog_path)
    return DaemonService(store=store, eventlog=eventlog)


def _emit(obj: Any) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True, default=str))


def _fail(code: str, message: str, **details: Any) -> int:
    print(json.dumps({"code": code, "message": message, "details": details}), file=sys.stderr)
    return 2


def _guess_kind(p: Path) -> str:
    if p.is_dir():
        return "folder"
    s = p.suffix.lower()
    if s in (".md", ".markdown"):
        return "markdown"
    if s == ".pdf":
        return "pdf"
    if s == ".zip":
        return "zip"
    if s in (".txt", ".log"):
        return "text"
    return "opaque"


def _ingest(args: argparse.Namespace) -> int:
    svc = _build_service(args.store_root, args.eventlog_path)
    try:
        ensure_runtime_dirs(attachment_dir=args.attachment_root, store_dir=args.store_root)
    except Exception as e:
        return _fail("RUNTIME_DIR", str(e))
    p = Path(args.file).expanduser()
    kind = args.kind if args.kind != "auto" else _guess_kind(p)
    try:
        if kind == "text":
            bucket = svc.ingest_text(p.read_text(encoding="utf-8"),
                                     source_uri=str(p.resolve()),
                                     expected_hash=args.supplied_sha256)
        elif kind == "markdown":
            bucket = svc.ingest_markdown(p.read_text(encoding="utf-8"),
                                         source_uri=str(p.resolve()),
                                         expected_hash=args.supplied_sha256)
        elif kind == "pdf":
            bucket = svc.ingest_pdf(p.read_bytes(),
                                     source_uri=str(p.resolve()),
                                     expected_hash=args.supplied_sha256)
        elif kind == "opaque":
            bucket = svc.ingest_opaque(p.read_bytes(),
                                        source_uri=str(p.resolve()),
                                        filename=p.name,
                                        expected_hash=args.supplied_sha256)
        elif kind == "folder":
            parent, children = svc.ingest_folder(str(p),
                                                 expected_hash=args.supplied_sha256)
            _emit({"parent_bucket_id": parent.bucket_id,
                   "children": [c.bucket_id for c in children],
                   "integrity_status": parent.integrity_status})
            return 0
        elif kind == "zip":
            parent, children = svc.ingest_zip(str(p),
                                              expected_hash=args.supplied_sha256)
            _emit({"parent_bucket_id": parent.bucket_id,
                   "children": [c.bucket_id for c in children],
                   "integrity_status": parent.integrity_status})
            return 0
        else:
            return _fail("UNSUPPORTED_KIND", f"kind={kind!r}")
    except Exception as e:
        return _fail("INGEST_FAILED", str(e), kind=kind, file=str(p))
    _emit({"bucket_id": bucket.bucket_id,
           "hash": bucket.hash.value,
           "integrity_status": bucket.integrity_status,
           "state": bucket.state})
    return 0


def _replay(args: argparse.Namespace) -> int:
    svc = _build_service(args.store_root, args.eventlog_path)
    from ..replay.envelope import build_replay_envelope
    bucket = svc.store.read(args.bucket_id)
    if bucket is None:
        return _fail("NOT_FOUND", f"No bucket {args.bucket_id!r}")
    from ..classification.model import DEFAULT_CLASSIFICATION
    classification = svc._classification.get(bucket.bucket_id, DEFAULT_CLASSIFICATION)
    envelope = build_replay_envelope(bucket, classification=classification)
    _emit(envelope)
    return 0


def _transition(args: argparse.Namespace) -> int:
    svc = _build_service(args.store_root, args.eventlog_path)
    try:
        bucket = svc.transition(args.bucket_id, args.to)
    except Exception as e:
        return _fail("TRANSITION_FAILED", str(e))
    _emit({"bucket_id": bucket.bucket_id, "state": bucket.state})
    return 0


def _events(args: argparse.Namespace) -> int:
    svc = _build_service(args.store_root, args.eventlog_path)
    _emit({"events": svc.eventlog.read(args.bucket_id)})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rsm")
    parser.add_argument("--store-root", default=DEFAULT_STORE_DIR,
                        help="Local store root (default ./store)")
    parser.add_argument("--attachment-root", default=DEFAULT_ATTACHMENT_DIR,
                        help="Local attachment root (default ./attachment)")
    parser.add_argument("--eventlog-path",
                        default="./store/events.log",
                        help="Lifecycle event log path (default ./store/events.log)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest-local", help="Ingest a local file / folder / zip into ./store")
    pi.add_argument("file", help="Path to file or folder")
    pi.add_argument("--kind", default="auto",
                    choices=["auto", "text", "markdown", "pdf", "opaque", "folder", "zip"])
    pi.add_argument("--supplied-sha256", default=None,
                    help="Optional caller-supplied SHA-256 for integrity verification")
    pi.set_defaults(fn=_ingest)

    pr = sub.add_parser("replay-local", help="Replay a stored Bucket")
    pr.add_argument("bucket_id")
    pr.set_defaults(fn=_replay)

    pt = sub.add_parser("transition-local", help="Trigger a lifecycle transition")
    pt.add_argument("bucket_id")
    pt.add_argument("to")
    pt.set_defaults(fn=_transition)

    pe = sub.add_parser("events-local", help="Read the lifecycle event log for a Bucket")
    pe.add_argument("bucket_id")
    pe.set_defaults(fn=_events)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
