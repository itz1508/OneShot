"""Structural gap checks: source closure, effect gates, and stage concerns."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from agent.contracts.planning import BuildSpecification
from agent.contracts.tool_registry import ToolRegistrySnapshot, resolve_invocation

CONCERNS = frozenset(
    {
        "identity",
        "authority",
        "registry",
        "provenance",
        "persistence",
        "recovery",
        "concurrency",
        "pinning",
        "evidence",
        "cleanup",
    }
)


@dataclass(frozen=True)
class ReferenceNeed:
    name: str
    consumer: str


@dataclass(frozen=True)
class SourceDeclaration:
    name: str
    owner: str
    evidence_ref: str
    resolver_ref: str = ""
    resolution_phase: Literal["", "admission", "effect_time"] = ""


@dataclass(frozen=True)
class PersistenceDeclaration:
    output: str
    consumers: frozenset[str] = frozenset()
    terminal: bool = False


@dataclass(frozen=True)
class TraceStep:
    step_id: str
    needs: frozenset[str]
    produces: frozenset[str]
    effect: str | None = None
    gate: str | None = None
    persistence: tuple[PersistenceDeclaration, ...] = ()
    ephemeral_outputs: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ConcernCell:
    stage: str
    concern: str
    status: Literal["covered", "not_applicable"]
    owner: str = ""
    evidence_ref: str = ""
    reason: str = ""


def reference_gaps(
    needs: tuple[ReferenceNeed, ...],
    sources: tuple[SourceDeclaration, ...],
) -> list[str]:
    """Every external reference must have an accountable owner and evidence."""
    defined: set[str] = set()
    errors: list[str] = []
    for source in sources:
        if not source.name or not source.owner or not source.evidence_ref:
            errors.append(f"source {source.name or '<unnamed>'}: missing owner/evidence")
        if source.name in defined:
            errors.append(f"source {source.name}: duplicate producer")
        defined.add(source.name)
    for need in needs:
        if need.name not in defined:
            errors.append(f"{need.consumer}: no producer for {need.name}")
    return errors


def registry_resolution_gaps(
    required_registry_ids: tuple[str, ...],
    sources: tuple[SourceDeclaration, ...],
) -> list[str]:
    """Require one evidenced producer and an effect-time resolver per registry."""
    errors: list[str] = []
    by_name = {source.name: source for source in sources}
    for name in sorted(set(required_registry_ids)):
        source = by_name.get(name)
        if source is None or not source.owner or not source.evidence_ref:
            errors.append(f"registry entry without producer: {name}")
        if source is None or not source.resolver_ref:
            errors.append(f"registry entry without resolver: {name}")
        if source is None or source.resolution_phase != "effect_time":
            errors.append(f"registry entry without effect-time resolver: {name}")
    return errors


def trace_gaps(steps: tuple[TraceStep, ...], external: tuple[SourceDeclaration, ...]) -> list[str]:
    """Validate temporal producer-before-consumer closure and effect gates."""
    errors = reference_gaps((), external)
    available = {item.name for item in external if item.owner and item.evidence_ref}
    positions: dict[str, int] = {}
    for index, step in enumerate(steps):
        if step.step_id in positions:
            errors.append(f"{step.step_id}: duplicate trace step")
        positions[step.step_id] = index

    for index, step in enumerate(steps):
        for missing in sorted(step.needs - available):
            errors.append(f"{step.step_id}: nothing produces {missing}")
        if step.effect and not step.gate:
            errors.append(f"{step.step_id}: effect {step.effect} has no gate")
        persisted: set[str] = set()
        for declaration in step.persistence:
            output = declaration.output
            if output in persisted:
                errors.append(f"{step.step_id}: duplicate persistence declaration for {output}")
            persisted.add(output)
            if output not in step.produces:
                errors.append(f"{step.step_id}: persists undeclared output {output}")
            if not declaration.consumers and not declaration.terminal:
                errors.append(f"{step.step_id}: persisted output without consumer: {output}")
            for consumer in sorted(declaration.consumers):
                consumer_index = positions.get(consumer)
                if consumer_index is None:
                    errors.append(f"{step.step_id}: unknown consumer {consumer} for {output}")
                elif consumer_index <= index:
                    errors.append(f"{step.step_id}: consumer {consumer} is not after producer for {output}")
                elif output not in steps[consumer_index].needs:
                    errors.append(f"{consumer}: does not consume declared output {output}")
        overlap = persisted & set(step.ephemeral_outputs)
        for output in sorted(overlap):
            errors.append(f"{step.step_id}: output is both persisted and ephemeral: {output}")
        for output in sorted(set(step.ephemeral_outputs) - step.produces):
            errors.append(f"{step.step_id}: undeclared ephemeral output {output}")
        unclassified = step.produces - persisted - step.ephemeral_outputs
        for output in sorted(unclassified):
            errors.append(f"{step.step_id}: output persistence not declared: {output}")
        available.update(step.produces)
    return errors


def concern_gaps(stages: tuple[str, ...], cells: tuple[ConcernCell, ...]) -> list[str]:
    """Coverage matrix is complete only with evidenced owners or reasoned N/A."""
    errors: list[str] = []
    observed: set[tuple[str, str]] = set()
    for cell in cells:
        key = (cell.stage, cell.concern)
        if key in observed:
            errors.append(f"{cell.stage}/{cell.concern}: duplicate coverage")
        observed.add(key)
        if cell.stage not in stages or cell.concern not in CONCERNS:
            errors.append(f"{cell.stage}/{cell.concern}: unknown cell")
        if cell.status == "covered" and (not cell.owner or not cell.evidence_ref):
            errors.append(f"{cell.stage}/{cell.concern}: missing owner/evidence")
        if cell.status == "not_applicable" and not cell.reason:
            errors.append(f"{cell.stage}/{cell.concern}: missing N/A reason")
    for stage in stages:
        for concern in sorted(CONCERNS):
            if (stage, concern) not in observed:
                errors.append(f"{stage}/{concern}: missing coverage")
    return errors


def tool_invocation_gaps(
    spec: BuildSpecification,
    registry: ToolRegistrySnapshot | None,
    *,
    stage: Literal["build", "build_validation"] = "build",
) -> list[str]:
    """No executable verification without a pinned catalog and resolvable tools."""
    pending = [action for action in spec.actions if action.verification_tools]
    if not pending:
        return []
    if registry is None:
        return ["tool registry snapshot required for executable validation"]
    errors: list[str] = []
    profiles_by_action: dict[str, set[str]] = {}
    for action in pending:
        paths = frozenset(
            path
            for path in (getattr(action, "source_path", None), getattr(action, "target_path", None))
            if path is not None
        )
        for invocation in action.verification_tools:
            try:
                resolved = resolve_invocation(registry, invocation, stage, paths)
            except ValueError as exc:
                errors.append(f"{action.action_id}: {exc}")
            else:
                profiles_by_action.setdefault(action.action_id, set()).add(resolved.sandbox_profile_id)
    phases: Mapping[str, tuple[str, ...]] = (
        {phase.phase_id: phase.action_ids for phase in spec.phases}
        if spec.phases
        else {"unphased": tuple(a.action_id for a in spec.actions)}
    )
    for phase_id, ids in phases.items():
        used = set().union(*(profiles_by_action.get(aid, set()) for aid in ids))
        if len(used) > 1:
            errors.append(f"{phase_id}: incompatible sandbox profiles in one execution unit")
    return errors
