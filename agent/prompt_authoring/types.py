"""Pydantic v2 domain model for Prompt Authoring.

All fields follow the spec verbatim. The schema deliberately reuses
`agent.providers.types.ProviderCapabilities` for `required_capabilities`
so prompts and provider adapters share one vocabulary — a prompt
cannot ask for a capability the registry does not know how to express.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agent.providers.types import ProviderCapabilities

# ---------------------------------------------------------------------------
# Stage + status enums
# ---------------------------------------------------------------------------


class Stage(str, Enum):
    """Stages Prompt Authoring may generate prompts for.

    Research / plan / build are the three OneShot workflow stages.
    `discovery` is the Builder-Discovery read-only role. `handoff`
    covers the Handoff Evaluator. `provider_adapter` covers prompts
    that live inside a provider adapter module (translation prompts).
    """

    RESEARCH = "research"
    PLAN = "plan"
    BUILD = "build"
    DISCOVERY = "discovery"
    HANDOFF = "handoff"
    PROVIDER_ADAPTER = "provider_adapter"


class PromptStatus(str, Enum):
    """Status machine from the spec.

    Allowed transitions:
        UNEVALUATED → EVALUATED | BLOCKED
        BLOCKED     → EVALUATED (after revise+evaluate)
        EVALUATED   → ACTIVE | SUPERSEDED | ARCHIVED
        ACTIVE      → SUPERSEDED | ARCHIVED
        SUPERSEDED  → (terminal)
        ARCHIVED    → (terminal)

    A revision never flips directly from UNEVALUATED to ACTIVE.
    Activation is the authorized-owner path only (see `PromptStore`).
    """

    UNEVALUATED = "unevaluated"
    BLOCKED = "blocked"
    EVALUATED = "evaluated"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


# ---------------------------------------------------------------------------
# Reused Fixture / Owner primitives
# ---------------------------------------------------------------------------


class OwnerRef(BaseModel):
    """Who owns this prompt revision.

    `kind` matches the four ownership boundaries from the spec:
    `prompt_authoring`, `main_agent`, `builder_discovery`,
    `provider_adapter`, `planner`. The identifier is free-form
    (team-slug or user handle) and is NOT a credential.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)
    identifier: str = Field(min_length=1)


