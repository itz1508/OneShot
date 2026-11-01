"""Prompt fixtures — valid / invalid / blocked / recovery.

Parallels `tools.fixtures.FixtureRegistry` but speaks the prompt-level
contract: each fixture carries a `kind` indicating which evaluator
axis it primarily exercises, and an independently-authored
`expected` (or `expected_rejection` for the invalid / blocked kinds)
so the evaluator never asks the prompt to grade itself (the G03
contract).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PromptFixtureKind(str, Enum):
    """One of the four fixture kinds the spec enumerates."""

    VALID = "valid"
    INVALID = "invalid"
    BLOCKED = "blocked"
    RECOVERY = "recovery"


class PromptFixture(BaseModel):
    """A single prompt-level fixture case."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    kind: PromptFixtureKind
    description: str = ""
    input: dict[str, Any] = Field(default_factory=dict)
    expected: dict[str, Any] | None = None
    expected_rejection: dict[str, Any] | None = None
    oracle: str = Field(
        default="",
        description=(
            "Pointer to the independent oracle entry (e.g. a case id in "
            "`agent/contracts/oracles.py`). Prompt Authoring NEVER lets the "
            "SUT's own output be the oracle (G01/G03 reopen rules)."
        ),
    )


class PromptFixtureRegistry:
    """Append-only, in-process prompt fixture registry.

    Default registry ships one of each kind so callers that don't
    build their own set still exercise every evaluator axis.
    """

    def __init__(self) -> None:
        self._cases: list[PromptFixture] = []

    def register(self, case: PromptFixture) -> None:
        self._cases.append(case)

    def all(self) -> list[PromptFixture]:
        return list(self._cases)

    def by_kind(self, kind: PromptFixtureKind) -> list[PromptFixture]:
        return [c for c in self._cases if c.kind == kind]

    @classmethod
    def default(cls) -> PromptFixtureRegistry:
        reg = cls()
        reg.register(
            PromptFixture(
                name="valid_minimal",
                kind=PromptFixtureKind.VALID,
                description="Minimal input that must produce a shape-conformant output.",
                input={"objective": "count the characters in 'A😀\\nB'"},
                expected={"status": "ok", "contract_compliant": True},
                oracle="S2.good_case",
            )
        )
        reg.register(
            PromptFixture(
                name="invalid_contract_shape",
                kind=PromptFixtureKind.INVALID,
                description=(
                    "Caller supplies a required field with an unaccepted type; "
                    "the prompt must refuse the request with a shape error, "
                    "not fabricate output."
                ),
                input={"objective": {"wrong": "shape"}},
                expected_rejection={"expected_result": {"status": "error"}},
                oracle="S2.bad_case",
            )
        )
        reg.register(
            PromptFixture(
                name="blocked_unsupported_capability",
                kind=PromptFixtureKind.BLOCKED,
                description=(
                    "Caller asks for a capability the adapter does not advertise. "
                    "The prompt must emit a BLOCKED outcome naming the capability, "
                    "never a silently-downgraded answer."
                ),
                input={"objective": "stream a long rationale"},
                expected_rejection={
                    "exception_type": "UnsupportedCapabilityError"
                },
                oracle="provider.capability_matrix",
            )
        )
        reg.register(
            PromptFixture(
                name="recovery_after_partial_failure",
                kind=PromptFixtureKind.RECOVERY,
                description=(
                    "Caller resumes with a prior partial result; the prompt must "
                    "preserve prior evidence refs and not re-run completed work."
                ),
                input={
                    "objective": "resume task after interrupt",
                    "prior_evidence": ["sha256:deadbeef"],
                },
                expected={"status": "resumed", "preserved_evidence": True},
                oracle="S5.post_effect_crash",
            )
        )
        return reg
