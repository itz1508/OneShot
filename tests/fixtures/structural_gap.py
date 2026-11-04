"""Test inputs for a genuine host structural-gap invocation.

These are synthetic fixtures, not historical production evidence or an
independent product E2E test. Only host-owned fixtures use these helpers.
"""

from __future__ import annotations

from pydantic import BaseModel

from agent.contracts.common import ArtifactRef
from agent.contracts.validation.structural import (
    CONCERNS,
    ConcernCell,
    ReferenceNeed,
    SourceDeclaration,
    TraceStep,
)
from agent.runtime.controller import HostController
from agent.runtime.host_gap_analyzer import (
    ComparableSystemAnalysis,
    GapBacktestCorpus,
    KnownCriticalBacktest,
    RegistrySnapshotSet,
    SourceGroundedAnalysis,
    StructuralGapOutcome,
    StructuralGapRequest,
    WalkingSkeletonObservation,
    WorkflowConcernMatrix,
    WorkflowContractBundle,
    WorkflowExecutionTrace,
)


class FixturePayload(BaseModel):
    content: str


def _store(controller: HostController, name: str, model: BaseModel) -> ArtifactRef:
    digest = controller.artifact_store.put_immutable(model, name, 1, "test_fixture", "1.0")
    return ArtifactRef(
        artifact_id=name,
        artifact_revision=1,
        artifact_digest=digest,
        contract_id="test_fixture",
        contract_version="1.0",
        serializer_profile="rfc8785-jcs-sha256-v1",
    )


def build_gap_inputs(
    controller: HostController,
    task_id: str = "task-001",
    run_id: str = "run-001",
    *,
    missing_registry_source: bool = False,
) -> tuple[StructuralGapRequest, object]:
    candidate = _store(controller, "candidate", FixturePayload(content="approved candidate"))
    source_snapshot = _store(controller, "source-snapshot", FixturePayload(content="repository snapshot"))
    evidence = _store(controller, "source-evidence", FixturePayload(content="inspected source evidence"))
    comparable_evidence = _store(controller, "comparable-evidence", FixturePayload(content="external system evidence"))
    historical_evidence = _store(controller, "historical-case", FixturePayload(content="known critical gap case"))
    skeleton_evidence = _store(controller, "walking-skeleton", FixturePayload(content="observed fixture run"))

    stages = ("research", "audit_discovery", "planning")
    roots = (
        SourceDeclaration("requirements", "host", "requirements-ref"),
        SourceDeclaration("tool_registry", "host", "tool-registry-ref"),
    )
    if missing_registry_source:
        roots = roots[:1]
    workflow = WorkflowContractBundle(
        stage_ids=stages,
        reference_needs=(ReferenceNeed("tool_registry", "planning"),),
        persisted_output_slots=("research_record", "audit_record", "planning_record"),
        consumed_output_slots=("research_record", "audit_record"),
        terminal_output_slots=("planning_record",),
    )
    registry = RegistrySnapshotSet(sources=roots, required_registry_ids=("tool_registry",))
    trace = WorkflowExecutionTrace(
        steps=(
            TraceStep("research", frozenset({"requirements"}), frozenset({"research_record"})),
            TraceStep("audit", frozenset({"research_record"}), frozenset({"audit_record"})),
            TraceStep("planning", frozenset({"audit_record", "tool_registry"}), frozenset({"planning_record"})),
        )
    )
    matrix = WorkflowConcernMatrix(
        stages=stages,
        cells=tuple(
            ConcernCell(stage=stage, concern=concern, status="covered", owner="host", evidence_ref="evidence")
            for stage in stages
            for concern in sorted(CONCERNS)
        ),
    )
    backtests = GapBacktestCorpus(
        historical_cases=(
            KnownCriticalBacktest(
                case_id="historical-001",
                case_evidence_ref=historical_evidence,
                reference_needs=(ReferenceNeed("missing_lock", "build_admission"),),
                sources=(SourceDeclaration("requirements", "host", "req"),),
                expected_findings=("build_admission: no producer for missing_lock",),
            ),
        )
    )
    grounded = SourceGroundedAnalysis(
        source_snapshot_ref=source_snapshot,
        evidence_refs=(evidence,),
        completed=True,
    )
    comparable = ComparableSystemAnalysis(
        evidence_refs=(comparable_evidence,),
        completed=True,
    )
    request = StructuralGapRequest(
        task_id=task_id,
        run_id=run_id,
        request_id="plan-request",
        request_revision=1,
        candidate_specification_ref=candidate,
        workflow_contract_bundle_ref=_store(controller, "workflow-contract", workflow),
        registry_snapshot_set_ref=_store(controller, "registry-snapshot", registry),
        workflow_trace_ref=_store(controller, "workflow-trace", trace),
        concern_matrix_ref=_store(controller, "concern-matrix", matrix),
        backtest_corpus_ref=_store(controller, "backtests", backtests),
        source_grounded_analysis_ref=_store(controller, "source-analysis", grounded),
        comparable_system_analysis_ref=_store(controller, "comparison", comparable),
    )

    def skeleton_runner(_: StructuralGapRequest) -> WalkingSkeletonObservation:
        # Exercise the stored fixture evidence instead of returning a blind boolean.
        controller.artifact_store.get_verified(skeleton_evidence.artifact_id, skeleton_evidence.artifact_revision)
        return WalkingSkeletonObservation(
            completed=True,
            executed_steps=("research", "audit", "planning"),
            evidence_ref=skeleton_evidence,
        )

    return request, skeleton_runner


def passing_gap(controller: HostController) -> StructuralGapOutcome:
    request, runner = build_gap_inputs(controller)
    return controller.run_structural_gap_analysis(request, walking_skeleton_runner=runner)
