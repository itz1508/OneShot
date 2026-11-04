"""Structural backtest cases: detect absence before Build dispatch."""

from __future__ import annotations

import pytest

from agent.contracts.validation.structural import (
    CONCERNS,
    ConcernCell,
    ReferenceNeed,
    SourceDeclaration,
    TraceStep,
    concern_gaps,
    reference_gaps,
    trace_gaps,
)


@pytest.mark.parametrize(
    ("missing", "consumer"),
    [
        ("catalog", "research"),
        ("research_intent", "planning"),
        ("catalog_lineage", "handoff"),
        ("task_batch_wave", "build_compiler"),
        ("preimage_revision", "wave_2"),
        ("move_atomicity", "effect_executor"),
        ("tool_registry", "build_admission"),
    ],
)
def test_late_discovered_gap_class_is_caught_early(missing: str, consumer: str) -> None:
    """Synthetic backtest fixtures, NOT a historical repository re-run."""
    findings = reference_gaps(
        (ReferenceNeed(name=missing, consumer=consumer),),
        (SourceDeclaration(name="requirements", owner="research", evidence_ref="ref-001"),),
    )
    assert findings == [f"{consumer}: no producer for {missing}"]


def test_external_sources_require_owner_and_evidence() -> None:
    findings = reference_gaps(
        (ReferenceNeed(name="tool_registry", consumer="build"),),
        (SourceDeclaration(name="tool_registry", owner="", evidence_ref=""),),
    )
    assert any("missing owner/evidence" in finding for finding in findings)


def test_trace_walk_catches_missing_producer_and_effect_gate() -> None:
    findings = trace_gaps(
        (
            TraceStep("planning", frozenset({"requirements"}), frozenset({"spec"})),
            TraceStep("build", frozenset({"spec", "tool_registry"}), frozenset({"effects"}), effect="write"),
        ),
        (SourceDeclaration(name="requirements", owner="research", evidence_ref="req-001"),),
    )
    assert any("tool_registry" in finding for finding in findings)
    assert any("no gate" in finding for finding in findings)


def test_trace_walk_accepts_closed_provenance_and_host_gate() -> None:
    assert not trace_gaps(
        (TraceStep("build", frozenset({"tool_registry"}), frozenset({"receipt"}), "write", "host"),),
        (SourceDeclaration("tool_registry", "host", "lock-ref"),),
    )


def test_concern_matrix_requires_evidence_or_reason() -> None:
    cells = tuple(
        ConcernCell(stage="build", concern=concern, status="covered", owner="host", evidence_ref="ref")
        for concern in CONCERNS
    )
    assert concern_gaps(("build",), cells) == []
    assert any("missing coverage" in gap for gap in concern_gaps(("build",), cells[:-1]))
    assert any(
        "N/A reason" in gap for gap in concern_gaps(("build",), (ConcernCell("build", "cleanup", "not_applicable"),))
    )
