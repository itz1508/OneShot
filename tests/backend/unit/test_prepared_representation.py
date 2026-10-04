"""Unit tests for `rsm.prepared.PreparedRepresentation`.

The Prepared Representation is the architectural name for the typed
envelope that unites:

    * SOURCE identity + integrity    (rsm.bucket)
    * SOURCE assessment              (rsm.assessment)
    * READER coverage                (rsm.reader)
    * PROCESSOR output (snapshot)    (rsm.snapshot)
    * REPLAY envelope                (rsm.replay)

The surface is purely a typed assembler — no new domain state, no new
I/O. These tests freeze the invariants.
"""

from __future__ import annotations

import pytest

from rsm.assessment import assess_source
from rsm.extraction.text import extract_text
from rsm.prepared import PreparedRepresentation, build_prepared_representation
from rsm.reader import read_bucket
from rsm.replay.envelope import build_replay_envelope
from rsm.snapshot import BudgetUnit, ContextBudget, build_snapshot


def _prepared(text: str = "hello world") -> tuple[PreparedRepresentation, dict]:
    bucket = extract_text(text, source_uri="demo.txt")
    assessment = assess_source(bucket)
    read_result = read_bucket(bucket)
    snap = build_snapshot(
        bucket,
        budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=max(1, len(text) + 50)),
    )
    envelope = build_replay_envelope(bucket)
    pr = build_prepared_representation(
        bucket=bucket,
        assessment=assessment,
        read_result=read_result,
        snapshot=snap,
        replay_envelope=envelope,
    )
    return pr, envelope


# ---- Shape ----


def test_prepared_representation_shape():
    pr, env = _prepared()
    d = pr.model_dump(mode="json")
    assert d["schema_version"] == "1"
    assert set(d.keys()) == {
        "schema_version", "bucket_id", "integrity",
        "assessment", "coverage", "snapshot", "replay",
    }
    # bucket_id is consistent across every sub-document.
    assert d["bucket_id"] == d["assessment"]["bucket_id"]
    assert d["bucket_id"] == d["coverage"]["bucket_id"]
    assert d["bucket_id"] == d["snapshot"]["bucket_id"]
    assert d["bucket_id"] == d["replay"]["bucket_id"]
    # Integrity is the Bucket's SHA-256 (A1 identity).
    assert d["integrity"]["algorithm"] == env["integrity"]["algorithm"]
    assert d["integrity"]["value"] == env["integrity"]["value"]


# ---- Preparation ≠ Source ----


def test_prepared_representation_is_derived_not_source():
    """The Prepared Representation carries provenance back to the Source
    but never becomes the Source. The replay envelope and snapshot both
    name the Bucket; neither claims to BE the authoritative Bucket."""
    pr, _ = _prepared("alpha")
    d = pr.model_dump(mode="json")
    # Replay envelope's provenance names the Source origin, not RSM.
    assert d["replay"]["provenance"]["origin"] == "text"
    # Snapshot provenance ties back to the Bucket by hash.
    assert d["snapshot"]["provenance"]["derived_from"]["bucket_hash"] == d["integrity"]["value"]


# ---- Observation preserved ----


def test_prepared_representation_includes_reader_coverage():
    pr, _ = _prepared("one line")
    d = pr.model_dump(mode="json")
    cov = d["coverage"]
    assert cov["discovered"] == 1
    assert cov["observed_count"] == 1
    assert cov["failed_count"] == 0
    assert cov["complete"] is True


# ---- Mismatched inputs are rejected ----


def test_build_prepared_rejects_mismatched_assessment():
    a_bucket = extract_text("A", source_uri="A.txt")
    b_bucket = extract_text("B", source_uri="B.txt")
    read_result = read_bucket(a_bucket)
    snap = build_snapshot(a_bucket, budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=10))
    envelope = build_replay_envelope(a_bucket)

    with pytest.raises(ValueError, match="assessment.bucket_id"):
        build_prepared_representation(
            bucket=a_bucket,
            assessment=assess_source(b_bucket),  # mismatched
            read_result=read_result,
            snapshot=snap,
            replay_envelope=envelope,
        )


def test_build_prepared_rejects_mismatched_read_result():
    a_bucket = extract_text("A", source_uri="A.txt")
    b_bucket = extract_text("B", source_uri="B.txt")
    snap = build_snapshot(a_bucket, budget=ContextBudget(unit=BudgetUnit.CHARACTERS, value=10))
    envelope = build_replay_envelope(a_bucket)

    with pytest.raises(ValueError, match="read_result.bucket_id"):
        build_prepared_representation(
            bucket=a_bucket,
            assessment=assess_source(a_bucket),
            read_result=read_bucket(b_bucket),
            snapshot=snap,
            replay_envelope=envelope,
        )
