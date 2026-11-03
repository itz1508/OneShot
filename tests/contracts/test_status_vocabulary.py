"""Test exact status vocabulary and OperationState projection."""

import pytest

from agent.contracts.common import (
    CoverageStatus,
    CriteriaStatus,
    DiagnosticStatus,
    OperationState,
    ProposalState,
    SpecificationState,
    StepStatus,
)


def test_status_vocabulary_is_exact():
    assert {v.value for v in DiagnosticStatus} == {"valid", "not_valid", "uncertainty"}
    assert {v.value for v in StepStatus} == {"completed", "failed", "blocked", "not_run", "skipped"}
    assert {v.value for v in ProposalState} == {
        "proposal_only",
        "review_required",
        "approved_for_apply",
        "not_approved",
        "already_applied",
        "idempotent",
        "missing_parent",
        "protected_surface",
    }
    assert {v.value for v in OperationState} == {
        "not_run",
        "in_flight",
        "effect_uncertain",
        "completed",
        "failed",
        "blocked",
        "skipped",
    }
    assert {v.value for v in SpecificationState} == {"candidate", "frozen", "blocked"}
    assert {v.value for v in CriteriaStatus} == {"defined", "incomplete", "blocked"}
    assert {v.value for v in CoverageStatus} == {"covered", "blocked", "not_run", "not_applicable"}


def test_internal_operation_projection():
    assert OperationState.EFFECT_UNCERTAIN.final_report_status is StepStatus.BLOCKED
    with pytest.raises(ValueError):
        _ = OperationState.IN_FLIGHT.final_report_status
