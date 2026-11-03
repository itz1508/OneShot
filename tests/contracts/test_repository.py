"""Test RepositoryIdentityV2 with Git object format validation."""

import pytest
from pydantic import ValidationError

from agent.contracts.repository import GitObjectFormat, RepositoryIdentityV2, WorktreeState


def test_git_object_formats():
    RepositoryIdentityV2(
        repository_id="r",
        object_format=GitObjectFormat.SHA1,
        commit_oid="a" * 40,
        worktree_state=WorktreeState.CLEAN,
        normalization_policy_id="p",
        ignored_policy_id="i",
    )
    RepositoryIdentityV2(
        repository_id="r",
        object_format=GitObjectFormat.SHA256,
        commit_oid="a" * 64,
        worktree_state=WorktreeState.CLEAN,
        normalization_policy_id="p",
        ignored_policy_id="i",
    )
    with pytest.raises(ValidationError):
        RepositoryIdentityV2(
            repository_id="r",
            object_format=GitObjectFormat.SHA256,
            commit_oid="a" * 40,
            worktree_state=WorktreeState.CLEAN,
            normalization_policy_id="p",
            ignored_policy_id="i",
        )


def test_modified_worktree_requires_manifest():
    with pytest.raises(ValidationError):
        RepositoryIdentityV2(
            repository_id="r",
            object_format=GitObjectFormat.SHA1,
            commit_oid="a" * 40,
            worktree_state=WorktreeState.MODIFIED,
            normalization_policy_id="p",
            ignored_policy_id="i",
        )
