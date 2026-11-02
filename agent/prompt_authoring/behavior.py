"""Behavior-based evaluation (M3) — grade ObservedOutput against golden evidence.

Reviewer directive 3:
  'Executable fixtures. Use ScriptedAdapter to verify predictable behavior,
   but keep independently authored expected results separate from recorded
   model responses. Test missing, conflicting, and malicious evidence.'

Design pins:

* Behavior checks run AFTER PromptEvaluator's structural axes. A prompt that
  fails structural pre-flight never costs a provider call. (The runner's
  caller is responsible for the ordering.)

* The GOLDEN evidence is independently authored and loaded from a separate
  path — `GoldenEvidence` — so a test cannot accidentally let the recorded
  provider output grade itself.

* Four behavior checks, mapped 1:1 onto the four reviewer-named concerns:

      io_contract_compliance_behavior
         Observed output content must parse as JSON matching
         `prompt.output_contract` (JSON Schema with jsonschema when the
         library is installed; fall back to a shape check otherwise).

      evidence_fidelity_behavior
         Observed output must not reference evidence IDs that are not in
         the golden evidence list. Protects against the "LLM invented a
         source" failure mode (reviewer-named 'malicious evidence').

      unknown_preservation_behavior
         For BLOCKED-kind fixtures the output must declare the refusal
         keyword expected by `fixture.expected_rejection`. A silent answer
         is a FAIL even if it conforms to the schema.

      recovery_failure_behaviour_behavior
         For RECOVERY-kind fixtures the output must contain the declared
         recovery marker from `fixture.expected`. A silent 'stop' is a
         FAIL even if the content is well-formed.

* The checks DO NOT mutate the ObservedOutput, the prompt, or the fixture.
  They emit `CheckResult` records that compose into an `EvaluationReceipt`-
  shaped `BehaviorReceipt` so downstream code (PromptStore gating) can hold
  the single-source-of-truth digest.
"""
from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent.prompt_authoring.evaluator import CheckOutcome, CheckResult
from agent.prompt_authoring.fixtures import PromptFixture, PromptFixtureKind
from agent.prompt_authoring.runner import ObservedOutput
from agent.prompt_authoring.types import PromptDefinition


class GoldenEvidence(BaseModel):
    """Independently authored expected result for a fixture (M3 contract).

    Loaded from `tests/_support/golden/<prompt_id>-<revision>/<fixture>.json`
    OR constructed inline by a test. SEPARATE from any recorded model
    response — the recording lives in `tests/_support/recordings/`.
    """

    model_config = ConfigDict(extra="forbid")

    fixture_name: str = Field(min_length=1)
    # The authoritative list of evidence ids a conformant answer may cite.
    # An ObservedOutput that cites an id not in this list is grading-FAIL.
    allowed_evidence_ids: list[str] = Field(default_factory=list)
    # Required substrings or JSON keys the output content must carry.
    required_markers: list[str] = Field(default_factory=list)
    # For BLOCKED fixtures, the refusal marker the output must emit.
    refusal_marker: str | None = None
    # For RECOVERY fixtures, the recovery marker the output must emit.
    recovery_marker: str | None = None


class BehaviorReceipt(BaseModel):
    """Receipt from a BehaviorEvaluator run.

    Deliberately NOT the same shape as EvaluationReceipt: the two sit side
    by side on an evaluated prompt, and PromptStore keeps the two digests
    separate.
    """

    model_config = ConfigDict(extra="forbid")

    prompt_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    content_digest: str = Field(min_length=1)
    fixtures_executed: list[str] = Field(default_factory=list)
    checks: list[CheckResult] = Field(default_factory=list)
    failures_by_axis: dict[str, int] = Field(default_factory=dict)
    overall: CheckOutcome = CheckOutcome.PASS


BEHAVIOR_AXES: tuple[str, ...] = (
    "io_contract_compliance_behavior",
    "evidence_fidelity_behavior",
    "unknown_preservation_behavior",
    "recovery_failure_behaviour_behavior",
)


