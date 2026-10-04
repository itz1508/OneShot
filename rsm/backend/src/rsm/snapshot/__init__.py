"""Snapshot — bounded, derived representation of a Bucket's normalized source.

Scope (spec):
    External Source
        ↓ Ingestion → canonical Bucket (frozen under A1)
        ↓ Normalization (deterministic view)
        ↓ Snapshot (bounded; may use a derived summary)
        ↓ Replay to Agent

Snapshot has its own identity and provenance but MUST NOT mutate the Bucket.
Bucket.hash remains independently verifiable (A1).
"""

from .model import (
    ContextBudget,
    BudgetUnit,
    SnapshotContent,
    SnapshotIntegrity,
    Snapshot,
    SnapshotKind,
)
from .builder import SnapshotBuildError, build_snapshot
from .summary_provider import (
    SummaryProvider,
    SummaryUnavailable,
    NullSummaryProvider,
    PrefixSummaryProvider,
)

__all__ = [
    "ContextBudget",
    "BudgetUnit",
    "SnapshotContent",
    "SnapshotIntegrity",
    "Snapshot",
    "SnapshotKind",
    "SnapshotBuildError",
    "build_snapshot",
    "SummaryProvider",
    "SummaryUnavailable",
    "NullSummaryProvider",
    "PrefixSummaryProvider",
]
