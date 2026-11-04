"""Host-owned immutable tool snapshot binding and executable preflight."""

from __future__ import annotations

import hashlib
from pathlib import Path

from agent.contracts.common import ArtifactRef
from agent.contracts.tool_registry import (
    ResolvedCommand,
    ToolRegistrySnapshot,
)
from agent.runtime.artifact_store import ArtifactStore
from agent.runtime.canonical_serialization import SERIALIZER_PROFILE, canonical_bytes, digest_raw


class ToolRegistryError(ValueError):
    pass


def pin_tool_registry(
    store: ArtifactStore,
    snapshot: ToolRegistrySnapshot,
    artifact_id: str,
    revision: int = 1,
) -> ArtifactRef:
    """Persist the trusted host catalog as content-addressed, immutable bytes."""
    digest = store.put_immutable(snapshot, artifact_id, revision, "tool_registry", "1.0")
    return ArtifactRef(
        artifact_id=artifact_id,
        artifact_revision=revision,
        artifact_digest=digest,
        contract_id="tool_registry",
        contract_version="1.0",
        serializer_profile=SERIALIZER_PROFILE,
    )


def load_pinned_tool_registry(store: ArtifactStore, ref: ArtifactRef) -> ToolRegistrySnapshot:
    """Fail closed for wrong identity, stale versions, or mismatched content."""
    if ref.contract_id != "tool_registry" or ref.contract_version != "1.0":
        raise ToolRegistryError("invalid tool registry contract identity")
    content = store.get_verified(ref.artifact_id, ref.artifact_revision)
    if digest_raw(content) != ref.artifact_digest:
        raise ToolRegistryError("tool registry artifact digest mismatch")
    snapshot = ToolRegistrySnapshot.model_validate_json(content)
    if canonical_bytes(snapshot) != content:
        raise ToolRegistryError("tool registry artifact not canonical")
    return snapshot


def verify_executable(command: ResolvedCommand, executable: str | Path) -> str:
    """Verify the sandbox-selected executable bytes before launching argv."""
    path = Path(executable)
    if not path.is_file() or path.is_symlink():
        raise ToolRegistryError("untrusted executable")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != command.executable_digest:
        raise ToolRegistryError("executable digest mismatch")
    return digest
