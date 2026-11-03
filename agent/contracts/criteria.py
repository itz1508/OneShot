"""OneShot criteria contracts extracted from the former models.py monolith.

Keep stage fields and validators compatible; YAML record templates remain intact.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .shared import _SHA256_RE, _is_filled

# ---------------------------------------------------------------------------
# Success Criteria models — referenced by Research, Plan, and Build
# ---------------------------------------------------------------------------


class EvidenceType(str, Enum):
    """Typed evidence categories for Research success criteria."""

    SOURCE_DOCUMENT = "source_document"
    SOURCE_EXCERPT = "source_excerpt"
    OFFICIAL_REFERENCE = "official_reference"
    CROSS_SOURCE_COMPARISON = "cross_source_comparison"
    REPOSITORY_OBSERVATION = "repository_observation"
    COMMAND_RESULT = "command_result"
    TEST_RESULT = "test_result"
    SCHEMA_RESULT = "schema_result"
    FIXTURE_RESULT = "fixture_result"
    HUMAN_OBSERVATION = "human_observation"
    WORK_EVENT = "work_event"


class InsufficientEvidenceDisposition(str, Enum):
    """Three-way disposition when evidence is insufficient for a criterion."""

    RECORD_UNKNOWN = "record_unknown"
    VALIDATE_FIRST = "validate_first"
    BLOCK_HANDOFF = "block_handoff"


class CriterionPriority(str, Enum):
    """Priority level for a Research success criterion."""

    BLOCKING = "blocking"
    MAJOR = "major"
    MINOR = "minor"


class Criterion(BaseModel):
    """Evidence-oriented acceptance criterion anchored to the accepted Input.

    The observable_outcome is a verifiable Research finding or artifact,
    not an implementation result.  This defines the structure referenced by
    RequirementTrace.criterion_ids, Plan.accepted_criterion_ids, and
    Build.criterion_id in validation checks.
    """

    model_config = ConfigDict(extra="allow")

    criterion_id: str
    statement: str = ""
    observable_outcome: str = ""
    priority: CriterionPriority = CriterionPriority.MAJOR
    source_outcome_ids: list[str] = Field(default_factory=list)
    research_question_ids: list[str] = Field(default_factory=list)
    required_evidence_types: list[EvidenceType] = Field(default_factory=list)
    pass_condition: str = ""
    fail_condition: str = ""
    insufficient_evidence_disposition: InsufficientEvidenceDisposition = (
        InsufficientEvidenceDisposition.RECORD_UNKNOWN
    )
    prohibited_outcomes: list[str] = Field(default_factory=list)

    @field_validator("criterion_id", "statement", "observable_outcome")
    @classmethod
    def not_placeholder(cls, v: str) -> str:
        if not _is_filled(v):
            raise ValueError("must be non-empty and not a placeholder")
        return v


class CoverageEntry(BaseModel):
    """Maps an accepted Input outcome to the Research criteria that cover it."""

    model_config = ConfigDict(extra="allow")

    outcome_id: str
    criterion_ids: list[str] = Field(default_factory=list)


class SuccessCriteria(BaseModel):
    """Evidence-oriented acceptance criteria for Research, anchored to the
    accepted Input rather than an implementation Plan.

    Referenced by Research outputs (success_criteria_refs), Plan input
    (accepted_criterion_ids), and Build validation (criterion_id in checks).

    Artifact identity follows the CaseDefinition oracle pattern from
    agent/contracts/oracles.py: content_digest, authority_ref,
    source_revision, and criteria_revision enable the evidence resolver
    to validate the criteria artifact's identity, content digest, and
    schema — not just whether its path exists.
    """

    model_config = ConfigDict(extra="allow")

    schema_version: str = "1.0"
    success_criteria_id: str
    operation_id: str
    input_reference: str  # exact accepted Input revision
    criteria: list[Criterion] = Field(default_factory=list)
    coverage: list[CoverageEntry] = Field(default_factory=list)
    created_at: str | None = None

    # Artifact identity — follows PromptDefinition pattern from
    # agent/prompt_authoring/types.py: content_digest is REQUIRED and
    # automatically validated by a model_validator against the canonical
    # digest of the stable fields. authority_ref and source_revision
    # are optional at model level but required for handoff admission
    # (see validate_success_criteria_artifact).
    content_digest: str = Field(pattern=_SHA256_RE)
    authority_ref: str | None = None
    source_revision: str | None = None
    criteria_revision: int = Field(default=1, ge=1)

    @field_validator("success_criteria_id", "operation_id", "input_reference")
    @classmethod
    def not_placeholder(cls, v: str) -> str:
        if not _is_filled(v):
            raise ValueError("must be non-empty and not a placeholder")
        return v

    @model_validator(mode="after")
    def digest_matches_canonical_payload(self) -> "SuccessCriteria":
        """Automatically validate content_digest against canonical digest.

        Follows PromptDefinition.digest_matches_canonical_payload: the
        digest is checked at construction time, not via an explicit
        method callers might forget to invoke. Raises ValueError if
        content_digest does not match the canonical SHA-256 of the
        stable fields.
        """
        expected = canonical_criteria_digest(self)
        if self.content_digest != expected:
            raise ValueError(
                "content_digest mismatch: supplied "
                f"{self.content_digest!r} != recomputed {expected!r}. "
                "A SuccessCriteria must carry the sha-256 of its own "
                "canonical stable fields. Use canonical_criteria_digest() "
                "to compute the digest before construction."
            )
        return self

    def compute_digest(self) -> str:
        """Compute SHA-256 of canonical JSON encoding of criteria content.

        Convenience wrapper around canonical_criteria_digest() for
        instance callers. Returns the same value that the
        model_validator checks at construction time.
        """
        return canonical_criteria_digest(self)



# ---------------------------------------------------------------------------
# Typed SuccessCriteria artifact validation (Research → Planner handoff)
# ---------------------------------------------------------------------------

# Stable fields included in the canonical digest. Excludes content_digest
# (circular), created_at, and schema_version (metadata, not content).
_CRITERIA_STABLE_FIELDS = (
    "success_criteria_id",
    "operation_id",
    "input_reference",
    "criteria_revision",
    "authority_ref",
    "source_revision",
    "criteria",
    "coverage",
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


def canonical_criteria_digest(
    criteria: SuccessCriteria | dict[str, Any],
) -> str:
    """Compute the sha-256 digest the model_validator enforces.

    Exposed as a module-level function so callers (and tests) can compute
    the digest WITHOUT a SuccessCriteria instance already existing — this
    is what authors use to seed content_digest on construction.

    When given a raw dict, Criterion and CoverageEntry entries are coerced
    through their Pydantic models to fill in default field values, ensuring
    the digest matches what the SuccessCriteria model_validator would
    compute from the fully-constructed model.

    Follows canonical_content_digest from agent/prompt_authoring/types.py.
    """
    if isinstance(criteria, SuccessCriteria):
        payload = criteria.model_dump(mode="json")
    else:
        payload = {k: _coerce_json_safe(v) for k, v in criteria.items()}
        # Coerce Criterion dicts through Pydantic to fill in defaults
        # so the dict-based digest matches the model-based digest.
        if "criteria" in payload:
            payload["criteria"] = [
                Criterion.model_validate(c).model_dump(mode="json")
                if isinstance(c, dict)
                else _coerce_json_safe(c)
                for c in payload["criteria"]
            ]
        if "coverage" in payload:
            payload["coverage"] = [
                CoverageEntry.model_validate(e).model_dump(mode="json")
                if isinstance(e, dict)
                else _coerce_json_safe(e)
                for e in payload["coverage"]
            ]
    stable = {k: payload.get(k) for k in _CRITERIA_STABLE_FIELDS}
    canonical = json.dumps(stable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_success_criteria_artifact(
    content: str | bytes | dict[str, Any],
    *,
    trusted_digest: str | None = None,
    trusted_authority_ref: str | None = None,
) -> list[str]:
    """Typed validation of a resolved SuccessCriteria artifact.

    Called at the Research → Planner handoff boundary AFTER the generic
    evidence_index_resolver confirms the reference resolves and the file
    digest matches. This function performs:

    1. Schema validation — parse content as SuccessCriteria Pydantic model
       (automatic: field types, placeholder rejection, content_digest
       model_validator all run at parse time)
    2. Identity comparison — compare content_digest against a separately
       trusted reference digest (not the artifact's own self-consistency)
    3. Provenance — require valid authority_ref and source_revision
    4. Criterion coverage — check unique criterion IDs, outcome coverage,
       evidence type sufficiency, and blocking dispositions

    Returns a list of error strings (empty = valid). Does NOT modify the
    generic evidence_index_resolver, which remains a multi-type resolver.
    """
    errors: list[str] = []

    # --- 1. Schema validation (Pydantic parse) ---
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    if isinstance(content, str):
        import json as _json

        try:
            data = _json.loads(content)
        except _json.JSONDecodeError as exc:
            return [f"criteria artifact is not valid JSON: {exc}"]
    else:
        data = content

    if not isinstance(data, dict):
        return [f"criteria artifact must be a JSON object, got {type(data).__name__}"]

    try:
        sc = SuccessCriteria.model_validate(data)
    except Exception as exc:
        return [f"criteria artifact failed schema validation: {exc}"]

    # --- 2. Identity comparison against separately trusted reference ---
    if trusted_digest is not None:
        if sc.content_digest != trusted_digest:
            errors.append(
                f"content_digest {sc.content_digest!r} does not match "
                f"trusted reference {trusted_digest!r}"
            )

    # --- 3. Provenance ---
    if not sc.authority_ref or not _is_filled(sc.authority_ref):
        errors.append("authority_ref is required for handoff admission")
    if not sc.source_revision or not _is_filled(sc.source_revision):
        errors.append("source_revision is required for handoff admission")

    # --- 4. Criterion coverage and evidence checks ---
    criterion_ids: list[str] = []
    for c in sc.criteria:
        criterion_ids.append(c.criterion_id)
        if not c.required_evidence_types:
            errors.append(
                f"criterion {c.criterion_id!r}: required_evidence_types is empty"
            )
        if not _is_filled(c.pass_condition):
            errors.append(
                f"criterion {c.criterion_id!r}: pass_condition is empty"
            )
        if not _is_filled(c.fail_condition):
            errors.append(
                f"criterion {c.criterion_id!r}: fail_condition is empty"
            )

    # Unique criterion IDs
    seen: set[str] = set()
    for cid in criterion_ids:
        if cid in seen:
            errors.append(f"duplicate criterion_id {cid!r}")
        seen.add(cid)

    # Coverage: every criterion must be covered by at least one outcome
    covered_ids: set[str] = set()
    for entry in sc.coverage:
        for cid in entry.criterion_ids:
            covered_ids.add(cid)
    for cid in criterion_ids:
        if cid not in covered_ids:
            errors.append(
                f"criterion {cid!r}: not covered by any CoverageEntry"
            )

    # Outcomes referenced in coverage must have at least one criterion
    for entry in sc.coverage:
        if not entry.criterion_ids:
            errors.append(
                f"coverage entry for outcome {entry.outcome_id!r}: "
                "criterion_ids is empty"
            )

    return errors

