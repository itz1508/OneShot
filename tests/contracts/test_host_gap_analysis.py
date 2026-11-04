"""Host structural-gap analyzer regression tests and fail-closed behavior."""

from __future__ import annotations

import pytest

from agent.contracts.scanner import ScannerOutcome
from agent.runtime.controller import HostController, TransitionError
from agent.runtime.host_gap_analyzer import StructuralGapError
from tests.fixtures.structural_gap import build_gap_inputs, passing_gap


def test_structural_gap_analyzer_persists_valid_result_and_receipt(tmp_path) -> None:
    controller = HostController(tmp_path)
    result = passing_gap(controller)
    assert result.result.execution_status == "completed"
    assert not result.result.findings
    assert result.result.known_critical_gap_detection_rate == 1.0
    assert result.result.walking_skeleton_completed
    assert result.completion_receipt_ref is not None
    controller.artifact_store.get_verified(result.result_ref.artifact_id, result.result_ref.artifact_revision)


def test_missing_walking_skeleton_blocks_and_never_issues_pass_receipt(tmp_path) -> None:
    controller = HostController(tmp_path)
    request, _runner = build_gap_inputs(controller)
    outcome = controller.run_structural_gap_analysis(request)
    assert outcome.result.execution_status == "blocked"
    assert "walking skeleton runner unavailable" in outcome.result.findings
    assert outcome.completion_receipt_ref is None


def test_missing_reference_and_registry_resolver_are_reported(tmp_path) -> None:
    controller = HostController(tmp_path)
    request, runner = build_gap_inputs(controller, missing_registry_source=True)
    outcome = controller.run_structural_gap_analysis(request, walking_skeleton_runner=runner)
    assert outcome.result.execution_status == "blocked"
    assert any("planning: no producer for tool_registry" in f for f in outcome.result.findings)
    assert any("registry entry without resolver: tool_registry" in f for f in outcome.result.findings)
    assert outcome.completion_receipt_ref is None


def test_mismatched_source_artifact_is_rejected(tmp_path) -> None:
    controller = HostController(tmp_path)
    request, runner = build_gap_inputs(controller)
    bad = request.candidate_specification_ref.model_copy(update={"artifact_digest": "0" * 64})
    with pytest.raises(StructuralGapError, match="missing or mismatched"):
        controller.run_structural_gap_analysis(
            request.model_copy(update={"candidate_specification_ref": bad}),
            walking_skeleton_runner=runner,
        )


def test_walking_skeleton_cannot_skip_trace_steps(tmp_path) -> None:
    controller = HostController(tmp_path)
    request, runner = build_gap_inputs(controller)

    def partial_skeleton(r):
        observed = runner(r)
        return observed.model_copy(update={"executed_steps": ("research", "planning")})

    outcome = controller.run_structural_gap_analysis(request, walking_skeleton_runner=partial_skeleton)
    assert outcome.result.execution_status == "blocked"
    assert any("walking skeleton incomplete" in msg for msg in outcome.result.findings)
    assert outcome.completion_receipt_ref is None


def test_skeleton_error_is_blocked_not_synthetic_success(tmp_path) -> None:
    controller = HostController(tmp_path)
    request, _ = build_gap_inputs(controller)

    def broken(_request):
        raise OSError("execution unavailable")

    outcome = controller.run_structural_gap_analysis(request, walking_skeleton_runner=broken)
    assert any("execution unavailable" in msg for msg in outcome.result.findings)
    assert outcome.completion_receipt_ref is None


def test_scanner_dispatch_requires_host_gap_pass(tmp_path) -> None:
    controller = HostController(tmp_path)
    request, _runner = build_gap_inputs(controller)
    controller.scanner.register_detector("syntax", lambda _content: ())
    with pytest.raises(TransitionError, match="structural gap analysis"):
        controller.scan_planning_candidate(
            request.task_id,
            request.run_id,
            request.candidate_specification_ref,
            "repo-snapshot",
            ("syntax",),
            None,
            None,
        )


def test_scanner_dispatch_accepts_only_exact_candidate_and_receipt(tmp_path) -> None:
    controller = HostController(tmp_path)
    request, runner = build_gap_inputs(controller)
    outcome = controller.run_structural_gap_analysis(request, walking_skeleton_runner=runner)
    assert outcome.completion_receipt_ref is not None
    controller.scanner.register_detector("syntax", lambda _content: ())
    result = controller.scan_planning_candidate(
        request.task_id,
        request.run_id,
        request.candidate_specification_ref,
        "repo-snapshot",
        ("syntax",),
        outcome.result_ref,
        outcome.completion_receipt_ref,
    )
    assert result.outcome == ScannerOutcome.PASS

    wrong = request.candidate_specification_ref.model_copy(update={"artifact_id": "different-candidate"})
    with pytest.raises(TransitionError, match="different candidate"):
        controller.scan_planning_candidate(
            request.task_id,
            request.run_id,
            wrong,
            "repo-snapshot",
            ("syntax",),
            outcome.result_ref,
            outcome.completion_receipt_ref,
        )
