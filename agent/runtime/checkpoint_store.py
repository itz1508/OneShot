"""CAS-based checkpoint store with operation ledger."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from agent.contracts.host import Checkpoint
from agent.runtime.canonical_serialization import digest_raw


class CheckpointStoreError(Exception):
    pass


class CompetingWriterError(CheckpointStoreError):
    pass


class StaleCheckpointError(CheckpointStoreError):
    """Raised when a checkpoint write conflicts with an existing revision."""


class InMemoryCheckpointStore:
    """In-memory checkpoint store with CAS semantics for testing."""

    def __init__(self) -> None:
        self._store: dict[str, Checkpoint] = {}

    def compare_and_swap(self, checkpoint: Checkpoint) -> None:
        """Write a checkpoint with CAS revision check."""
        cid = checkpoint.checkpoint_id
        expected = checkpoint.expected_previous_revision
        revision = checkpoint.checkpoint_revision
        existing = self._store.get(cid)
        current = 0 if existing is None else existing.checkpoint_revision
        if expected != current:
            raise StaleCheckpointError(f"Expected {expected}, found {current}")
        if revision != current + 1:
            raise StaleCheckpointError("Revision must increase by one")
        self._store[cid] = checkpoint

    def get(self, checkpoint_id: str) -> Checkpoint | None:
        return self._store.get(checkpoint_id)


class CheckpointStore:
    """CAS-based checkpoint store for task state and recovery.

    Each checkpoint has a revision number. Writers must provide the
    expected previous revision (compare-and-swap). Competing writers
    are rejected.
    """

    def __init__(self, state_root: str | Path) -> None:
        self.state_root = Path(state_root)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_root / "checkpoints.db"
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS checkpoints (
                    task_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    state_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (task_id, revision)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS operation_ledger (
                    op_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    checkpoint_revision INTEGER NOT NULL,
                    operation_type TEXT NOT NULL,
                    operation_data TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def checkpoint_cas(
        self,
        task_id: str,
        expected_prev_revision: int,
        state: dict[str, Any],
    ) -> tuple[int, str]:
        """Checkpoint with compare-and-swap. Returns (new_revision, digest).

        Raises CompetingWriterError if expected_prev_revision doesn't match.
        """
        state_json = json.dumps(state, sort_keys=True, separators=(",", ":"))
        state_digest = digest_raw(state_json.encode("utf-8"))

        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT MAX(revision) FROM checkpoints WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            current_rev = row[0] or 0
            if current_rev != expected_prev_revision:
                raise CompetingWriterError(f"CAS failed: expected rev {expected_prev_revision}, found {current_rev}")
            new_rev = current_rev + 1
            conn.execute(
                "INSERT INTO checkpoints (task_id, revision, state_json, state_digest) VALUES (?, ?, ?, ?)",
                (task_id, new_rev, state_json, state_digest),
            )
            conn.execute("COMMIT")
            return new_rev, state_digest
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def load_checkpoint(self, task_id: str) -> tuple[int, dict[str, Any], str] | None:
        """Load the latest checkpoint for a task.

        Returns (revision, state, digest) or None if no checkpoint exists.
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT revision, state_json, state_digest FROM checkpoints "
                "WHERE task_id = ? ORDER BY revision DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            if row is None:
                return None
            return row[0], json.loads(row[1]), row[2]
        finally:
            conn.close()

    def record_operation(
        self,
        task_id: str,
        checkpoint_revision: int,
        operation_type: str,
        operation_data: str,
    ) -> int:
        """Record an operation in the ledger."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.execute(
                "INSERT INTO operation_ledger (task_id, checkpoint_revision, operation_type, operation_data) "
                "VALUES (?, ?, ?, ?)",
                (task_id, checkpoint_revision, operation_type, operation_data),
            )
            conn.commit()
            return cursor.lastrowid or 0
        finally:
            conn.close()

    def update_operation_status(self, op_id: int, status: str) -> None:
        """Update an operation's status."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                "UPDATE operation_ledger SET status = ? WHERE op_id = ?",
                (status, op_id),
            )
            conn.commit()
        finally:
            conn.close()
