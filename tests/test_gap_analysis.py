"""Canonical Gap Analysis ownership and missing-capability detection."""

from __future__ import annotations

from agent.contracts.common import DiagnosticStatus
from agent.gap_analysis import (
    CapabilityConsumer,
    CapabilityProducer,
    CapabilityRequirement,
    MissingCapabilityAnalyzer,
    RepositorySnapshot,
    audit_repository,
)


def test_missing_capability_reports_producer_symbol_and_consumer_gaps() -> None:
    requirements = (
        CapabilityRequirement(
            capability_id="tool_registry",
            producers=(CapabilityProducer(path="owner.py", symbols=("ToolRegistry",)),),
            consumers=(CapabilityConsumer(path="consumer.py", reference="ToolRegistry"),),
        ),
    )
    snapshot = RepositorySnapshot(
        source_id="fixture:broken",
        files={"owner.py": "class WrongOwner: pass\n", "consumer.py": "value = None\n"},
    )

    result = MissingCapabilityAnalyzer().analyze(snapshot, requirements)

    assert result.diagnostic_status is DiagnosticStatus.NOT_VALID
    assert {(gap.kind, gap.path) for gap in result.gaps} == {
        ("missing_symbol", "owner.py"),
        ("unresolved_consumer", "consumer.py"),
    }


def test_current_repository_uses_canonical_gap_owner_and_finds_real_missing_capabilities() -> None:
    result = audit_repository(".")
    gaps_by_capability = {gap.capability_id for gap in result.gaps}

    assert "gap_analysis_owner" not in gaps_by_capability
    assert "reference_closure" not in gaps_by_capability
    assert "execution_trace" not in gaps_by_capability
    assert "scanner_check_registry" in gaps_by_capability
    assert "runtime_root_registry" in gaps_by_capability
    assert "recovery_readiness" in gaps_by_capability
    assert "wave_preimage_pinning" in gaps_by_capability
    assert result.diagnostic_status is DiagnosticStatus.NOT_VALID
