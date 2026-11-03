"""Durable pause/resume boundary independent from provider session state."""

from __future__ import annotations

from agent.contracts.host import Checkpoint
from agent.contracts.interrupts import InterruptRecord, InterruptStatus


def validate_resume(interrupt: InterruptRecord, checkpoint: Checkpoint) -> None:
    """Validate that an interrupt can resume from a checkpoint."""
    if interrupt.status is not InterruptStatus.RESUMED:
        raise ValueError("Interrupt is not resumed")
    if interrupt.checkpoint_id != checkpoint.checkpoint_id:
        raise ValueError("Checkpoint identity mismatch")
    if interrupt.checkpoint_revision != checkpoint.checkpoint_revision:
        raise ValueError("Checkpoint revision mismatch")
    if interrupt.checkpoint_digest != checkpoint.checkpoint_digest:
        raise ValueError("Checkpoint digest mismatch")
