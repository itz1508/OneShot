"""Cross-stage validation: lineage, coverage, and acyclicity checks."""

from __future__ import annotations

from collections import defaultdict, deque

from agent.contracts.audit_discovery import AuditDiscoveryPackage
from agent.contracts.planning import BuildSpecification
from agent.contracts.research import AuthorizationStatus, ResearchRecord
from agent.contracts.tool_registry import ToolRegistrySnapshot
from agent.contracts.validation.structural import tool_invocation_gaps


def normalize_relative_path(value: str) -> str:
    """Normalize a repository-relative path and reject traversal/escape."""
    candidate = value.replace("\\", "/")
    while candidate.startswith("./"):
        candidate = candidate[2:]
    if not candidate or candidate.startswith("/"):
        raise ValueError(f"Unsafe repository path: {value}")
    parts = candidate.split("/")
    if ".." in parts:
        raise ValueError(f"Unsafe repository path: {value}")
    return candidate


def validate_audit_lineage(research: ResearchRecord, audit: AuditDiscoveryPackage) -> None:
    """Validate that audit assessments and code intents align with research."""
    accepted = {
        r.requirement_id for r in research.requirements if r.authorization_status is AuthorizationStatus.GRANTED
    }
    assessed = {a.requirement_id for a in audit.assessments}
    if accepted != assessed:
        raise ValueError(f"Audit assessment coverage mismatch: expected {sorted(accepted)}, got {sorted(assessed)}")
    criteria = {c.criterion_id for c in research.acceptance_criteria}
    findings = {f.finding_id for f in audit.findings}
    for intent in audit.code_intents:
        if not set(intent.requirement_ids) <= accepted:
            raise ValueError(f"{intent.intent_id} references unknown or unaccepted requirement")
        if not set(intent.acceptance_criteria_ids) <= criteria:
            raise ValueError(f"{intent.intent_id} references unknown acceptance criterion")
        if not set(intent.finding_ids) <= findings:
            raise ValueError(f"{intent.intent_id} references unknown finding")
        verified = {normalize_relative_path(p) for p in intent.verified_paths}
        candidate_paths = getattr(intent, "candidate_paths", ())
        candidates = {normalize_relative_path(p) for p in candidate_paths}
        if verified & candidates:
            raise ValueError(f"{intent.intent_id} overlaps verified and candidate paths")


def _acyclic(nodes: set[str], edges: dict[str, list[str]], label: str) -> None:
    """Check that a dependency graph is acyclic using topological sort."""
    incoming = {n: 0 for n in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for node, deps in edges.items():
        for dep in deps:
            if dep not in nodes:
                raise ValueError(f"Unknown {label} dependency {dep}")
            incoming[node] += 1
            outgoing[dep].append(node)
    queue = deque(n for n, count in incoming.items() if count == 0)
    seen = 0
    while queue:
        node = queue.popleft()
        seen += 1
        for child in outgoing[node]:
            incoming[child] -= 1
            if incoming[child] == 0:
                queue.append(child)
    if seen != len(nodes):
        raise ValueError(f"{label} dependency cycle")


def validate_build_specification(
    spec: BuildSpecification,
    research: ResearchRecord,
    audit: AuditDiscoveryPackage,
    tool_registry: ToolRegistrySnapshot | None = None,
) -> None:
    """Validate requirement coverage AND executable tool provenance before freeze."""
    accepted = {
        r.requirement_id for r in research.requirements if r.authorization_status is AuthorizationStatus.GRANTED
    }
    coverage = {c.requirement_id for c in spec.requirement_coverage}
    if not coverage:
        raise ValueError("BuildSpecification must have requirement coverage")
    if coverage != accepted:
        missing = sorted(accepted - coverage)
        extra = sorted(coverage - accepted)
        raise ValueError(f"Requirement coverage mismatch: missing={missing}, extra={extra}")
    # Validate action dependency graph is acyclic
    action_ids = {a.action_id for a in spec.actions}
    _acyclic(action_ids, {a.action_id: list(a.depends_on) for a in spec.actions}, "action")

    # Validate phase dependency graph is acyclic
    phase_ids = {p.phase_id for p in spec.phases}
    if phase_ids:
        _acyclic(phase_ids, {p.phase_id: list(p.depends_on) for p in spec.phases}, "phase")

    # Validate action paths are safe
    for action in spec.actions:
        for attr in ("source_path", "target_path"):
            path = getattr(action, attr, None)
            if path:
                normalize_relative_path(path)

    tool_errors = tool_invocation_gaps(spec, tool_registry)
    if tool_errors:
        raise ValueError("BuildSpecification tool provenance failed: " + "; ".join(tool_errors))
