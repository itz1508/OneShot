"""Host-only immutable receipt store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from agent.runtime.canonical_serialization import digest_raw


class ReceiptStoreError(Exception):
    pass


class ReceiptForgeryError(ReceiptStoreError):
    pass


class ReceiptStore:
    """Host-only immutable receipt store.

    Only the host may issue receipts. Receipts are content-addressed
    and verify subject integrity.
    """

    def __init__(self, state_root: str | Path) -> None:
        self.state_root = Path(state_root)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_root / "receipts.db"
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS receipts (
                    receipt_id TEXT PRIMARY KEY,
                    issuer_id TEXT NOT NULL,
                    subject_digest TEXT NOT NULL,
                    receipt_digest TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def issue_verified(
        self,
        receipt_id: str,
        issuer_id: str,
        subject_digest: str,
    ) -> tuple[str, str]:
        """Issue a verified receipt. Returns (receipt_id, receipt_digest).

        Idempotent: if the same receipt_id is issued again with identical
        issuer and subject, returns the existing receipt. Raises
        ReceiptStoreError if the same ID is reused with different content.
        """
        receipt_content = f"{receipt_id}:{issuer_id}:{subject_digest}".encode()
        receipt_digest = digest_raw(receipt_content)
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT issuer_id, subject_digest, receipt_digest FROM receipts WHERE receipt_id = ?",
                (receipt_id,),
            ).fetchone()
            if row is not None:
                existing_issuer, existing_subject, existing_digest = row
                if (
                    existing_issuer == issuer_id
                    and existing_subject == subject_digest
                    and existing_digest == receipt_digest
                ):
                    conn.execute("COMMIT")
                    return receipt_id, receipt_digest
                raise ReceiptStoreError(f"receipt {receipt_id} already exists with different content")
            conn.execute(
                "INSERT INTO receipts (receipt_id, issuer_id, subject_digest, receipt_digest) VALUES (?, ?, ?, ?)",
                (receipt_id, issuer_id, subject_digest, receipt_digest),
            )
            conn.execute("COMMIT")
        except ReceiptStoreError:
            conn.execute("ROLLBACK")
            raise
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return receipt_id, receipt_digest

    def verify(
        self,
        receipt_id: str,
        receipt_digest: str,
        expected_subject: str,
        expected_issuer: str = "host",
    ) -> bool:
        """Verify a receipt against expected subject and issuer.

        Checks receipt_id exists, digest matches, subject matches,
        and issuer matches the expected issuer (default: host).
        A receipt issued by an untrusted agent will fail verification.
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT issuer_id, subject_digest, receipt_digest FROM receipts WHERE receipt_id = ?",
                (receipt_id,),
            ).fetchone()
            if row is None:
                return False
            issuer_id, subject_digest, stored_receipt_digest = row
            if receipt_digest != stored_receipt_digest:
                return False
            if issuer_id != expected_issuer:
                return False
            return bool(subject_digest == expected_subject)
        finally:
            conn.close()

    def get_subject(self, receipt_id: str) -> str | None:
        """Read the immutable subject; callers must independently verify issuer and digest."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT subject_digest FROM receipts WHERE receipt_id = ?",
                (receipt_id,),
            ).fetchone()
            return str(row[0]) if row is not None else None
        finally:
            conn.close()

    def verify_receipt(self, receipt_id: str, receipt_digest: str) -> bool:
        """Verify a receipt exists and digest matches, without subject verification."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT receipt_digest FROM receipts WHERE receipt_id = ?",
                (receipt_id,),
            ).fetchone()
            if row is None:
                return False
            return bool(receipt_digest == row[0])
        finally:
            conn.close()
