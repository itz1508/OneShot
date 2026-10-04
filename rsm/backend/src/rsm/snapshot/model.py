"""Snapshot domain models (spec §3)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BudgetUnit(StrEnum):
    """Budget units Snapshot understands.

    - `bytes`             — UTF-8 byte length. Deterministic.
    - `characters`        — Unicode code points. Deterministic.
    - `tokens_estimate`   — ⌈chars/4⌉ heuristic. **Not** an exact model token count.
    """
    BYTES = "bytes"
    CHARACTERS = "characters"
    TOKENS_ESTIMATE = "tokens_estimate"


class ContextBudget(BaseModel):
    """Declared budget for a Snapshot (spec §4)."""
    model_config = ConfigDict(extra="forbid")

    unit: BudgetUnit = BudgetUnit.CHARACTERS
    value: int = Field(..., ge=1)
    # Flag that marks the budget as a true limit, not a heuristic.
    is_hard_limit: bool = True


class SnapshotKind(StrEnum):
    """Whether the Snapshot carries original or derived content."""
    PRESERVED = "preserved"  # full normalized source fit within budget
    SUMMARY = "summary"      # content reduced via a derived summary (SummaryProvider)


class SnapshotContent(BaseModel):
    """What the Snapshot actually carries."""
    model_config = ConfigDict(extra="forbid")

    kind: SnapshotKind
    text: str
    size_bytes: int
    size_chars: int
    # When kind == SUMMARY, these record the derivation audit trail (spec §5).
    reduced_from_bytes: int | None = None
    reduced_from_chars: int | None = None
    omitted_bytes: int | None = None
    omitted_chars: int | None = None
    summary_provider: str | None = None


class SnapshotIntegrity(BaseModel):
    """SHA-256 of the Snapshot's canonical bytes (independent of Bucket.hash)."""
    model_config = ConfigDict(extra="forbid")
    algorithm: Literal["sha256"] = "sha256"
    value: str = Field(..., pattern=r"^[0-9a-f]{64}$")


class Snapshot(BaseModel):
    """Bounded, derived representation of a Bucket's normalized source."""
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    snapshot_id: str
    bucket_id: str

    # When this Snapshot was built.
    created_at: datetime

    # Budget / sizing.
    context_budget: ContextBudget
    source_size_bytes: int
    source_size_chars: int
    source_token_estimate: int
    fits_within_budget: bool

    # Payload.
    content: SnapshotContent

    # Audit of which sources are PRESERVED vs REDUCED/OMITTED (spec §3). V2
    # Snapshot derives from exactly one Bucket; these lists use `bucket_id`.
    included_sources: list[str]
    reduced_sources: list[str]
    omitted_sources: list[str]

    # Provenance back to the Bucket.
    provenance: dict[str, Any]

    # Snapshot's own integrity.
    integrity: SnapshotIntegrity
