"""Structural backtest cases: detect absence before Build dispatch."""

from __future__ import annotations

import pytest

from agent.contracts.validation.structural import (
    CONCERNS,
    ConcernCell,
    PersistenceDeclaration,
    ReferenceNeed,
    SourceDeclaration,
    TraceStep,
    concern_gaps,
    reference_gaps,
    registry_resolution_gaps,
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
        ("registered_command_resolver", "build_action_verification"),
        ("sandbox_profile_registry", "sandbox_execution"),
        ("scanner_check_registry", "scanner"),
        ("runtime_root_registry", "runtime_output_allocation"),
        ("recovery_readiness", "build_admission"),
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


def test_registry_sources_require_separate_effect_time_resolvers() -> None:
    findings = registry_resolution_gaps(
        ("tool_registry",),
        (SourceDeclaration("tool_registry", "host", "snapshot-ref"),),
    )
    assert findings == [
        "registry entry without resolver: tool_registry",
        "registry entry without effect-time resolver: tool_registry",
    ]


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
        (
            TraceStep(
                "build",
                frozenset({"tool_registry"}),
                frozenset({"receipt"}),
                "write",
                "host",
                persistence=(PersistenceDeclaration("receipt", terminal=True),),
            ),
        ),
        (SourceDeclaration("tool_registry", "host", "lock-ref"),),
    )


def test_trace_walk_validates_persisted_output_consumers() -> None:
    findings = trace_gaps(
        (
            TraceStep(
                "research",
                frozenset({"requirements"}),
                frozenset({"research_record"}),
                persistence=(PersistenceDeclaration("research_record", frozenset({"planning"})),),
            ),
            TraceStep(
                "planning",
                frozenset({"other_input"}),
                frozenset({"candidate"}),
                persistence=(PersistenceDeclaration("candidate", terminal=True),),
            ),
        ),
        (SourceDeclaration("requirements", "host", "requirements-ref"),),
    )
    assert "planning: does not consume declared output research_record" in findings


def test_trace_walk_rejects_persisted_output_without_consumer() -> None:
    findings = trace_gaps(
        (
            TraceStep(
                "research",
                frozenset({"requirements"}),
                frozenset({"research_record"}),
                persistence=(PersistenceDeclaration("research_record"),),
            ),
        ),
        (SourceDeclaration("requirements", "host", "requirements-ref"),),
    )
    assert "research: persisted output without consumer: research_record" in findings


def test_trace_walk_requires_output_persistence_classification() -> None:
    findings = trace_gaps(
        (TraceStep("research", frozenset({"requirements"}), frozenset({"research_record"})),),
        (SourceDeclaration("requirements", "host", "requirements-ref"),),
    )
    assert "research: output persistence not declared: research_record" in findings


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
