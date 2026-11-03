"""Repository identity contracts -- Git-aware source state tracking."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from agent.contracts.common import ContractModel, Sha256


class GitObjectFormat(StrEnum):
    """Git object hash format."""

    SHA1 = "sha1"
    SHA256 = "sha256"


class WorktreeState(StrEnum):
    """Working tree cleanliness state."""

    CLEAN = "clean"
    MODIFIED = "modified"


class WorktreeEntry(ContractModel):
    """Per-file entry in a repository identity snapshot."""

    relative_path: str = Field(min_length=1)
    entry_type: Literal["file", "directory", "symlink"] = "file"
    staged: bool = False
    unstaged: bool = False
    authorized_untracked: bool = False
    content_digest: Sha256 | None = None
    symlink_target: str | None = None


class RepositoryIdentityV2(ContractModel):
    """Git-aware repository identity with object format and worktree state."""

    identity_version: str = "2.0"
    repository_id: str = Field(min_length=1)
    object_format: GitObjectFormat = GitObjectFormat.SHA1
    commit_oid: str = Field(min_length=1)
    worktree_state: WorktreeState = WorktreeState.CLEAN
    entries: tuple[WorktreeEntry, ...] = ()
    source_manifest_digest: Sha256 | None = None
    normalization_policy_id: str = Field(min_length=1)
    ignored_policy_id: str = Field(min_length=1)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    receipt_ref: str | None = None

    @model_validator(mode="after")
    def validate_oid_length(self) -> RepositoryIdentityV2:
        if self.object_format is GitObjectFormat.SHA1 and len(self.commit_oid) != 40:
            raise ValueError("SHA-1 OID must be 40 hex characters")
        if self.object_format is GitObjectFormat.SHA256 and len(self.commit_oid) != 64:
            raise ValueError("SHA-256 OID must be 64 hex characters")
        if self.worktree_state is WorktreeState.MODIFIED and not self.source_manifest_digest:
            raise ValueError("modified worktree requires source manifest digest")
        return self
