"""Crash-recoverable JSONL projections from one authoritative SQLite journal ledger.

Only the host selects roots and appends events. Model-supplied paths are never
accepted. Successful append is committed to SQLite before its projection.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

from agent.contracts.host import ReceiptRef
from agent.contracts.stage_log import StageLogEvent, StageName
from agent.runtime.receipt_store import ReceiptStore

STAGES: tuple[StageName, ...] = ("search", "audit", "plan", "build", "mem")


class StageJournalError(ValueError):
    pass


class StageJournalService:
    def __init__(self, runtime_root: str | Path, event_db_path: str | Path) -> None:
        Path(runtime_root).mkdir(parents=True, exist_ok=True)
        self._root = Path(runtime_root).resolve(strict=True)
        self._db_path = Path(event_db_path)
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS stage_log_events (
                event_id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL,
                task_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                stage TEXT NOT NULL,
                payload TEXT NOT NULL,
                UNIQUE(workspace_id, task_id, run_id, sequence)
            )""")
            conn.execute("""CREATE INDEX IF NOT EXISTS idx_stage_run
                ON stage_log_events(workspace_id, task_id, run_id, sequence)""")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path), timeout=30.0)

    @staticmethod
    def _validate_identity(value: str) -> str:
        import re

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
            raise StageJournalError("invalid workspace/task/run identity")
        return value

    def _run_dir(self, workspace_id: str, task_id: str, run_id: str) -> Path:
        ids = (workspace_id, task_id, run_id)
        root = self._root
        for item in ids:
            root = root / self._validate_identity(item)
            if root.is_symlink():
                raise StageJournalError("symlinked run directory is forbidden")
            if root.exists() and not root.is_dir():
                raise StageJournalError("run path is not a directory")
            root.mkdir(exist_ok=True)
        if not root.resolve().is_relative_to(self._root):
            raise StageJournalError("run escaped runtime root")
        return root

    def append(self, event: StageLogEvent) -> StageLogEvent:
        """Append an ordinary stage event; memory promotion is a separate host gate."""
        if event.stage == "mem":
            raise StageJournalError("mem.log requires verified host memory promotion")
        return self._append_authoritative(event)

    def append_verified_memory(
        self,
        event: StageLogEvent,
        *,
        receipts: ReceiptStore,
        verification_receipt_ref: ReceiptRef,
        verification_subject: str,
        approval_receipt_ref: ReceiptRef,
        approval_subject: str,
    ) -> StageLogEvent:
        """Host-only memory append, bound to trusted verification and approval."""
        if event.stage != "mem" or event.status != "verified":
            raise StageJournalError("memory events must be verified")
        if verification_receipt_ref.issuer_id != "host" or approval_receipt_ref.issuer_id != "host":
            raise StageJournalError("untrusted memory receipt issuer")
        if not receipts.verify(
            verification_receipt_ref.receipt_id,
            verification_receipt_ref.receipt_digest,
            verification_subject,
        ):
            raise StageJournalError("invalid Build verification receipt")
        if not receipts.verify(
            approval_receipt_ref.receipt_id,
            approval_receipt_ref.receipt_digest,
            approval_subject,
        ):
            raise StageJournalError("reusable-memory approval required")
        return self._append_authoritative(event)

    def _append_authoritative(self, event: StageLogEvent) -> StageLogEvent:
        """Assign run sequence transactionally; never use JSONL as authoritative state."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            previous = conn.execute(
                "SELECT payload FROM stage_log_events WHERE event_id = ?", (event.event_id,)
            ).fetchone()
            if previous is not None:
                saved = StageLogEvent.model_validate_json(previous[0])
                comparable = event.model_copy(update={"sequence": saved.sequence})
                if comparable.model_copy(update={"created_at": saved.created_at}) != saved:
                    raise StageJournalError("conflicting duplicate event_id")
                persisted = saved
            else:
                seq = conn.execute(
                    """SELECT COALESCE(MAX(sequence),0)+1 FROM stage_log_events
                       WHERE workspace_id=? AND task_id=? AND run_id=?""",
                    (event.workspace_id, event.task_id, event.run_id),
                ).fetchone()[0]
                persisted = event.model_copy(update={"sequence": seq})
                conn.execute(
                    """INSERT INTO stage_log_events
                    (event_id, workspace_id, task_id, run_id, sequence, stage, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        persisted.event_id,
                        persisted.workspace_id,
                        persisted.task_id,
                        persisted.run_id,
                        seq,
                        persisted.stage,
                        persisted.model_dump_json(),
                    ),
                )
        self.rebuild(persisted.workspace_id, persisted.task_id, persisted.run_id)
        return persisted

    def load(
        self,
        *,
        workspace_id: str,
        task_id: str,
        run_id: str,
        stage: StageName,
        after_sequence: int = 0,
    ) -> tuple[StageLogEvent, ...]:
        if stage not in STAGES or after_sequence < 0:
            raise StageJournalError("invalid stage or sequence")
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT payload FROM stage_log_events WHERE workspace_id=?
                AND task_id=? AND run_id=? AND stage=? AND sequence>?
                ORDER BY sequence""",
                (workspace_id, task_id, run_id, stage, after_sequence),
            ).fetchall()
        return tuple(StageLogEvent.model_validate_json(row[0]) for row in rows)

    def rebuild(self, workspace_id: str, task_id: str, run_id: str) -> None:
        """Reconstruct projections while holding the SQLite writer lock.

        A writer cannot publish an older snapshot after a newer writer's
        projection. SQLite remains the authoritative recovery source.
        """
        folder = self._run_dir(workspace_id, task_id, run_id)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for stage in STAGES:
                rows = conn.execute(
                    """SELECT payload FROM stage_log_events WHERE workspace_id=?
                    AND task_id=? AND run_id=? AND stage=? ORDER BY sequence""",
                    (workspace_id, task_id, run_id, stage),
                ).fetchall()
                target = folder / f"{stage}.log"
                if target.is_symlink():
                    raise StageJournalError("journal destination cannot be a symlink")
                fd, temporary = tempfile.mkstemp(prefix=".journal-", dir=folder)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as stream:
                        for (payload,) in rows:
                            stream.write(payload + "\n")
                        stream.flush()
                        os.fsync(stream.fileno())
                    if target.is_symlink():
                        raise StageJournalError("journal destination cannot be a symlink")
                    os.replace(temporary, target)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
