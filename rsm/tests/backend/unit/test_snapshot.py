"""Snapshot — bounded derived representation (spec §3–§5)."""

import pytest

from rsm.bucket.model import Bucket
from rsm.extraction.text import extract_text
from rsm.integrity.sha256 import canonical_preimage
from rsm.snapshot import (
    ContextBudget,
    BudgetUnit,
    Snapshot,
    SnapshotKind,
    SnapshotBuildError,
    SummaryUnavailable,
    NullSummaryProvider,
    PrefixSummaryProvider,
    build_snapshot,
)


def _bucket(text: str) -> Bucket:
    return extract_text(text)


# --- schema shape ---

def test_snapshot_has_stable_schema_fields():
    b = _bucket("hello")
    snap = build_snapshot(b, budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=100))
    assert snap.schema_version == "1"
    assert snap.snapshot_id.startswith("snap_")
    assert snap.bucket_id == b.bucket_id
    assert snap.context_budget.unit == BudgetUnit.CHARACTERS
    assert snap.context_budget.value == 100
    assert snap.content.kind == SnapshotKind.PRESERVED
    assert snap.content.text == "hello"
    assert snap.integrity.algorithm == "sha256"
    assert len(snap.integrity.value) == 64


# --- preserved path ---

def test_snapshot_preserves_full_content_when_within_budget():
    b = _bucket("short")
    snap = build_snapshot(b, budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=100))
    assert snap.fits_within_budget is True
    assert snap.content.kind == SnapshotKind.PRESERVED
    assert snap.content.text == "short"
    assert snap.included_sources == [b.bucket_id]
    assert snap.reduced_sources == []
    assert snap.omitted_sources == []


# --- overflow without provider ---

def test_overflow_without_provider_raises():
    b = _bucket("x" * 200)
    with pytest.raises(SummaryUnavailable):
        build_snapshot(b, budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=50))


def test_null_provider_fails_explicitly():
    b = _bucket("x" * 200)
    with pytest.raises(SummaryUnavailable):
        build_snapshot(
            b,
            budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=50),
            summary_provider=NullSummaryProvider(),
        )


# --- overflow with prefix provider ---

def test_overflow_with_prefix_provider_produces_summary_within_budget():
    b = _bucket("y" * 1000)
    budget = ContextBudget(unit=BudgetUnit.CHARACTERS, value=120)
    snap = build_snapshot(b, budget=budget, summary_provider=PrefixSummaryProvider())
    assert snap.fits_within_budget is False  # Source does not fit
    assert snap.content.kind == SnapshotKind.SUMMARY
    assert snap.content.summary_provider == "prefix"
    assert snap.content.size_chars <= 120
    assert snap.content.reduced_from_chars == 1000
    assert snap.content.omitted_chars == 1000 - snap.content.size_chars
    assert snap.reduced_sources == [b.bucket_id]
    assert snap.omitted_sources == []
    assert "[TRUNCATED BY RSM" in snap.content.text


def test_summary_marks_derivation_clearly():
    """Spec §8: a summary MUST be explicitly marked as derived."""
    b = _bucket("y" * 1000)
    snap = build_snapshot(
        b,
        budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=120),
        summary_provider=PrefixSummaryProvider(),
    )
    assert snap.content.kind == SnapshotKind.SUMMARY
    assert snap.content.summary_provider is not None
    # The derived summary includes a human-readable marker so it cannot be
    # mistaken for the original source.
    assert "RSM PrefixSummaryProvider" in snap.content.text


# --- determinism of normalization ---

def test_identical_inputs_produce_identical_content():
    b1 = _bucket("same content")
    b2 = _bucket("same content")
    snap1 = build_snapshot(b1, budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=100))
    snap2 = build_snapshot(b2, budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=100))
    # content equals (snapshot_id and bucket_id differ)
    assert snap1.content.model_dump() == snap2.content.model_dump()


# --- A1: Bucket.hash is unaffected ---

def test_bucket_hash_unchanged_after_snapshot():
    import hashlib
    b = _bucket("A1 check")
    original_hash = b.hash.value
    reproduced_before = hashlib.sha256(canonical_preimage(b.model_dump(mode="json"))).hexdigest()
    build_snapshot(b, budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=100))
    build_snapshot(
        b,
        budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=5),
        summary_provider=PrefixSummaryProvider(),
    )
    reproduced_after = hashlib.sha256(canonical_preimage(b.model_dump(mode="json"))).hexdigest()
    assert b.hash.value == original_hash
    assert reproduced_before == original_hash
    assert reproduced_after == original_hash


def test_snapshot_integrity_is_independent_from_bucket_hash():
    b = _bucket("independent")
    snap = build_snapshot(b, budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=100))
    assert snap.integrity.value != b.hash.value


# --- budget enforcement ---

def test_snapshot_never_exceeds_declared_budget_for_preserved_path():
    b = _bucket("fit")
    snap = build_snapshot(b, budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=10))
    assert snap.content.size_chars <= 10


def test_snapshot_never_exceeds_declared_budget_for_summary_path():
    b = _bucket("z" * 10_000)
    for budget_value in (16, 64, 256, 1024):
        snap = build_snapshot(
            b,
            budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=budget_value),
            summary_provider=PrefixSummaryProvider(),
        )
        assert snap.content.size_chars <= budget_value


# --- budget units ---

def test_bytes_budget_works():
    b = _bucket("héllo \u2764" * 200)  # multi-byte UTF-8
    snap = build_snapshot(
        b,
        budget=ContextBudget(unit=BudgetUnit.BYTES, value=64),
        summary_provider=PrefixSummaryProvider(),
    )
    assert snap.content.size_bytes <= 64


def test_tokens_estimate_budget_works():
    b = _bucket("w" * 2000)
    snap = build_snapshot(
        b,
        budget=ContextBudget(unit=BudgetUnit.TOKENS_ESTIMATE, value=10),
        summary_provider=PrefixSummaryProvider(),
    )
    # tokens_estimate = ceil(chars/4), so chars ≤ 40
    est = (snap.content.size_chars + 3) // 4
    assert est <= 10


# --- provenance / audit ---

def test_provenance_links_to_bucket():
    b = _bucket("linked")
    snap = build_snapshot(b, budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=100))
    assert snap.provenance["derived_from"]["kind"] == "rsm_bucket"
    assert snap.provenance["derived_from"]["bucket_id"] == b.bucket_id
    assert snap.provenance["derived_from"]["bucket_hash"] == b.hash.value


def test_audit_trail_distinguishes_included_reduced_omitted():
    b = _bucket("y" * 500)
    # Preserved: included
    pres = build_snapshot(b, budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=1000))
    assert pres.included_sources == [b.bucket_id]
    assert pres.reduced_sources == []
    # Summary: reduced
    summ = build_snapshot(
        b,
        budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=50),
        summary_provider=PrefixSummaryProvider(),
    )
    assert summ.included_sources == []
    assert summ.reduced_sources == [b.bucket_id]


# --- no silent overflow if a buggy provider lies ---

class _BadProvider:
    name = "bad"
    def summarize(self, *, text, budget_bytes, budget_chars):
        return "x" * (budget_chars + 50)


def test_builder_rejects_provider_that_exceeds_budget():
    b = _bucket("x" * 10_000)
    with pytest.raises(SnapshotBuildError):
        build_snapshot(
            b,
            budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=64),
            summary_provider=_BadProvider(),
        )
