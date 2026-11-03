"""Blocking host guardrails for stage input, tool calls, and stage output."""

from __future__ import annotations

from collections.abc import Callable

from agent.contracts.guardrails import GuardrailDecision, GuardrailRequest, GuardrailResult

GuardrailCheck = Callable[[GuardrailRequest], GuardrailResult]


class GuardrailBlocked(RuntimeError):
    """Raised when a guardrail check denies a request."""


def run_blocking_guardrails(request: GuardrailRequest, checks: list[GuardrailCheck]) -> list[GuardrailResult]:
    """Run guardrail checks in order. Stops and raises on first non-allow."""
    results: list[GuardrailResult] = []
    for check in checks:
        result = check(request)
        results.append(result)
        if result.decision is not GuardrailDecision.ALLOW:
            raise GuardrailBlocked(result.reason)
    return results