class RuntimeInputSpec(BaseModel):
    """Named runtime input the prompt consumes.

    Prompt Authoring picks minimal, non-overlapping runtime variables.
    Each input carries a name, an accepted-meaning blurb, and whether
    the input is required.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    meaning: str = Field(min_length=1)
    required: bool = True


# ---------------------------------------------------------------------------
# PromptSpec (the authoring INPUT)
# ---------------------------------------------------------------------------


class PromptSpec(BaseModel):
    """Authoring input — the four `STAGE_SPECIFICATION`, `TASK_CLASS`,
    `INPUT_CONTRACT`, `OUTPUT_REQUIREMENTS` the spec names.

    Supplied by a caller BEFORE a prompt definition exists. The
    `PromptAuthor` turns a spec into a `PromptDefinition`.
    """

    model_config = ConfigDict(extra="forbid")

    prompt_id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_\-]*$")
    stage: Stage
    owner: OwnerRef
    stage_specification: str = Field(min_length=1)
    task_class: str = Field(min_length=1)
    runtime_inputs: list[RuntimeInputSpec] = Field(default_factory=list)
    output_contract: dict[str, Any] = Field(min_length=1)
    required_capabilities: ProviderCapabilities = Field(default_factory=ProviderCapabilities)
    stable_instructions: list[str] = Field(default_factory=list, min_length=1)
    evaluation_rules: list[str] = Field(default_factory=list)
    recovery_behavior: str = Field(min_length=1)
    fixture_refs: list[str] = Field(default_factory=list)

    @field_validator("output_contract")
    @classmethod
    def output_contract_is_non_empty_schema(cls, v):
        if not isinstance(v, dict) or not v:
            raise ValueError("output_contract must be a non-empty JSON Schema")
        return v


# ---------------------------------------------------------------------------
# PromptDefinition (the authoring OUTPUT, versioned)
# ---------------------------------------------------------------------------


_SHA256_RE = r"^[0-9a-f]{64}$"


class PromptDefinition(BaseModel):
    """Versioned, immutable-once-active prompt definition.

    Field order matches the spec's bullet list.
    `content_digest` is a sha-256 over a canonical serialisation of
    the STABLE fields (prompt_id, revision, stage, owner,
    runtime_inputs, stable_instructions, required_capabilities,
    output_contract, evaluation_rules, recovery_behavior) — fixture
    refs and the evaluation receipt are NOT part of the digest so
    reusing the same prompt against a new fixture set keeps the
    digest stable.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_\-]*$")
    revision: int = Field(ge=1)
    content_digest: str = Field(pattern=_SHA256_RE)

    stage: Stage
    owner: OwnerRef
    runtime_inputs: list[RuntimeInputSpec] = Field(default_factory=list)
    stable_instructions: list[str] = Field(min_length=1)
    required_capabilities: ProviderCapabilities = Field(default_factory=ProviderCapabilities)

    output_contract: dict[str, Any] = Field(min_length=1)
    evaluation_rules: list[str] = Field(default_factory=list)
    recovery_behavior: str = Field(min_length=1)

    fixture_refs: list[str] = Field(default_factory=list)
    evaluation_receipt_ref: str | None = None

    supersedes: str | None = None
    status: PromptStatus = PromptStatus.UNEVALUATED

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("output_contract")
    @classmethod
    def output_contract_is_non_empty_schema(cls, v):
        if not isinstance(v, dict) or not v:
            raise ValueError("output_contract must be a non-empty JSON Schema")
        if "type" not in v and "properties" not in v and "$ref" not in v:
            raise ValueError(
                "output_contract must declare a `type`, `properties`, or `$ref`"
            )
        return v

    @field_validator("stable_instructions")
    @classmethod
    def stable_instructions_non_blank(cls, v):
        if any((not isinstance(s, str)) or (not s.strip()) for s in v):
            raise ValueError("stable_instructions entries must be non-blank strings")
        return v

    @model_validator(mode="after")
    def digest_matches_canonical_payload(self) -> PromptDefinition:
        expected = canonical_content_digest(self)
        if self.content_digest != expected:
            raise ValueError(
                "content_digest mismatch: supplied "
                f"{self.content_digest!r} != recomputed {expected!r}. "
                "A PromptDefinition must carry the sha-256 of its own "
                "canonical stable fields."
            )
        return self

    @model_validator(mode="after")
    def status_shape_rules(self) -> PromptDefinition:
        # supersedes is the back-reference to the PRIOR revision this
        # revision replaces. A revision 1 may NOT carry a supersedes
        # reference (there is no earlier revision to point at).
        if self.supersedes is not None and self.revision < 2:
            raise ValueError(
                "supersedes may only be set on revision >= 2"
            )
        return self


# ---------------------------------------------------------------------------
# Canonical content digest
# ---------------------------------------------------------------------------


_STABLE_FIELDS = (
    "prompt_id",
    "revision",
    "stage",
    "owner",
    "runtime_inputs",
    "stable_instructions",
    "required_capabilities",
    "output_contract",
    "evaluation_rules",
    "recovery_behavior",
    "supersedes",
)


def _coerce_json_safe(value: Any) -> Any:
    """Convert Pydantic models / enums to JSON-safe primitives."""
    from enum import Enum as _Enum

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, _Enum):
        return value.value
    if isinstance(value, list):
        return [_coerce_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_coerce_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _coerce_json_safe(v) for k, v in value.items()}
    return value


def canonical_content_digest(definition: PromptDefinition | dict[str, Any]) -> str:
    """Compute the sha-256 digest the model_validator enforces.

    Exposed as a module-level function so callers (and tests) can
    compute the digest WITHOUT a `PromptDefinition` instance already
    existing — this is what `PromptAuthor.author_candidate` uses to
    seed `content_digest` on construction.
    """

    if isinstance(definition, PromptDefinition):
        payload = definition.model_dump(mode="json")
    else:
        payload = {k: _coerce_json_safe(v) for k, v in definition.items()}
    stable = {k: payload.get(k) for k in _STABLE_FIELDS}
    canonical = json.dumps(stable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
