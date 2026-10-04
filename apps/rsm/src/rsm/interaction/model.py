"""Pydantic model for an `InteractionRecord` (ADR 0009)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class InteractionRecord(BaseModel):
    """Per-interaction authorization + Bucket selection.

    Fields:
      - interaction_id: opaque string provided by the consuming runtime.
      - rsm_enabled: fail-closed default (False). Toggling to True authorises
        RSM delivery into this interaction.
      - selected_bucket_id: at most one Bucket per interaction in V3.
        Multi-Bucket aggregation is deferred to V3.x (ADR 0015).
      - last_streamed_at: UX hint only. Never used as an authorization or
        correctness signal.

    This record is NEVER part of the Bucket's A1 identity and does NOT alter
    `Bucket.hash`.
    """

    model_config = ConfigDict(extra="forbid")

    interaction_id: str = Field(..., min_length=1)
    rsm_enabled: bool = False
    selected_bucket_id: Optional[str] = None
    last_streamed_at: Optional[datetime] = None

    def with_update(
        self,
        *,
        rsm_enabled: Optional[bool] = None,
        selected_bucket_id: Optional[str] = None,
        unset_selected_bucket_id: bool = False,
    ) -> "InteractionRecord":
        """Return a new record with the given fields overridden.

        `unset_selected_bucket_id=True` explicitly clears the selection
        (distinguishable from `selected_bucket_id=None` which leaves it alone).
        """
        new_bucket = self.selected_bucket_id
        if unset_selected_bucket_id:
            new_bucket = None
        elif selected_bucket_id is not None:
            new_bucket = selected_bucket_id

        return InteractionRecord(
            interaction_id=self.interaction_id,
            rsm_enabled=self.rsm_enabled if rsm_enabled is None else rsm_enabled,
            selected_bucket_id=new_bucket,
            last_streamed_at=self.last_streamed_at,
        )


def DEFAULT_INTERACTION(interaction_id: str) -> InteractionRecord:
    """Default (fail-closed) record for an unknown interaction id."""
    return InteractionRecord(
        interaction_id=interaction_id,
        rsm_enabled=False,
        selected_bucket_id=None,
        last_streamed_at=None,
    )