def _try_parse_json(text: str) -> dict | None:
    try:
        value = json.loads(text)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _schema_shape_check(payload: dict, schema: dict) -> list[str]:
    """Lightweight shape check against a JSON Schema fragment.

    If `jsonschema` is importable we use it; otherwise we fall back to a
    required-key subset check so this module stays import-safe when the
    dev dependency is missing in a stripped-down environment.
    """
    errors: list[str] = []
    try:
        import jsonschema  # type: ignore
    except Exception:
        jsonschema = None  # type: ignore
    if jsonschema is not None:
        try:
            jsonschema.validate(payload, schema)
        except jsonschema.ValidationError as exc:
            errors.append(str(exc))
        return errors
    required = schema.get("required") or []
    for key in required:
        if key not in payload:
            errors.append(f"missing required key: {key!r}")
    return errors


def _check_io_contract(
    prompt: PromptDefinition, fixture: PromptFixture, observed: ObservedOutput
) -> CheckResult:
    axis = "io_contract_compliance_behavior"
    parsed = _try_parse_json(observed.content)
    if parsed is None:
        return CheckResult(
            axis=axis, fixture=fixture.name, status=CheckOutcome.FAIL,
            evidence="observed content does not parse as a JSON object",
        )
    errors = _schema_shape_check(parsed, dict(prompt.output_contract))
    status = CheckOutcome.PASS if not errors else CheckOutcome.FAIL
    return CheckResult(
        axis=axis, fixture=fixture.name, status=status,
        evidence="; ".join(errors) if errors else "schema conformant",
    )


def _collect_evidence_refs(payload: Any) -> list[str]:
    """Walk a parsed payload and pull every evidence_id-shaped string.

    Convention: an `evidence_id` key value or any entry inside an
    `evidence_refs` or `inspected_paths` list is treated as a reference.
    """
    refs: list[str] = []
    def walk(v: Any) -> None:
        if isinstance(v, dict):
            for k, child in v.items():
                if k in ("evidence_id", "ref"):
                    if isinstance(child, str):
                        refs.append(child)
                elif k in ("evidence_refs", "inspected_paths") and isinstance(child, list):
                    for item in child:
                        if isinstance(item, str):
                            refs.append(item)
                        elif isinstance(item, dict):
                            walk(item)
                else:
                    walk(child)
        elif isinstance(v, list):
            for item in v:
                walk(item)
    walk(payload)
    return refs


def _check_evidence_fidelity(
    prompt: PromptDefinition,
    fixture: PromptFixture,
    observed: ObservedOutput,
    golden: GoldenEvidence | None,
) -> CheckResult:
    axis = "evidence_fidelity_behavior"
    parsed = _try_parse_json(observed.content)
    if parsed is None:
        # Already reported by io_contract; skip (NOT_APPLICABLE here).
        return CheckResult(
            axis=axis, fixture=fixture.name, status=CheckOutcome.NOT_APPLICABLE,
            evidence="content not parseable; see io_contract",
        )
    if golden is None or not golden.allowed_evidence_ids:
        return CheckResult(
            axis=axis, fixture=fixture.name, status=CheckOutcome.NOT_APPLICABLE,
            evidence="no golden evidence list declared",
        )
    cited = set(_collect_evidence_refs(parsed))
    allowed = set(golden.allowed_evidence_ids)
    fabricated = sorted(cited - allowed)
    status = CheckOutcome.PASS if not fabricated else CheckOutcome.FAIL
    return CheckResult(
        axis=axis, fixture=fixture.name, status=status,
        evidence=(
            f"cited={sorted(cited)}; fabricated={fabricated}"
            if cited else "no evidence references in output"
        ),
    )


