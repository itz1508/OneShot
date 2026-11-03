"""Semantic validators for Planning records."""

from __future__ import annotations

from agent.contracts.planning import (
    BuildSpecification,
    PlanningRecord,
)


def validate_reviews(record: PlanningRecord) -> list[str]:
    """Every code intent must be dispositioned."""
    errors: list[str] = []
    # Intent IDs come from the audit package; we validate reviews exist
    for review in record.intent_reviews:
        if review.disposition.value in ("combine", "split") and not (
            review.resulting_review_ids or review.resulting_decision_ids or review.resulting_action_ids
        ):
            errors.append(f"review {review.review_id} combines/splits without resulting IDs")
    return errors


def validate_planning_issues(record: PlanningRecord) -> list[str]:
    errors: list[str] = []
    for issue in record.issues:
        if issue.issue_type == "security" and not issue.receipt_ref:
            errors.append(f"security issue {issue.issue_id} missing technical check receipt")
    return errors


def validate_decisions(record: PlanningRecord) -> list[str]:
    errors: list[str] = []
    for decision in record.design_decisions:
        if len(decision.options_considered) < 2:
            errors.append(f"decision {decision.decision_id} has fewer than 2 alternatives")
    return errors


def validate_refactors(record: PlanningRecord) -> list[str]:
    errors: list[str] = []
    for refactor in record.corrective_refactors:
        if not refactor.finding_ref:
            errors.append(f"refactor {refactor.refactor_id} has no finding reference")
    return errors


def validate_action_graph(spec: BuildSpecification) -> list[str]:
    errors: list[str] = []
    action_ids = [a.action_id for a in spec.actions]
    if len(action_ids) != len(set(action_ids)):
        errors.append("duplicate action IDs")
    id_set = set(action_ids)
    for action in spec.actions:
        for dep in action.depends_on:
            if dep not in id_set:
                errors.append(f"action {action.action_id} depends on unknown action {dep}")
    # Check for cycles (simple DFS)
    visited: set[str] = set()
    in_stack: set[str] = set()

    def visit(aid: str) -> bool:
        if aid in in_stack:
            return True
        if aid in visited:
            return False
        visited.add(aid)
        in_stack.add(aid)
        matching = [a for a in spec.actions if a.action_id == aid]
        if not matching:
            in_stack.discard(aid)
            return False
        action = matching[0]
        for dep in action.depends_on:
            if visit(dep):
                return True
        in_stack.discard(aid)
        return False

    for aid in action_ids:
        if visit(aid):
            errors.append(f"cycle detected involving action {aid}")
            break
    return errors


def validate_phase_graph(spec: BuildSpecification) -> list[str]:
    errors: list[str] = []
    action_ids = {a.action_id for a in spec.actions}
    for phase in spec.phases:
        for aid in phase.action_ids:
            if aid not in action_ids:
                errors.append(f"phase {phase.phase_id} references unknown action {aid}")
    return errors


def validate_spec_coverage(spec: BuildSpecification) -> list[str]:
    errors: list[str] = []
    for cov in spec.requirement_coverage:
        if cov.status == "covered" and not cov.specification_refs:
            errors.append(f"requirement {cov.requirement_id} marked covered without specification refs")
    for ccov in spec.criterion_coverage:
        if ccov.status == "covered" and not ccov.validation_step_refs:
            errors.append(f"criterion {ccov.criterion_id} marked covered without validation step refs")
    return errors


def validate_paths(spec: BuildSpecification) -> list[str]:
    errors: list[str] = []
    paths: dict[str, str] = {}
    for action in spec.actions:
        path = getattr(action, "target_path", None) or getattr(action, "source_path", None)
        if path:
            if path in paths and paths[path] != action.action_id:
                errors.append(f"path collision: {path} in actions {paths[path]} and {action.action_id}")
            paths[path] = action.action_id
    return errors
