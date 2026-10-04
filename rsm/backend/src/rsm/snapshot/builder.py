"""Snapshot builder (spec §5)."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ..bucket.model import Bucket
from ..bucket.serializer import canonical_dumps
from ..normalization.model import NormalizedSource, normalize
from .model import (
    BudgetUnit,
    ContextBudget,
    Snapshot,
    SnapshotContent,
    SnapshotIntegrity,
    SnapshotKind,
)
from .summary_provider import SummaryProvider, SummaryUnavailable


class SnapshotBuildError(Exception):
    """Raised when a Snapshot cannot be constructed."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_snapshot_id() -> str:
    return f"snap_{uuid.uuid4().hex}"


def _measure(text: str, unit: BudgetUnit) -> int:
    if unit == BudgetUnit.BYTES:
        return len(text.encode("utf-8"))
    if unit == BudgetUnit.CHARACTERS:
        return len(text)
    if unit == BudgetUnit.TOKENS_ESTIMATE:
        return (len(text) + 3) // 4
    raise AssertionError(f"unknown budget unit: {unit}")


def _within_budget(text: str, budget: ContextBudget) -> bool:
    return _measure(text, budget.unit) <= budget.value


def _budget_as_bytes_chars(budget: ContextBudget) -> tuple[int, int]:
    """Translate a declared budget into (byte_cap, char_cap) for providers."""
    v = budget.value
    if budget.unit == BudgetUnit.BYTES:
        return (v, v)  # chars ≤ bytes for UTF-8
    if budget.unit == BudgetUnit.CHARACTERS:
        return (v * 4, v)  # UTF-8 character ≤ 4 bytes
    if budget.unit == BudgetUnit.TOKENS_ESTIMATE:
        # tokens_estimate = ceil(chars/4) ⇒ allow chars ≤ v * 4
        char_cap = v * 4
        return (char_cap * 4, char_cap)
    raise AssertionError(f"unknown budget unit: {budget.unit}")


def _snapshot_hash(payload: dict[str, Any]) -> str:
    """SHA-256 over the canonical bytes of the Snapshot projection, excluding
    the `integrity` field (self-reference)."""
    projected = {k: v for k, v in payload.items() if k != "integrity"}
    return hashlib.sha256(canonical_dumps(projected)).hexdigest()


def build_snapshot(
    bucket: Bucket,
    *,
    budget: ContextBudget,
    summary_provider: SummaryProvider | None = None,
) -> Snapshot:
    """Build a bounded Snapshot of a Bucket.

    Behaviour:
      - If the normalized source fits within `budget`, the Snapshot is PRESERVED
        (full content, no derivation).
      - If it does not fit and a `summary_provider` is given, the Snapshot is a
        SUMMARY whose text is produced by the provider. The result MUST fit
        within the budget; otherwise `SnapshotBuildError`.
      - If it does not fit and no provider is given, `SummaryUnavailable` is
        raised. **No silent truncation.**
      - The Bucket is never mutated. The Bucket's `hash.value` is unaffected.
    """
    ns: NormalizedSource = normalize(bucket)
    source_bytes = ns.size_bytes
    source_chars = ns.size_chars

    fits = _within_budget(ns.content_text, budget)

    if fits:
        content = SnapshotContent(
            kind=SnapshotKind.PRESERVED,
            text=ns.content_text,
            size_bytes=source_bytes,
            size_chars=source_chars,
        )
        reduced_sources: list[str] = []
        omitted_sources: list[str] = []
    else:
        if summary_provider is None:
            raise SummaryUnavailable(
                "Source exceeds Snapshot budget and no SummaryProvider is wired."
            )
        byte_cap, char_cap = _budget_as_bytes_chars(budget)
        summary_text = summary_provider.summarize(
            text=ns.content_text,
            budget_bytes=byte_cap,
            budget_chars=char_cap,
        )
        if not _within_budget(summary_text, budget):
            raise SnapshotBuildError(
                f"SummaryProvider {summary_provider.name!r} returned text "
                f"that exceeds the declared budget "
                f"({budget.value} {budget.unit.value})."
            )
        sb = len(summary_text.encode("utf-8"))
        sc = len(summary_text)
        content = SnapshotContent(
            kind=SnapshotKind.SUMMARY,
            text=summary_text,
            size_bytes=sb,
            size_chars=sc,
            reduced_from_bytes=source_bytes,
            reduced_from_chars=source_chars,
            omitted_bytes=max(0, source_bytes - sb),
            omitted_chars=max(0, source_chars - sc),
            summary_provider=summary_provider.name,
        )
        reduced_sources = [bucket.bucket_id]
        omitted_sources = []

    snapshot_id = _new_snapshot_id()
    created_at = _utcnow()

    # Provenance: this Snapshot was DERIVED from the Bucket.
    provenance = {
        "derived_from": {
            "kind": "rsm_bucket",
            "bucket_id": bucket.bucket_id,
            "bucket_hash": bucket.hash.value,
        },
        "produced_at": created_at.isoformat().replace("+00:00", "Z"),
    }

    draft: dict[str, Any] = {
        "schema_version": "1",
        "snapshot_id": snapshot_id,
        "bucket_id": bucket.bucket_id,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "context_budget": budget.model_dump(mode="json"),
        "source_size_bytes": source_bytes,
        "source_size_chars": source_chars,
        "source_token_estimate": ns.token_estimate,
        "fits_within_budget": fits,
        "content": content.model_dump(mode="json"),
        "included_sources": [bucket.bucket_id] if fits else [],
        "reduced_sources": reduced_sources,
        "omitted_sources": omitted_sources,
        "provenance": provenance,
    }
    digest = _snapshot_hash(draft)
    integrity = SnapshotIntegrity(value=digest)
    return Snapshot(
        schema_version="1",
        snapshot_id=snapshot_id,
        bucket_id=bucket.bucket_id,
        created_at=created_at,
        context_budget=budget,
        source_size_bytes=source_bytes,
        source_size_chars=source_chars,
        source_token_estimate=ns.token_estimate,
        fits_within_budget=fits,
        content=content,
        included_sources=[bucket.bucket_id] if fits else [],
        reduced_sources=reduced_sources,
        omitted_sources=omitted_sources,
        provenance=provenance,
        integrity=integrity,
    )
