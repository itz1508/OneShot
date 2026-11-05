"""Durable pre-effect attempt intents, CAS transitions and reconciliation handles."""

from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


class AttemptStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise ValueError("attempt store cannot be a symlink")
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS attempts (
                operation_id TEXT NOT NULL, attempt_id TEXT NOT NULL,
                state TEXT NOT NULL, version INTEGER NOT NULL,
                sandbox_name TEXT NOT NULL, sandbox_id TEXT,
                detail TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
                PRIMARY KEY(operation_id, attempt_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS transitions (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                operation_id TEXT NOT NULL, attempt_id TEXT NOT NULL,
                state TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL)""")
        os.chmod(self.path, 0o600)

    def start(self, operation_id: str, attempt_id: str, sandbox_name: str) -> dict[str, object]:
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.path, timeout=10) as db:
            try:
                db.execute(
                    (
                        "INSERT INTO attempts(operation_id,attempt_id,state,version,sandbox_name,updated_at) "
                        "VALUES(?,?,?,?,?,?)"
                    ),
                    (operation_id, attempt_id, "INTENT_RECORDED", 1, sandbox_name, now),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("duplicate or unreconciled attempt cannot be restarted") from exc
            db.execute(
                "INSERT INTO transitions(operation_id,attempt_id,state,detail,created_at) VALUES(?,?,?,?,?)",
                (operation_id, attempt_id, "INTENT_RECORDED", "", now),
            )
        return self.get(operation_id, attempt_id)

    def get(self, operation_id: str, attempt_id: str) -> dict[str, object]:
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            found = db.execute(
                "SELECT * FROM attempts WHERE operation_id=? AND attempt_id=?", (operation_id, attempt_id)
            ).fetchone()
        if found is None:
            raise KeyError("unknown attempt")
        return dict(found)

    def transition(
        self, operation_id: str, attempt_id: str, old: str, new: str, *, detail: str = "", sandbox_id: str | None = None
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            n = db.execute(
                (
                    "UPDATE attempts SET state=?,version=version+1,sandbox_id=COALESCE(?,sandbox_id),"
                    "detail=?,updated_at=? WHERE operation_id=? AND attempt_id=? AND state=?"
                ),
                (new, sandbox_id, detail[:300], now, operation_id, attempt_id, old),
            ).rowcount
            if n != 1:
                raise ValueError("stale or invalid attempt transition")
            db.execute(
                "INSERT INTO transitions(operation_id,attempt_id,state,detail,created_at) VALUES(?,?,?,?,?)",
                (operation_id, attempt_id, new, detail[:300], now),
            )

    def transitions(self, operation_id: str, attempt_id: str) -> list[dict[str, object]]:
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM transitions WHERE operation_id=? AND attempt_id=? ORDER BY sequence",
                    (operation_id, attempt_id),
                )
            ]

    def unresolved(self) -> list[dict[str, object]]:
        with sqlite3.connect(self.path) as db:
            db.row_factory = sqlite3.Row
            return [
                dict(r)
                for r in db.execute(
                    "SELECT * FROM attempts WHERE state NOT IN ('TERMINATION_RECORDED','BLOCKED_PRE_EFFECT') "
                    "ORDER BY updated_at"
                )
            ]
