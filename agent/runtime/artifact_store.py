"""Content-addressed artifact store with CAS and revision tracking."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pydantic import BaseModel

from agent.runtime.canonical_serialization import (
    SERIALIZER_PROFILE,
    canonical_bytes,
    digest_raw,
)


class ArtifactStoreError(Exception):
    pass


class DuplicateArtifactError(ArtifactStoreError):
    pass


class ArtifactNotFoundError(ArtifactStoreError):
    pass


class StaleRevisionError(ArtifactStoreError):
    """Raised when a CAS write conflicts with an existing revision."""


class ArtifactStore:
    """Content-addressed artifact store backed by SQLite.

    - Immutable: once written, an (artifact_id, revision) cannot change.
    - Content-addressed: each artifact is stored by its SHA-256 digest.
    - Revision-tracked: each artifact_id can have multiple revisions.
    """

    def __init__(self, state_root: str | Path) -> None:
        self.state_root = Path(state_root)
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state_root / "artifacts.db"
        self._init_db()

    def _init_db(self) -> None:
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    digest TEXT NOT NULL,
                    contract_id TEXT NOT NULL,
                    contract_version TEXT NOT NULL,
                    serializer_profile TEXT NOT NULL,
                    content BLOB NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    PRIMARY KEY (artifact_id, revision)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def put_immutable(
        self,
        model: BaseModel,
        artifact_id: str,
        revision: int,
        contract_id: str,
        contract_version: str,
    ) -> str:
        """Store an immutable artifact. Returns the SHA-256 digest.

        Raises DuplicateArtifactError if (artifact_id, revision) exists with different bytes.
        """
        content = canonical_bytes(model)
        digest = digest_raw(content)

        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Check if already exists
            row = conn.execute(
                "SELECT digest FROM artifacts WHERE artifact_id = ? AND revision = ?",
                (artifact_id, revision),
            ).fetchone()
            if row is not None:
                if row[0] != digest:
                    raise DuplicateArtifactError(f"artifact {artifact_id} rev {revision} exists with different digest")
                # Same content, same revision — idempotent
                conn.execute("COMMIT")
                return digest
            conn.execute(
                "INSERT INTO artifacts ("
                "artifact_id, revision, digest, "
                "contract_id, contract_version, serializer_profile, content) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    artifact_id,
                    revision,
                    digest,
                    contract_id,
                    contract_version,
                    SERIALIZER_PROFILE,
                    content,
                ),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return digest

    def get_verified(self, artifact_id: str, revision: int) -> bytes:
        """Retrieve verified artifact bytes by ID and revision."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT content, digest FROM artifacts WHERE artifact_id = ? AND revision = ?",
                (artifact_id, revision),
            ).fetchone()
            if row is None:
                raise ArtifactNotFoundError(f"artifact {artifact_id} rev {revision} not found")
            content, stored_digest = row
            # Verify digest
            actual_digest = digest_raw(content)
            if actual_digest != stored_digest:
                raise ArtifactStoreError(f"digest mismatch for artifact {artifact_id} rev {revision}")
            return bytes(content)
        finally:
            conn.close()

    def get_digest(self, artifact_id: str, revision: int) -> str | None:
        """Get the digest for an artifact without retrieving content."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT digest FROM artifacts WHERE artifact_id = ? AND revision = ?",
                (artifact_id, revision),
            ).fetchone()
            if row is None:
                return None
            return str(row[0])
        finally:
            conn.close()

    def latest_revision(self, artifact_id: str) -> int:
        """Get the latest revision number for an artifact."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT MAX(revision) FROM artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
            return int(row[0] or 0)
        finally:
            conn.close()

    def put_cas(
        self,
        model: BaseModel,
        artifact_id: str,
        expected_revision: int,
        contract_id: str,
        contract_version: str,
    ) -> tuple[int, str]:
        """Atomic compare-and-swap write.

        Writes at revision = expected_revision + 1. Raises
        StaleRevisionError if another writer has already committed
        at expected_revision or beyond.

        Returns (new_revision, digest).
        """
        content = canonical_bytes(model)
        digest = digest_raw(content)
        new_rev = expected_revision + 1

        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT MAX(revision) FROM artifacts WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()
            current_rev = row[0] or 0
            if current_rev != expected_revision:
                raise StaleRevisionError(
                    f"CAS failed for {artifact_id}: expected rev {expected_revision}, found {current_rev}"
                )
            conn.execute(
                "INSERT INTO artifacts ("
                "artifact_id, revision, digest, "
                "contract_id, contract_version, serializer_profile, content) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    artifact_id,
                    new_rev,
                    digest,
                    contract_id,
                    contract_version,
                    SERIALIZER_PROFILE,
                    content,
                ),
            )
            conn.execute("COMMIT")
        except StaleRevisionError:
            conn.execute("ROLLBACK")
            raise
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return new_rev, digest

    def exists(self, artifact_id: str, revision: int) -> bool:
        """Check if an artifact exists at the given revision."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute(
                "SELECT 1 FROM artifacts WHERE artifact_id = ? AND revision = ?",
                (artifact_id, revision),
            ).fetchone()
            return row is not None
        finally:
            conn.close()
