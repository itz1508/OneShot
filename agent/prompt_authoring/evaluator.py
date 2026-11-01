"""Prompt evaluator — the nine axes from the spec.

Pluggable: each axis is a `Callable[[PromptDefinition, PromptFixture],
CheckResult]`. The orchestrator runs every registered axis on every
fixture and returns a single `EvaluationReceipt` summarising the
result. The receipt is immutable and append-only — callers hand it to
the `PromptStore` as evidence; the store never recomputes the
receipt.

Axes (verbatim from the spec):

1. Instruction compliance
2. Input / output contract compliance
3. Evidence fidelity and traceability
4. Unknown and uncertainty preservation
5. Responsibility-boundary compliance
6. Tool-selection accuracy
7. Recovery and failure behaviour
8. Downstream artifact usability
9. Regression against the accepted prompt

Design rules:
  * Each axis returns `CheckResult(axis, status, evidence)`. Status is
    `pass | fail | not_applicable | not_run`.
  * The orchestrator REFUSES to infer success from schema compliance
    alone — a prompt that passes axis 2 but fails any of axes 3..9 is
    reported BLOCKED, not EVALUATED.
  * Fixture.kind primarily exercises one axis; the orchestrator does
    not short-circuit the other axes just because kind=="invalid".
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent.prompt_authoring.fixtures import (
    PromptFixture,
    PromptFixtureKind,
)
from agent.prompt_authoring.types import PromptDefinition, PromptStatus

# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------


class CheckOutcome(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"
    NOT_RUN = "not_run"


class CheckResult(BaseModel):
    """Outcome of ONE evaluator axis against ONE fixture."""

    model_config = ConfigDict(extra="forbid")

    axis: str = Field(min_length=1)
    fixture: str = Field(min_length=1)
    status: CheckOutcome
    evidence: str = ""
    details: dict[str, Any] = Field(default_factory=dict)


class EvaluationReceipt(BaseModel):
    """Immutable receipt the evaluator emits per prompt revision.

    `status` is the aggregate rule (see `_aggregate_status`): any FAIL
    on axes 1..9 collapses the whole receipt to BLOCKED; a receipt
    with all passes (and at least one fixture per axis) is EVALUATED;
    anything else is UNEVALUATED. The receipt is NEVER ACTIVE —
    activation is an authorized-owner step owned by `PromptStore`.
    """

    model_config = ConfigDict(extra="forbid")

    prompt_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    content_digest: str = Field(min_length=1)
    fixtures_executed: list[str] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    status: PromptStatus
    receipt_digest: str = Field(min_length=1)
    failures_by_axis: dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# PromptEvaluator
# ---------------------------------------------------------------------------


AxisFn = Callable[[PromptDefinition, PromptFixture], CheckResult]


class PromptEvaluator:
    """Runs the nine axes against a prompt + fixture set."""

    AXES: tuple[str, ...] = (
        "instruction_compliance",
        "io_contract_compliance",
        "evidence_fidelity",
        "unknown_preservation",
        "responsibility_boundary",
        "tool_selection_accuracy",
        "recovery_failure_behaviour",
        "downstream_usability",
        "accepted_regression",
    )

    def __init__(self, axes: dict[str, AxisFn] | None = None) -> None:
        self._axes: dict[str, AxisFn] = (
            axes if axes is not None else _default_axes()
        )
        # Preserve declared order.
        self._order: list[str] = list(self.AXES)
        for name in self._axes:
            if name not in self._order:
                self._order.append(name)

    def register_axis(self, name: str, fn: AxisFn) -> None:
        self._axes[name] = fn
        if name not in self._order:
            self._order.append(name)

    def evaluate(
        self,
        prompt: PromptDefinition,
        fixtures: list[PromptFixture],
    ) -> EvaluationReceipt:
        checks: list[CheckResult] = []
        for fixture in fixtures:
            for axis_name in self._order:
                fn = self._axes.get(axis_name)
                if fn is None:
                    continue
                try:
                    result = fn(prompt, fixture)
                except Exception as exc:  # noqa: BLE001 - evaluator must not crash
                    result = CheckResult(
                        axis=axis_name,
                        fixture=fixture.name,
                        status=CheckOutcome.FAIL,
                        evidence=f"{type(exc).__name__}: {exc}",
                        details={"error": True},
                    )
                checks.append(result)

        failures_by_axis: dict[str, int] = {}
        for c in checks:
            if c.status == CheckOutcome.FAIL:
                failures_by_axis[c.axis] = failures_by_axis.get(c.axis, 0) + 1

        status = _aggregate_status(checks, self._order)
        canonical = json.dumps(
            {
                "prompt_id": prompt.prompt_id,
                "revision": prompt.revision,
                "content_digest": prompt.content_digest,
                "checks": [c.model_dump() for c in checks],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        receipt_digest = hashlib.sha256(canonical).hexdigest()

        return EvaluationReceipt(
            prompt_id=prompt.prompt_id,
            revision=prompt.revision,
            content_digest=prompt.content_digest,
            fixtures_executed=[f.name for f in fixtures],
            checks=checks,
            status=status,
            receipt_digest=receipt_digest,
            failures_by_axis=failures_by_axis,
        )


# ---------------------------------------------------------------------------
# Aggregate status rule
# ---------------------------------------------------------------------------


def _aggregate_status(
    checks: list[CheckResult], axis_order: list[str]
) -> PromptStatus:
    if not checks:
        return PromptStatus.UNEVALUATED
    # Any single FAIL on ANY axis collapses the receipt — the spec is
    # explicit that evaluation does not infer success from schema
    # compliance alone.
    if any(c.status == CheckOutcome.FAIL for c in checks):
        return PromptStatus.BLOCKED
    # If any axis was NEVER executed (no PASS, no FAIL, no NA), the
    # receipt is UNEVALUATED.
    executed_axes = {c.axis for c in checks if c.status != CheckOutcome.NOT_RUN}
    missing = [ax for ax in axis_order if ax not in executed_axes]
    if missing:
        return PromptStatus.UNEVALUATED
    return PromptStatus.EVALUATED


# ---------------------------------------------------------------------------
# Default axes
# ---------------------------------------------------------------------------
#
# Each axis is a deterministic, side-effect-free check that operates
# purely on `(prompt, fixture)`. These are DEFAULT axes — callers may
# plug in richer axes (e.g. one that runs a live model) via
# `PromptEvaluator.register_axis`. The defaults establish the baseline
# contract AND exercise every axis in the test suite without network
# dependencies.


def _default_axes() -> dict[str, AxisFn]:
    return {
        "instruction_compliance": _instruction_compliance,
        "io_contract_compliance": _io_contract_compliance,
        "evidence_fidelity": _evidence_fidelity,
        "unknown_preservation": _unknown_preservation,
        "responsibility_boundary": _responsibility_boundary,
        "tool_selection_accuracy": _tool_selection_accuracy,
        "recovery_failure_behaviour": _recovery_failure_behaviour,
        "downstream_usability": _downstream_usability,
        "accepted_regression": _accepted_regression,
    }


def _instruction_compliance(
    prompt: PromptDefinition, fixture: PromptFixture
) -> CheckResult:
    present = len(prompt.stable_instructions) >= 1
    return CheckResult(
        axis="instruction_compliance",
        fixture=fixture.name,
        status=CheckOutcome.PASS if present else CheckOutcome.FAIL,
        evidence=(
            f"stable_instructions count = {len(prompt.stable_instructions)}"
        ),
    )


def _io_contract_compliance(
    prompt: PromptDefinition, fixture: PromptFixture
) -> CheckResult:
    # The fixture's input keys must map onto the prompt's declared
    # runtime input names (ignoring optional inputs). The fixture's
    # expected / expected_rejection must be non-null for its kind.
    required = {ri.name for ri in prompt.runtime_inputs if ri.required}
    missing = sorted(required - set(fixture.input.keys()))
    expected_ok = (
        fixture.expected is not None
        if fixture.kind in {PromptFixtureKind.VALID, PromptFixtureKind.RECOVERY}
        else fixture.expected_rejection is not None
    )
    status = (
        CheckOutcome.PASS
        if not missing and expected_ok
        else CheckOutcome.FAIL
    )
    return CheckResult(
        axis="io_contract_compliance",
        fixture=fixture.name,
        status=status,
        evidence=f"missing_required_inputs={missing}; expected_ok={expected_ok}",
    )


def _evidence_fidelity(
    prompt: PromptDefinition, fixture: PromptFixture
) -> CheckResult:
    # Every fixture must carry an independently-authored oracle (per
    # G01/G03). A missing oracle is an evidence-fidelity failure.
    status = (
        CheckOutcome.PASS if fixture.oracle.strip() else CheckOutcome.FAIL
    )
    return CheckResult(
        axis="evidence_fidelity",
        fixture=fixture.name,
        status=status,
        evidence=f"oracle={fixture.oracle!r}",
    )


def _unknown_preservation(
    prompt: PromptDefinition, fixture: PromptFixture
) -> CheckResult:
    # The prompt must say something about unknowns in either stable
    # instructions, evaluation rules, or recovery behaviour. A silent
    # prompt is an unknown-preservation failure.
    joined = " ".join(prompt.stable_instructions + prompt.evaluation_rules
                      + [prompt.recovery_behavior]).lower()
    keywords = ("unknown", "uncertain", "not_checked", "unsupported", "blocked")
    status = (
        CheckOutcome.PASS
        if any(k in joined for k in keywords)
        else CheckOutcome.FAIL
    )
    return CheckResult(
        axis="unknown_preservation",
        fixture=fixture.name,
        status=status,
        evidence=f"keyword_hits={[k for k in keywords if k in joined]}",
    )


def _responsibility_boundary(
    prompt: PromptDefinition, fixture: PromptFixture
) -> CheckResult:
    # The prompt owner must match the stage. A `research` stage prompt
    # owned by `provider_adapter` is a boundary violation.
    expected_owner_kind = {
        "research": "prompt_authoring",
        "plan": "prompt_authoring",
        "build": "prompt_authoring",
        "discovery": "audit_discovery",
        "handoff": "main_agent",
        "provider_adapter": "provider_adapter",
    }
    want = expected_owner_kind.get(prompt.stage.value)
    # An immutable historical prompt may contain the former role identifier.
    # Normalize at evaluation only, preserving its original signed digest.
    actual_kind = (
        "audit_discovery"
        if prompt.owner.kind == "builder_discovery"
        else prompt.owner.kind
    )
    ok = want is None or actual_kind == want
    return CheckResult(
        axis="responsibility_boundary",
        fixture=fixture.name,
        status=CheckOutcome.PASS if ok else CheckOutcome.FAIL,
        evidence=f"stage={prompt.stage.value} owner_kind={actual_kind}",
    )


def _tool_selection_accuracy(
    prompt: PromptDefinition, fixture: PromptFixture
) -> CheckResult:
    # Prompt Authoring never names specific vendors — that would be a
    # provider leak. Any mention of 'openai', 'anthropic', etc. in
    # stable_instructions is a boundary violation.
    joined = " ".join(prompt.stable_instructions).lower()
    forbidden = ("openai", "anthropic", "claude", "gpt-", "together.xyz")
    hits = [k for k in forbidden if k in joined]
    status = CheckOutcome.PASS if not hits else CheckOutcome.FAIL
    return CheckResult(
        axis="tool_selection_accuracy",
        fixture=fixture.name,
        status=status,
        evidence=f"vendor_mentions={hits}",
    )


def _recovery_failure_behaviour(
    prompt: PromptDefinition, fixture: PromptFixture
) -> CheckResult:
    status = (
        CheckOutcome.PASS
        if prompt.recovery_behavior.strip()
        else CheckOutcome.FAIL
    )
    return CheckResult(
        axis="recovery_failure_behaviour",
        fixture=fixture.name,
        status=status,
        evidence=f"recovery_behavior_length={len(prompt.recovery_behavior)}",
    )


def _downstream_usability(
    prompt: PromptDefinition, fixture: PromptFixture
) -> CheckResult:
    oc = prompt.output_contract or {}
    status = (
        CheckOutcome.PASS
        if ("type" in oc or "properties" in oc or "$ref" in oc)
        else CheckOutcome.FAIL
    )
    return CheckResult(
        axis="downstream_usability",
        fixture=fixture.name,
        status=status,
        evidence=f"output_contract_keys={sorted(oc.keys())}",
    )


def _accepted_regression(
    prompt: PromptDefinition, fixture: PromptFixture
) -> CheckResult:
    # First revisions have nothing to regress against; the axis is NA.
    # Later revisions must supersede the prior one (we don't look up
    # the prior content here — the store does that at activation time).
    if prompt.revision == 1:
        return CheckResult(
            axis="accepted_regression",
            fixture=fixture.name,
            status=CheckOutcome.NOT_APPLICABLE,
            evidence="revision=1 — nothing to regress against",
        )
    status = (
        CheckOutcome.PASS if prompt.supersedes else CheckOutcome.FAIL
    )
    return CheckResult(
        axis="accepted_regression",
        fixture=fixture.name,
        status=status,
        evidence=f"supersedes={prompt.supersedes!r}",
    )