def _check_unknown_preservation(
    prompt: PromptDefinition,
    fixture: PromptFixture,
    observed: ObservedOutput,
    golden: GoldenEvidence | None,
) -> CheckResult:
    axis = "unknown_preservation_behavior"
    if fixture.kind != PromptFixtureKind.BLOCKED:
        return CheckResult(
            axis=axis, fixture=fixture.name, status=CheckOutcome.NOT_APPLICABLE,
            evidence=f"fixture kind={fixture.kind.value}",
        )
    marker = golden.refusal_marker if golden and golden.refusal_marker else None
    if marker is None and fixture.expected_rejection:
        marker = (
            fixture.expected_rejection.get("marker")
            or fixture.expected_rejection.get("reason")
        )
    if marker is None:
        return CheckResult(
            axis=axis, fixture=fixture.name, status=CheckOutcome.NOT_APPLICABLE,
            evidence="no refusal marker declared on fixture or golden",
        )
    status = (
        CheckOutcome.PASS if marker.lower() in observed.content.lower()
        else CheckOutcome.FAIL
    )
    return CheckResult(
        axis=axis, fixture=fixture.name, status=status,
        evidence=f"refusal_marker={marker!r}; present={status is CheckOutcome.PASS}",
    )


def _check_recovery_failure_behaviour(
    prompt: PromptDefinition,
    fixture: PromptFixture,
    observed: ObservedOutput,
    golden: GoldenEvidence | None,
) -> CheckResult:
    axis = "recovery_failure_behaviour_behavior"
    if fixture.kind != PromptFixtureKind.RECOVERY:
        return CheckResult(
            axis=axis, fixture=fixture.name, status=CheckOutcome.NOT_APPLICABLE,
            evidence=f"fixture kind={fixture.kind.value}",
        )
    marker = golden.recovery_marker if golden and golden.recovery_marker else None
    if marker is None and fixture.expected:
        marker = fixture.expected.get("recovery_marker") or fixture.expected.get("marker")
    if marker is None:
        return CheckResult(
            axis=axis, fixture=fixture.name, status=CheckOutcome.NOT_APPLICABLE,
            evidence="no recovery marker declared",
        )
    status = (
        CheckOutcome.PASS if marker.lower() in observed.content.lower()
        else CheckOutcome.FAIL
    )
    return CheckResult(
        axis=axis, fixture=fixture.name, status=status,
        evidence=f"recovery_marker={marker!r}; present={status is CheckOutcome.PASS}",
    )


class BehaviorEvaluator:
    """Grades ObservedOutput for one (prompt, fixture) pair."""

    def grade(
        self,
        prompt: PromptDefinition,
        fixture: PromptFixture,
        observed: ObservedOutput,
        golden: GoldenEvidence | None = None,
    ) -> list[CheckResult]:
        return [
            _check_io_contract(prompt, fixture, observed),
            _check_evidence_fidelity(prompt, fixture, observed, golden),
            _check_unknown_preservation(prompt, fixture, observed, golden),
            _check_recovery_failure_behaviour(prompt, fixture, observed, golden),
        ]

    def grade_many(
        self,
        prompt: PromptDefinition,
        pairs: list[tuple[PromptFixture, ObservedOutput, GoldenEvidence | None]],
    ) -> BehaviorReceipt:
        checks: list[CheckResult] = []
        for fixture, observed, golden in pairs:
            checks.extend(self.grade(prompt, fixture, observed, golden))
        failures: dict[str, int] = {}
        for c in checks:
            if c.status == CheckOutcome.FAIL:
                failures[c.axis] = failures.get(c.axis, 0) + 1
        overall = CheckOutcome.FAIL if failures else CheckOutcome.PASS
        return BehaviorReceipt(
            prompt_id=prompt.prompt_id,
            revision=prompt.revision,
            content_digest=prompt.content_digest,
            fixtures_executed=[f.name for (f, _, _) in pairs],
            checks=checks,
            failures_by_axis=failures,
            overall=overall,
        )


__all__ = [
    "BehaviorEvaluator",
    "BehaviorReceipt",
    "BEHAVIOR_AXES",
    "GoldenEvidence",
]
