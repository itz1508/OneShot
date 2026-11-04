"""Host-owned structural gap analysis before Scanner and Planning acceptance.

Reuses the existing pure structural validators. Missing inputs, unavailable
walking-skeleton execution, and incomplete backtests fail closed. No role agent
owns this workflow or issues its receipt.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import Field

from agent.contracts.common import ArtifactRef, ContractModel
from agent.contracts.host import ReceiptRef
from agent.contracts.validation.structural import (
    ConcernCell,
    ReferenceNeed,
    SourceDeclaration,
    TraceStep,
    concern_gaps,
    reference_gaps,
    trace_gaps,
)
from agent.runtime.artifact_store import ArtifactStore
from agent.runtime.receipt_store import ReceiptStore


class StructuralGapError(RuntimeError):
    """A required structural input or its evidence cannot be verified."""


class WorkflowContractBundle(ContractModel):
    """Registered producer/consumer closure for the exact workflow revision."""

    stage_ids: tuple[str, ...] = Field(min_length=1)
    reference_needs: tuple[ReferenceNeed, ...] = ()
    persisted_output_slots: tuple[str, ...] = ()
    consumed_output_slots: tuple[str, ...] = ()
    terminal_output_slots: tuple[str, ...] = ()


class RegistrySnapshotSet(ContractModel):
    """Frozen registry entries with an accountable producer and evidence."""

    sources: tuple[SourceDeclaration, ...] = ()
    required_registry_ids: tuple[str, ...] = ()


class WorkflowExecutionTrace(ContractModel):
    """Ordered executable steps and their declared effect gates."""

    steps: tuple[TraceStep, ...] = Field(min_length=1)


class WorkflowConcernMatrix(ContractModel):
    stages: tuple[str, ...] = Field(min_length=1)
    cells: tuple[ConcernCell, ...] = ()


class KnownCriticalBacktest(ContractModel):
    case_id: str = Field(min_length=1)
    case_evidence_ref: ArtifactRef
    reference_needs: tuple[ReferenceNeed, ...] = ()
    sources: tuple[SourceDeclaration, ...] = ()
    trace_steps: tuple[TraceStep, ...] = ()
    stages: tuple[str, ...] = ()
    concern_cells: tuple[ConcernCell, ...] = ()
    expected_findings: tuple[str, ...] = Field(min_length=1)


class GapBacktestCorpus(ContractModel):
    historical_cases: tuple[KnownCriticalBacktest, ...] = Field(min_length=1)


class SourceGroundedAnalysis(ContractModel):
    source_snapshot_ref: ArtifactRef
    evidence_refs: tuple[ArtifactRef, ...] = Field(min_length=1)
    completed: bool
    unresolved: tuple[str, ...] = ()


class ComparableSystemAnalysis(ContractModel):
    evidence_refs: tuple[ArtifactRef, ...] = ()
    completed: bool
    not_applicable_reason: str = ""
    unresolved: tuple[str, ...] = ()


class WalkingSkeletonObservation(ContractModel):
    """Actual fixture execution returned by a host-registered runner."""

    completed: bool
    executed_steps: tuple[str, ...] = ()
    evidence_ref: ArtifactRef | None = None
    error: str = ""


class StructuralGapRequest(ContractModel):
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    request_revision: int = Field(ge=1)
    candidate_specification_ref: ArtifactRef
    workflow_contract_bundle_ref: ArtifactRef
    registry_snapshot_set_ref: ArtifactRef
    workflow_trace_ref: ArtifactRef
    concern_matrix_ref: ArtifactRef
    backtest_corpus_ref: ArtifactRef
    source_grounded_analysis_ref: ArtifactRef
    comparable_system_analysis_ref: ArtifactRef


class StructuralGapResult(ContractModel):
    task_id: str
    run_id: str
    request_id: str
    request_revision: int
    candidate_specification_ref: ArtifactRef
    workflow_contract_bundle_ref: ArtifactRef
    execution_status: str
    findings: tuple[str, ...]
    known_critical_gap_detection_rate: float
    walking_skeleton_completed: bool
    walking_skeleton_evidence_ref: ArtifactRef | None = None
    source_grounded: bool
    comparable_system_analysis_completed: bool


@dataclass(frozen=True)
class StructuralGapOutcome:
    result: StructuralGapResult
    result_ref: ArtifactRef
    completion_receipt_ref: ReceiptRef | None


SkeletonRunner = Callable[[StructuralGapRequest], WalkingSkeletonObservation]


def structural_gap_receipt_subject(result: StructuralGapResult, digest: str) -> str:
    """Bind host receipt to exact task/run/request/candidate and analysis digest."""
    return (
        f"structural_gap_pass:{result.task_id}:{result.run_id}:"
        f"{result.request_id}:{result.request_revision}:"
        f"{result.candidate_specification_ref.artifact_digest}:{digest}"
    )


class HostGapAnalyzer:
    """Execute all structural passes; only fully observed PASS earns a receipt."""

    def __init__(self, artifacts: ArtifactStore, receipts: ReceiptStore) -> None:
        self._artifacts = artifacts
        self._receipts = receipts

    def _get(self, ref: ArtifactRef, model: type[ContractModel]) -> ContractModel:
        try:
            content = self._artifacts.get_verified(ref.artifact_id, ref.artifact_revision)
            digest = self._artifacts.get_digest(ref.artifact_id, ref.artifact_revision)
            if digest != ref.artifact_digest:
                raise StructuralGapError(f"artifact digest mismatch: {ref.artifact_id}")
            return model.model_validate_json(content)
        except StructuralGapError:
            raise
        except Exception as exc:
            raise StructuralGapError(f"cannot validate {ref.artifact_id}: {exc}") from exc

    def _verify(self, ref: ArtifactRef) -> None:
        if self._artifacts.get_digest(ref.artifact_id, ref.artifact_revision) != ref.artifact_digest:
            raise StructuralGapError(f"missing or mismatched artifact: {ref.artifact_id}")
        self._artifacts.get_verified(ref.artifact_id, ref.artifact_revision)

    def evaluate(
        self,
        request: StructuralGapRequest,
        *,
        walking_skeleton_runner: SkeletonRunner | None = None,
    ) -> StructuralGapOutcome:
        """Run reference, trace, concern, backtest, skeleton, source and comparable passes.

        The walking skeleton must be executed by host-supplied trusted runner.
        An absent or failing runner never produces a successful receipt.
        """
        self._verify(request.candidate_specification_ref)
        workflow = self._get(request.workflow_contract_bundle_ref, WorkflowContractBundle)
        registry = self._get(request.registry_snapshot_set_ref, RegistrySnapshotSet)
        trace = self._get(request.workflow_trace_ref, WorkflowExecutionTrace)
        matrix = self._get(request.concern_matrix_ref, WorkflowConcernMatrix)
        corpus = self._get(request.backtest_corpus_ref, GapBacktestCorpus)
        grounded = self._get(request.source_grounded_analysis_ref, SourceGroundedAnalysis)
        comparable = self._get(request.comparable_system_analysis_ref, ComparableSystemAnalysis)
        assert isinstance(workflow, WorkflowContractBundle)
        assert isinstance(registry, RegistrySnapshotSet)
        assert isinstance(trace, WorkflowExecutionTrace)
        assert isinstance(matrix, WorkflowConcernMatrix)
        assert isinstance(corpus, GapBacktestCorpus)
        assert isinstance(grounded, SourceGroundedAnalysis)
        assert isinstance(comparable, ComparableSystemAnalysis)

        findings = reference_gaps(workflow.reference_needs, registry.sources)
        findings.extend(trace_gaps(trace.steps, registry.sources))
        findings.extend(concern_gaps(matrix.stages, matrix.cells))
        if set(workflow.stage_ids) != set(matrix.stages):
            findings.append("concern matrix stage coverage differs from workflow")
        unknown_outputs = (
            set(workflow.persisted_output_slots)
            - set(workflow.consumed_output_slots)
            - set(workflow.terminal_output_slots)
        )
        findings.extend(f"persisted output without consumer: {name}" for name in sorted(unknown_outputs))
        producers = {source.name for source in registry.sources if source.owner and source.evidence_ref}
        findings.extend(
            f"registry entry without resolver: {name}"
            for name in sorted(set(registry.required_registry_ids) - producers)
        )

        # Backtest all known critical cases against actual deterministic validators.
        total = 0
        detected = 0
        for case in corpus.historical_cases:
            self._verify(case.case_evidence_ref)
            observed = set(reference_gaps(case.reference_needs, case.sources))
            observed.update(trace_gaps(case.trace_steps, case.sources))
            if case.stages:
                observed.update(concern_gaps(case.stages, case.concern_cells))
            for expected in case.expected_findings:
                total += 1
                if expected in observed:
                    detected += 1
                else:
                    findings.append(f"backtest {case.case_id}: missed known gap: {expected}")
        rate = detected / total if total else 0.0
        if rate != 1.0:
            findings.append(f"known critical gap detection rate: {rate:.3f}, required 1.0")

        # Source and comparable-system findings must be supported by stored evidence.
        self._verify(grounded.source_snapshot_ref)
        for ref in grounded.evidence_refs:
            self._verify(ref)
        source_valid = grounded.completed and not grounded.unresolved
        if not source_valid:
            findings.append("source-grounded analysis incomplete")
        for ref in comparable.evidence_refs:
            self._verify(ref)
        comparable_valid = (
            comparable.completed
            and not comparable.unresolved
            and (bool(comparable.evidence_refs) or bool(comparable.not_applicable_reason))
        )
        if not comparable_valid:
            findings.append("comparable-system analysis incomplete")

        skeleton = None
        if walking_skeleton_runner is None:
            findings.append("walking skeleton runner unavailable")
        else:
            try:
                skeleton = walking_skeleton_runner(request)
            except Exception as exc:
                findings.append(f"walking skeleton execution failed: {exc}")
        skeleton_valid = False
        if skeleton is not None:
            if skeleton.evidence_ref is not None:
                self._verify(skeleton.evidence_ref)
            required_steps = {step.step_id for step in trace.steps}
            skeleton_valid = (
                skeleton.completed
                and skeleton.evidence_ref is not None
                and required_steps <= set(skeleton.executed_steps)
            )
            if not skeleton_valid:
                findings.append(f"walking skeleton incomplete: {skeleton.error or 'missing step or evidence'}")

        findings = list(dict.fromkeys(findings))
        passed = not findings
        result = StructuralGapResult(
            task_id=request.task_id,
            run_id=request.run_id,
            request_id=request.request_id,
            request_revision=request.request_revision,
            candidate_specification_ref=request.candidate_specification_ref,
            workflow_contract_bundle_ref=request.workflow_contract_bundle_ref,
            execution_status="completed" if passed else "blocked",
            findings=tuple(findings),
            known_critical_gap_detection_rate=rate,
            walking_skeleton_completed=skeleton_valid,
            walking_skeleton_evidence_ref=skeleton.evidence_ref if skeleton else None,
            source_grounded=source_valid,
            comparable_system_analysis_completed=comparable_valid,
        )
        result_id = (
            f"structural-gap-{request.task_id}-{request.run_id}-{request.candidate_specification_ref.artifact_digest}"
        )
        digest = self._artifacts.put_immutable(result, result_id, 1, "structural_analysis_result", "1.0")
        ref = ArtifactRef(
            artifact_id=result_id,
            artifact_revision=1,
            artifact_digest=digest,
            contract_id="structural_analysis_result",
            contract_version="1.0",
            serializer_profile="rfc8785-jcs-sha256-v1",
        )
        if not passed:
            return StructuralGapOutcome(result=result, result_ref=ref, completion_receipt_ref=None)

        receipt_id = f"gap-pass-{result_id}"
        _, receipt_digest = self._receipts.issue_verified(
            receipt_id, "host", structural_gap_receipt_subject(result, digest)
        )
        receipt = ReceiptRef(receipt_id=receipt_id, receipt_digest=receipt_digest, issuer_id="host")
        return StructuralGapOutcome(result=result, result_ref=ref, completion_receipt_ref=receipt)
