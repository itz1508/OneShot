"""Build temporary model context from authoritative artifacts and checkpoints."""

from __future__ import annotations

from agent.contracts.common import ArtifactRef
from agent.contracts.host import Checkpoint


def project_context(
    checkpoint: Checkpoint,
    upstream_artifacts: tuple[ArtifactRef, ...] = (),
) -> dict[str, str]:
    """Project a temporary context dict from a checkpoint and its upstream artifacts.

    The returned dict maps artifact_id to artifact_digest so the model can
    reference upstream artifacts without holding them in its context window.
    """
    context: dict[str, str] = {}
    for ref in upstream_artifacts:
        context[ref.artifact_id] = ref.artifact_digest
    context["_checkpoint_id"] = checkpoint.checkpoint_id
    context["_checkpoint_revision"] = str(checkpoint.checkpoint_revision)
    return context
