"""Canonical missing-capability and structural gap analysis owner.

This module decides whether a Planning candidate is structurally complete.
It is pure: host-only artifact verification, persistence, execution, and
receipt issuance remain in ``agent.runtime.host_gap_analyzer``.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path

from pydantic import Field

from agent.contracts.common import ArtifactRef, ContractModel, DiagnosticStatus, StepStatus
from agent.contracts.validation.structural import (
    ConcernCell,
    ReferenceNeed,
    SourceDeclaration,
    TraceStep,
    concern_gaps,
    reference_gaps,
    registry_resolution_gaps,
    trace_gaps,
)


class WorkflowContractBundle(ContractModel):
    """Declared stages, cross-stage references, and persisted outputs."""

    stage_ids: tuple[str, ...] = Field(min_length=1)
    reference_needs: tuple[ReferenceNeed, ...] = ()
    persisted_output_slots: tuple[str, ...] = ()
    consumed_output_slots: tuple[str, ...] = ()
    terminal_output_slots: tuple[str, ...] = ()


class RegistrySnapshotSet(ContractModel):
    """Frozen capability registries and their effect-time resolvers."""

    sources: tuple[SourceDeclaration, ...] = ()
    required_registry_ids: tuple[str, ...] = ()


class WorkflowExecutionTrace(ContractModel):
    """Ordered workflow steps with dependencies, outputs, effects, and gates."""

    steps: tuple[TraceStep, ...] = Field(min_length=1)


class WorkflowConcernMatrix(ContractModel):
    """Required concern coverage for every declared workflow stage."""

    stages: tuple[str, ...] = Field(min_length=1)
    cells: tuple[ConcernCell, ...] = ()


class KnownCriticalBacktest(ContractModel):
    """One historical omission that the current analyzer must detect."""

    case_id: str = Field(min_length=1)
    case_evidence_ref: ArtifactRef
    reference_needs: tuple[ReferenceNeed, ...] = ()
    sources: tuple[SourceDeclaration, ...] = ()
    trace_steps: tuple[TraceStep, ...] = ()
    stages: tuple[str, ...] = ()
    concern_cells: tuple[ConcernCell, ...] = ()
    expected_findings: tuple[str, ...] = Field(min_length=1)


class GapBacktestCorpus(ContractModel):
    """Historical failures used to prevent regression in detection ability."""

    historical_cases: tuple[KnownCriticalBacktest, ...] = Field(min_length=1)


class SourceGroundedAnalysis(ContractModel):
    """Evidence that candidate capabilities were compared with actual source."""

    source_snapshot_ref: ArtifactRef
    evidence_refs: tuple[ArtifactRef, ...] = Field(min_length=1)
    completed: bool
    unresolved: tuple[str, ...] = ()


class ComparableSystemAnalysis(ContractModel):
    """Evidence that applicable comparable systems were checked."""

    evidence_refs: tuple[ArtifactRef, ...] = ()
    completed: bool
    not_applicable_reason: str = ""
    unresolved: tuple[str, ...] = ()


class WalkingSkeletonObservation(ContractModel):
    """Observed execution of the minimal complete workflow."""

    completed: bool
    executed_steps: tuple[str, ...] = ()
    evidence_ref: ArtifactRef | None = None
    error: str = ""


class StructuralGapRequest(ContractModel):
    """Exact immutable inputs for one candidate analysis."""

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
    """Evidence-backed determination for one exact Planning candidate."""

    task_id: str
    run_id: str
    request_id: str
    request_revision: int
    candidate_specification_ref: ArtifactRef
    workflow_contract_bundle_ref: ArtifactRef
    execution_status: StepStatus
    diagnostic_status: DiagnosticStatus
    findings: tuple[str, ...]
    known_critical_gap_detection_rate: float
    walking_skeleton_completed: bool
    walking_skeleton_evidence_ref: ArtifactRef | None = None
    source_grounded: bool
    comparable_system_analysis_completed: bool


class GapAnalyzer:
    """Detect missing capabilities before Scanner or Planning acceptance."""

    def analyze(
        self,
        request: StructuralGapRequest,
        workflow: WorkflowContractBundle,
        registry: RegistrySnapshotSet,
        trace: WorkflowExecutionTrace,
        matrix: WorkflowConcernMatrix,
        corpus: GapBacktestCorpus,
        grounded: SourceGroundedAnalysis,
        comparable: ComparableSystemAnalysis,
        skeleton: WalkingSkeletonObservation | None,
    ) -> StructuralGapResult:
        """Run every deterministic gap pass over already verified inputs."""
        findings = reference_gaps(workflow.reference_needs, registry.sources)
        findings.extend(trace_gaps(trace.steps, registry.sources))
        findings.extend(concern_gaps(matrix.stages, matrix.cells))

        if set(workflow.stage_ids) != set(matrix.stages):
            findings.append("concern matrix stage coverage differs from workflow")

        unconsumed = (
            set(workflow.persisted_output_slots)
            - set(workflow.consumed_output_slots)
            - set(workflow.terminal_output_slots)
        )
        findings.extend(f"persisted output without consumer: {name}" for name in sorted(unconsumed))
        findings.extend(registry_resolution_gaps(registry.required_registry_ids, registry.sources))

        total, detected = self._run_backtests(corpus, findings)
        rate = detected / total if total else 0.0
        if rate != 1.0:
            findings.append(f"known critical gap detection rate: {rate:.3f}, required 1.0")

        source_valid = grounded.completed and not grounded.unresolved
        if not source_valid:
            findings.append("source-grounded analysis incomplete")

        comparable_valid = (
            comparable.completed
            and not comparable.unresolved
            and (bool(comparable.evidence_refs) or bool(comparable.not_applicable_reason))
        )
        if not comparable_valid:
            findings.append("comparable-system analysis incomplete")

        skeleton_valid = self._check_skeleton(trace, skeleton, findings)
        findings = list(dict.fromkeys(findings))

        if not findings:
            execution_status = StepStatus.COMPLETED
            diagnostic_status = DiagnosticStatus.VALID
        elif skeleton is None:
            execution_status = StepStatus.BLOCKED
            diagnostic_status = DiagnosticStatus.UNCERTAINTY
        else:
            execution_status = StepStatus.FAILED
            diagnostic_status = DiagnosticStatus.NOT_VALID

        return StructuralGapResult(
            task_id=request.task_id,
            run_id=request.run_id,
            request_id=request.request_id,
            request_revision=request.request_revision,
            candidate_specification_ref=request.candidate_specification_ref,
            workflow_contract_bundle_ref=request.workflow_contract_bundle_ref,
            execution_status=execution_status,
            diagnostic_status=diagnostic_status,
            findings=tuple(findings),
            known_critical_gap_detection_rate=rate,
            walking_skeleton_completed=skeleton_valid,
            walking_skeleton_evidence_ref=skeleton.evidence_ref if skeleton else None,
            source_grounded=source_valid,
            comparable_system_analysis_completed=comparable_valid,
        )

    @staticmethod
    def _run_backtests(corpus: GapBacktestCorpus, findings: list[str]) -> tuple[int, int]:
        total = 0
        detected = 0
        for case in corpus.historical_cases:
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
        return total, detected

    @staticmethod
    def _check_skeleton(
        trace: WorkflowExecutionTrace,
        skeleton: WalkingSkeletonObservation | None,
        findings: list[str],
    ) -> bool:
        if skeleton is None:
            findings.append("walking skeleton runner unavailable")
            return False
        required_steps = {step.step_id for step in trace.steps}
        valid = (
            skeleton.completed and skeleton.evidence_ref is not None and required_steps <= set(skeleton.executed_steps)
        )
        if not valid:
            findings.append(f"walking skeleton incomplete: {skeleton.error or 'missing step or evidence'}")
        return valid


class CapabilityProducer(ContractModel):
    """Expected source owner and symbols for one required capability."""

    path: str = Field(min_length=1)
    symbols: tuple[str, ...] = ()


class CapabilityConsumer(ContractModel):
    """Expected source consumer and the capability reference it must contain."""

    path: str = Field(min_length=1)
    reference: str = Field(min_length=1)


class CapabilityRequirement(ContractModel):
    """One capability whose producer and consumers must close."""

    capability_id: str = Field(min_length=1)
    producers: tuple[CapabilityProducer, ...] = Field(min_length=1)
    consumers: tuple[CapabilityConsumer, ...] = ()


class RepositorySnapshot(ContractModel):
    """Exact source texts needed for a capability audit."""

    source_id: str = Field(min_length=1)
    files: dict[str, str]


class CapabilityGap(ContractModel):
    capability_id: str
    kind: str
    path: str
    detail: str


class CapabilityAuditResult(ContractModel):
    source_id: str
    diagnostic_status: DiagnosticStatus
    checked_capabilities: tuple[str, ...]
    gaps: tuple[CapabilityGap, ...]
    limitations: tuple[str, ...] = (
        "static producer/symbol/consumer audit; walking-skeleton execution is a separate host pass",
    )


class MissingCapabilityAnalyzer:
    """Detect capability omissions in current or historical source snapshots."""

    def analyze(
        self,
        snapshot: RepositorySnapshot,
        requirements: tuple[CapabilityRequirement, ...],
    ) -> CapabilityAuditResult:
        gaps: list[CapabilityGap] = []
        for requirement in requirements:
            for producer in requirement.producers:
                source = snapshot.files.get(producer.path)
                if source is None:
                    gaps.append(
                        CapabilityGap(
                            capability_id=requirement.capability_id,
                            kind="missing_producer",
                            path=producer.path,
                            detail="required producer file is absent",
                        )
                    )
                    continue
                symbols = self._python_symbols(source) if producer.path.endswith(".py") else set()
                for symbol in producer.symbols:
                    if symbol not in symbols:
                        gaps.append(
                            CapabilityGap(
                                capability_id=requirement.capability_id,
                                kind="missing_symbol",
                                path=producer.path,
                                detail=f"required producer symbol is absent: {symbol}",
                            )
                        )
            for consumer in requirement.consumers:
                source = snapshot.files.get(consumer.path)
                if source is None:
                    gaps.append(
                        CapabilityGap(
                            capability_id=requirement.capability_id,
                            kind="missing_consumer",
                            path=consumer.path,
                            detail="required consumer file is absent",
                        )
                    )
                elif re.search(rf"(?<![A-Za-z0-9_]){re.escape(consumer.reference)}(?![A-Za-z0-9_])", source) is None:
                    gaps.append(
                        CapabilityGap(
                            capability_id=requirement.capability_id,
                            kind="unresolved_consumer",
                            path=consumer.path,
                            detail=f"consumer does not reference capability: {consumer.reference}",
                        )
                    )
        return CapabilityAuditResult(
            source_id=snapshot.source_id,
            diagnostic_status=DiagnosticStatus.VALID if not gaps else DiagnosticStatus.NOT_VALID,
            checked_capabilities=tuple(requirement.capability_id for requirement in requirements),
            gaps=tuple(gaps),
        )

    @staticmethod
    def _python_symbols(source: str) -> set[str]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return set()
        symbols: set[str] = set()

        def visit(nodes: list[ast.stmt], prefix: str = "") -> None:
            for node in nodes:
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    qualified = f"{prefix}.{node.name}" if prefix else node.name
                    symbols.add(qualified)
                    visit(node.body, qualified)

        visit(tree.body)
        return symbols


class GitSnapshotLoader:
    """Read only admitted capability paths from a worktree or Git commit."""

    _REVISION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")

    def __init__(self, repository_root: str | Path) -> None:
        self.root = Path(repository_root).resolve(strict=True)
        resolved = self._git("rev-parse", "--show-toplevel").strip()
        if Path(resolved).resolve(strict=True) != self.root:
            raise ValueError("repository_root must be the physical Git root")

    def load(
        self,
        requirements: tuple[CapabilityRequirement, ...],
        revision: str | None = None,
    ) -> RepositorySnapshot:
        paths = sorted(
            {producer.path for requirement in requirements for producer in requirement.producers}
            | {consumer.path for requirement in requirements for consumer in requirement.consumers}
        )
        if revision is None:
            source_id = f"worktree:{self._git('rev-parse', 'HEAD').strip()}"
            files = {path: content for path in paths if (content := self._read_worktree(path)) is not None}
        else:
            if self._REVISION.fullmatch(revision) is None:
                raise ValueError("invalid Git revision")
            commit = self._git("rev-parse", "--verify", f"{revision}^{{commit}}").strip()
            source_id = f"git:{commit}"
            files = {path: content for path in paths if (content := self._read_revision(commit, path)) is not None}
        return RepositorySnapshot(source_id=source_id, files=files)

    def _read_worktree(self, relative_path: str) -> str | None:
        path = self._safe_path(relative_path)
        if not path.is_file() or path.is_symlink():
            return None
        return path.read_text(encoding="utf-8")

    def _read_revision(self, commit: str, relative_path: str) -> str | None:
        self._safe_path(relative_path)
        result = subprocess.run(
            ["git", "-C", str(self.root), "show", f"{commit}:{relative_path}"],
            capture_output=True,
            check=False,
            timeout=20,
        )
        if result.returncode != 0:
            return None
        return result.stdout.decode("utf-8")

    def _safe_path(self, relative_path: str) -> Path:
        candidate = (self.root / relative_path).resolve(strict=False)
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"capability path escapes repository: {relative_path}") from exc
        return candidate

    def _git(self, *arguments: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.root), *arguments],
            capture_output=True,
            check=False,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            raise ValueError(result.stderr.strip() or "Git command failed")
        return result.stdout


def structural_capability_requirements() -> tuple[CapabilityRequirement, ...]:
    """Accepted historical capability set for forward and backward audits."""
    return (
        CapabilityRequirement(
            capability_id="gap_analysis_owner",
            producers=(
                CapabilityProducer(
                    path="agent/gap_analysis.py",
                    symbols=("GapAnalyzer", "GapAnalyzer.analyze"),
                ),
            ),
            consumers=(CapabilityConsumer(path="agent/runtime/host_gap_analyzer.py", reference="GapAnalyzer"),),
        ),
        CapabilityRequirement(
            capability_id="reference_closure",
            producers=(
                CapabilityProducer(path="agent/contracts/validation/structural.py", symbols=("reference_gaps",)),
            ),
            consumers=(CapabilityConsumer(path="agent/gap_analysis.py", reference="reference_gaps"),),
        ),
        CapabilityRequirement(
            capability_id="execution_trace",
            producers=(CapabilityProducer(path="agent/contracts/validation/structural.py", symbols=("trace_gaps",)),),
            consumers=(CapabilityConsumer(path="agent/gap_analysis.py", reference="trace_gaps"),),
        ),
        CapabilityRequirement(
            capability_id="concern_matrix",
            producers=(CapabilityProducer(path="agent/contracts/validation/structural.py", symbols=("concern_gaps",)),),
            consumers=(CapabilityConsumer(path="agent/gap_analysis.py", reference="concern_gaps"),),
        ),
        CapabilityRequirement(
            capability_id="historical_backtest",
            producers=(CapabilityProducer(path="agent/gap_analysis.py", symbols=("GapAnalyzer._run_backtests",)),),
        ),
        CapabilityRequirement(
            capability_id="walking_skeleton",
            producers=(
                CapabilityProducer(
                    path="agent/runtime/host_gap_analyzer.py",
                    symbols=("HostGapAnalyzer._run_skeleton",),
                ),
            ),
        ),
        CapabilityRequirement(
            capability_id="tool_registry",
            producers=(
                CapabilityProducer(
                    path="agent/runtime/tool_registry.py",
                    symbols=("pin_tool_registry", "load_pinned_tool_registry"),
                ),
            ),
        ),
        CapabilityRequirement(
            capability_id="registered_command_resolver",
            producers=(CapabilityProducer(path="agent/contracts/tool_registry.py", symbols=("resolve_invocation",)),),
            consumers=(
                CapabilityConsumer(path="agent/contracts/validation/structural.py", reference="resolve_invocation"),
            ),
        ),
        CapabilityRequirement(
            capability_id="sandbox_profile_registry",
            producers=(
                CapabilityProducer(
                    path="agent/contracts/tool_registry.py",
                    symbols=("SandboxProfile", "ToolRegistrySnapshot"),
                ),
            ),
        ),
        CapabilityRequirement(
            capability_id="scanner_check_registry",
            producers=(
                CapabilityProducer(
                    path="agent/runtime/scanner_check_registry.py",
                    symbols=("ScannerCheckRegistry",),
                ),
            ),
        ),
        CapabilityRequirement(
            capability_id="runtime_root_registry",
            producers=(
                CapabilityProducer(
                    path="agent/runtime/runtime_root_registry.py",
                    symbols=("RuntimeRootRegistry",),
                ),
            ),
        ),
        CapabilityRequirement(
            capability_id="recovery_readiness",
            producers=(
                CapabilityProducer(
                    path="agent/runtime/recovery_readiness.py",
                    symbols=("RecoveryReadiness",),
                ),
            ),
            consumers=(
                CapabilityConsumer(
                    path="agent/runtime/build_admission.py",
                    reference="recovery_readiness_ref",
                ),
            ),
        ),
        CapabilityRequirement(
            capability_id="task_batch_wave",
            producers=(
                CapabilityProducer(
                    path="agent/contracts/build_schedule.py",
                    symbols=("BuildTask", "BuildBatch", "BuildWave"),
                ),
            ),
        ),
        CapabilityRequirement(
            capability_id="move_atomicity",
            producers=(CapabilityProducer(path="agent/runtime/effect_executor.py", symbols=("EffectExecutor",)),),
            consumers=(CapabilityConsumer(path="agent/runtime/effect_executor.py", reference='action_kind == "move"'),),
        ),
        CapabilityRequirement(
            capability_id="catalog_lineage",
            producers=(CapabilityProducer(path="agent/research_catalog.py", symbols=("CatalogLineage",)),),
        ),
        CapabilityRequirement(
            capability_id="research_catalog_contract",
            producers=(
                CapabilityProducer(
                    path="agent/research_catalog.py",
                    symbols=("CatalogSample", "ResearchCatalog"),
                ),
            ),
        ),
        CapabilityRequirement(
            capability_id="wave_preimage_pinning",
            producers=(
                CapabilityProducer(path="agent/contracts/build_schedule.py", symbols=("BuildWave",)),
                CapabilityProducer(
                    path="agent/runtime/effect_executor.py",
                    symbols=("EffectExecutor.execute_admitted",),
                ),
            ),
            consumers=(
                CapabilityConsumer(
                    path="agent/runtime/effect_executor.py",
                    reference="expected_source_digest",
                ),
            ),
        ),
    )


def audit_repository(repository_root: str | Path, revision: str | None = None) -> CapabilityAuditResult:
    """Audit current or historical source using the accepted capability set."""
    requirements = structural_capability_requirements()
    snapshot = GitSnapshotLoader(repository_root).load(requirements, revision)
    return MissingCapabilityAnalyzer().analyze(snapshot, requirements)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit OneShot structural capabilities")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--ref", dest="revision")
    args = parser.parse_args(argv)
    result = audit_repository(args.repo, args.revision)
    print(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0 if result.diagnostic_status is DiagnosticStatus.VALID else 1


if __name__ == "__main__":
    raise SystemExit(main())
