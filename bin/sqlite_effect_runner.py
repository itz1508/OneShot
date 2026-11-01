#!/usr/bin/env python3
"""Pre-effect-durable effect runner used by Scenario S5.

Deterministic 3-stage flow:

  intent → effect → receipt

Each stage reads and writes a single SQLite database (the independent effect
observer). The database schema:

    actions(action_id TEXT PRIMARY KEY,
            state TEXT NOT NULL,          -- 'pending' | 'applied' | 'reconciled'
            applied_count INTEGER NOT NULL DEFAULT 0,
            payload TEXT,
            applied_at TEXT,
            reconciled_at TEXT)

Modes (via env):

  CHECKPOINT_KILL_AT=pre_effect     — exit abruptly between intent and effect
  CHECKPOINT_KILL_AT=post_effect    — exit abruptly between effect and receipt
                                      (effect already applied → restart must
                                      detect and not reapply)
  CHECKPOINT_RECONCILE=1            — restart path: read pending/applied, run
                                      only if 'applied' is absent

Exit codes:
    0 — effect applied exactly once (ok)
    2 — intent persistence failed
    3 — reconcile detected unknown state
    137/9 — killed by SIGKILL (OS)
"""

from __future__ import annotations

import datetime as _dt
import os
import sqlite3
import sys
from pathlib import Path


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), isolation_level=None, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS actions (
            action_id TEXT PRIMARY KEY,
            state TEXT NOT NULL,
            applied_count INTEGER NOT NULL DEFAULT 0,
            payload TEXT,
            applied_at TEXT,
            reconciled_at TEXT
        )
        """
    )
    return conn


def _record_intent(conn: sqlite3.Connection, action_id: str, payload: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO actions (action_id, state, payload) VALUES (?, 'pending', ?)",
        (action_id, payload),
    )


def _apply_effect(conn: sqlite3.Connection, action_id: str) -> None:
    # Idempotent at the DB layer: a resumed worker that already applied the
    # effect must not reapply it. Enforce via UPDATE guarded by current state.
    cur = conn.execute(
        """
        UPDATE actions
        SET state='applied', applied_count=applied_count+1, applied_at=?
        WHERE action_id=? AND state='pending'
        """,
        (_utc_now(), action_id),
    )
    if cur.rowcount != 1:
        # Not pending — either already applied, or missing entirely.
        row = conn.execute(
            "SELECT state, applied_count FROM actions WHERE action_id=?", (action_id,)
        ).fetchone()
        if row is None:
            raise RuntimeError(f"intent for {action_id!r} missing at effect")
        if row[0] == "applied":
            # Already done; this is the honest recovery case.
            return
        raise RuntimeError(f"unexpected state {row[0]!r} at effect")


def _write_receipt(conn: sqlite3.Connection, action_id: str) -> None:
    conn.execute(
        "UPDATE actions SET state='reconciled', reconciled_at=? WHERE action_id=?",
        (_utc_now(), action_id),
    )


def _detect_restart_state(conn: sqlite3.Connection, action_id: str) -> str:
    row = conn.execute("SELECT state FROM actions WHERE action_id=?", (action_id,)).fetchone()
    if row is None:
        return "none"
    return row[0]


def main() -> int:
    db = Path(os.environ["SQLITE_OBSERVER_DB"])
    action_id = os.environ["ACTION_ID"]
    payload = os.environ.get("ACTION_PAYLOAD", "")
    kill_at = os.environ.get("CHECKPOINT_KILL_AT", "")
    reconcile = os.environ.get("CHECKPOINT_RECONCILE", "")

    conn = _conn(db)
    try:
        if reconcile:
            state = _detect_restart_state(conn, action_id)
            if state == "none":
                # Intent missing — honest refusal.
                print("reconcile: no intent found", file=sys.stderr)
                return 3
            if state == "applied":
                # Receipt stage was never reached.
                _write_receipt(conn, action_id)
                return 0
            if state == "reconciled":
                # Already done end-to-end — nothing to do.
                return 0
            if state == "pending":
                # Intent exists; effect not applied. Apply exactly once.
                _apply_effect(conn, action_id)
                _write_receipt(conn, action_id)
                return 0
            print(f"reconcile: unexpected state {state!r}", file=sys.stderr)
            return 3

        # Normal run (not a restart).
        _record_intent(conn, action_id, payload)

        if kill_at == "pre_effect":
            # Exit abruptly BEFORE touching the external effect.
            # Must not go through atexit — simulate hard crash via os._exit.
            os._exit(137)

        _apply_effect(conn, action_id)

        if kill_at == "post_effect":
            # Effect applied but receipt not written. Restart must detect.
            os._exit(137)

        _write_receipt(conn, action_id)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
