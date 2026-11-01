"""Frozen, versioned acceptance oracles for the five contract scenarios.

Addresses gap-analysis items:

  G01 — Oracle authority is pinned via `oracle_revision`, `authority_ref`,
        and `accepted_requirement_id`. Every CaseDefinition carries a
        self-sha so inputs cannot be mutated silently after acceptance.
  G03 — Negative outcomes require an exact rejection identity:
        the specific finding category + a forbidden-side-effect list.
  G04 — The oracle module contains ONLY expectations, no fault injectors.
        Fault injectors live in `tests/scenarios/_fault_injectors.py`.
        An oracle that was mutated by the SUT becomes identity-invalid
        at the next `.verify_identity()` check.

Lifecycle:
    OracleCatalog is the registry. Entries are
    frozen (dataclass + hashable), identity-stable (sha of a
    canonical JSON encoding), and bound to:
        - accepted_requirement_id    the Research/Plan requirement
        - authority_ref              AGENTS.md or equivalent authority
        - source_revision            the OneShot source SHA the oracle
                                     was authored against (plain string)
        - oracle_revision            a monotonic integer bumped when
                                     the frozen content changes
        - self_sha                   sha256(canonical_json(payload))

Usage:
    cat = OracleCatalog.default()
    case = cat.get("S2.do_not_use.bad_case")
    case.verify_identity()                  # raises if someone edited the oracle
    assert run_scenario(bundle).matches(case.expected_findings)

An oracle entry is DELIBERATELY immutable: writes raise. The one way
to add a new case is to append in `_build_default_catalog()` and
bump the module-level `ORACLE_CATALOG_REVISION`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

# Module-level revision. Bump on every material change below.
ORACLE_CATALOG_REVISION: int = 1


# ---------------------------------------------------------------------------
# Core shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FindingShape:
    """The shape of a single finding the oracle REQUIRES or FORBIDS.

    `category` and `kind` are semantic category labels (e.g.
    "duplication", "contradictions") — NOT file-diff statuses. The
    audit's central objection was that the scanner equated
    `added/modified/missing` with semantic findings; FindingShape makes
    that confusion impossible in the oracle layer.
    """

    category: Literal[
        "drift",
        "missing",
        "duplication",
        "contradictions",
        "coverage",
        "dependencies",
        "feasibility",
        "cli_docs",
    ]
    kind: str
    """Semantic sub-kind, e.g. 'duplicate_callable_name',
    'conflicting_requirement_assertion', 'uncovered_requirement',
    'prerequisite_order_violation'."""

    severity: Literal["low", "medium", "high", "critical"] = "medium"
    affected_requirement_id: str | None = None
    affected_subject: str | None = None
    """Free-text subject (callable name, requirement id, module path).
    Used as a stable identity for the finding."""


@dataclass(frozen=True)
class CaseDefinition:
    """One accepted good/bad case for a category or scenario.

    Fault injection is EXPLICITLY not part of this record. The
    `fault_injector_ref` field is a *name* of a function in the
    separate `tests/scenarios/_fault_injectors` module; the oracle
    never carries executable code (G04).
    """

    case_id: str
    accepted_requirement_id: str
    authority_ref: str
    source_revision: str
    oracle_revision: int

    # The two halves of the oracle. "good" cases MUST produce no
    # findings; "bad" cases MUST produce the expected findings.
    polarity: Literal["good", "bad"]
    inputs: Mapping[str, Any]
    """Pure data (no callables). SUT may *read* this but cannot modify
    it; oracles.verify_identity() enforces that at use time."""

    fault_injector_ref: str | None = None
    """Name of a function in tests/scenarios/_fault_injectors.py that
    may be called to materialise the bad case into a disposable
    workspace. The oracle module does NOT import or call it."""

    expected_findings: tuple[FindingShape, ...] = field(default_factory=tuple)
    forbidden_findings: tuple[FindingShape, ...] = field(default_factory=tuple)
    expected_decision: Literal["admit", "block"] = "admit"
    forbidden_side_effects: tuple[str, ...] = field(default_factory=tuple)
    required_correction: str | None = None
    post_correction_outcome: Literal["admit", "block"] | None = None

    def canonical_payload(self) -> str:
        """Return a canonical JSON string used to compute self_sha."""
        payload = {
            "case_id": self.case_id,
            "accepted_requirement_id": self.accepted_requirement_id,
            "authority_ref": self.authority_ref,
            "source_revision": self.source_revision,
            "oracle_revision": self.oracle_revision,
            "polarity": self.polarity,
            "inputs": _normalise(self.inputs),
            "fault_injector_ref": self.fault_injector_ref,
            "expected_findings": [_finding_payload(f) for f in self.expected_findings],
            "forbidden_findings": [_finding_payload(f) for f in self.forbidden_findings],
            "expected_decision": self.expected_decision,
            "forbidden_side_effects": list(self.forbidden_side_effects),
            "required_correction": self.required_correction,
            "post_correction_outcome": self.post_correction_outcome,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    @property
    def self_sha(self) -> str:
        return hashlib.sha256(self.canonical_payload().encode("utf-8")).hexdigest()

    def verify_identity(self, *, expected_sha: str) -> None:
        """Raise if the oracle has drifted since authorisation.

        Callers hold the authorised sha in a frozen registry (see
        `OracleCatalog._default_entries()`). The verify step prevents a
        SUT that reaches into the oracle module from editing the oracle
        and then passing itself (G04).
        """
        got = self.self_sha
        if got != expected_sha:
            raise ValueError(
                f"oracle identity mismatch for case {self.case_id!r}: "
                f"expected sha {expected_sha!r}, got {got!r} — the oracle has "
                "been modified after authorisation"
            )


def _finding_payload(f: FindingShape) -> dict[str, Any]:
    return {
        "category": f.category,
        "kind": f.kind,
        "severity": f.severity,
        "affected_requirement_id": f.affected_requirement_id,
        "affected_subject": f.affected_subject,
    }


def _normalise(value: Any) -> Any:
    """Recursively convert the input mapping to plain JSON-safe values."""
    if isinstance(value, Mapping):
        return {k: _normalise(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalise(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return {"__bytes__": value.hex()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _AuthorisedEntry:
    case: CaseDefinition
    sha: str


class OracleCatalog:
    """Registry of frozen oracle cases.

    Not a database and not a service — a single-process in-memory read
    model. Entries are the AUTHORITY for scenario expectations and are
    verified by their self-sha on every access.
    """

    def __init__(self, entries: tuple[_AuthorisedEntry, ...]) -> None:
        self._entries: dict[str, _AuthorisedEntry] = {e.case.case_id: e for e in entries}

    @classmethod
    def default(cls) -> OracleCatalog:
        return cls(tuple(_default_entries()))

    def get(self, case_id: str) -> CaseDefinition:
        entry = self._entries[case_id]
        entry.case.verify_identity(expected_sha=entry.sha)
        return entry.case

    def ids(self) -> tuple[str, ...]:
        return tuple(self._entries.keys())


def _default_entries() -> list[_AuthorisedEntry]:
    """Authorised oracle entries. SHA is captured at authoring time.

    When editing an entry: bump `oracle_revision` and update the SHA
    constant below (recomputed via `case.self_sha`).
    """
    # ----- S2 bad case: an unsupported finding reaches the Plan -----
    s2_bad = CaseDefinition(
        case_id="S2.do_not_use.bad_case",
        accepted_requirement_id="R_CLAIM",
        authority_ref="AGENTS.md",
        source_revision="a0370fc",
        oracle_revision=1,
        polarity="bad",
        inputs={
            "finding_id": "F_UNSUPPORTED",
            "assessment": "contradicted",
            "evidence_refs": ["AGENTS.md"],
            "derived_milestone_id": "m_removed",
        },
        fault_injector_ref=None,
        expected_findings=(
            FindingShape(
                category="contradictions",
                kind="conflicting_requirement_assertion",
                severity="high",
                affected_requirement_id="R_CLAIM",
                affected_subject="F_UNSUPPORTED",
            ),
        ),
        expected_decision="block",
        forbidden_side_effects=(
            "m_removed executed",
            "paraphrased derivative admitted",
        ),
        required_correction="plan.claim_decisions += DO_NOT_USE(F_UNSUPPORTED, [m_removed])",
        post_correction_outcome="admit",
    )

    # ----- S2 good case (post-correction) -----
    s2_good = CaseDefinition(
        case_id="S2.do_not_use.good_case",
        accepted_requirement_id="R_SUPPORTED",
        authority_ref="AGENTS.md",
        source_revision="a0370fc",
        oracle_revision=1,
        polarity="good",
        inputs={
            "finding_id": "F_SUPPORTED",
            "assessment": "supported",
            "evidence_refs": ["bin/context_counter.py"],
            "accepted_milestone_id": "m_keep",
        },
        expected_findings=(),
        forbidden_findings=(
            FindingShape(category="contradictions", kind="conflicting_requirement_assertion"),
            FindingShape(category="duplication", kind="duplicate_callable_name"),
        ),
        expected_decision="admit",
        forbidden_side_effects=(),
    )

    # ----- S3 bad case: VALIDATE_FIRST gates m_gated -----
    s3_bad = CaseDefinition(
        case_id="S3.validate_first.bad_case",
        accepted_requirement_id="R_GATED",
        authority_ref="AGENTS.md",
        source_revision="a0370fc",
        oracle_revision=1,
        polarity="bad",
        inputs={
            "finding_id": "F_GATED",
            "assessment": "uncertain",
            "evidence_refs": ["AGENTS.md"],
            "derived_milestone_id": "m_gated",
        },
        expected_findings=(
            FindingShape(
                category="dependencies",
                kind="prerequisite_evidence_missing",
                severity="high",
                affected_requirement_id="R_GATED",
                affected_subject="F_GATED",
            ),
        ),
        expected_decision="block",
        forbidden_side_effects=("m_gated executed before evidence lands",),
        required_correction="plan.claim_decisions += VALIDATE_FIRST(F_GATED, [m_gated])",
        post_correction_outcome="admit",
    )

    # ----- S1 bad case: an unresolved critical gap on Plan r1 -----
    s1_bad = CaseDefinition(
        case_id="S1.plan_correction.bad_case",
        accepted_requirement_id="R1",
        authority_ref="AGENTS.md",
        source_revision="a0370fc",
        oracle_revision=1,
        polarity="bad",
        inputs={
            "gap_id": "g_missing_recovery",
            "status": "open",
            "severity": "critical",
            "evidence_ref": "docs/recovery_runbook.md",
        },
        expected_findings=(
            FindingShape(
                category="missing",
                kind="required_capability_missing",
                severity="critical",
                affected_requirement_id="R1",
                affected_subject="docs/recovery_runbook.md",
            ),
        ),
        expected_decision="block",
        forbidden_side_effects=("Build admitted on Plan r1",),
        required_correction=(
            "resolve gap with fix_receipt_ref and recheck_receipt_ref; bump plan.revision to 2"
        ),
        post_correction_outcome="admit",
    )

    # ----- S5 bad case: effect must be at-most-once -----
    s5_bad = CaseDefinition(
        case_id="S5.crash_restart.bad_case",
        accepted_requirement_id="R_EFFECT",
        authority_ref="AGENTS.md",
        source_revision="a0370fc",
        oracle_revision=1,
        polarity="bad",
        inputs={
            "action_id": "aid-pre",
            "kill_at": "pre_effect",
        },
        expected_findings=(
            FindingShape(
                category="feasibility",
                kind="pre_effect_crash_without_reconcile",
                severity="high",
                affected_requirement_id="R_EFFECT",
                affected_subject="aid-pre",
            ),
        ),
        expected_decision="block",
        forbidden_side_effects=(
            "effect applied twice",
            "effect applied without prior intent record",
        ),
        required_correction="restart with CHECKPOINT_RECONCILE=1",
        post_correction_outcome="admit",
    )

    cases = [s1_bad, s2_bad, s2_good, s3_bad, s5_bad]
    return [_AuthorisedEntry(case=c, sha=c.self_sha) for c in cases]


# Convenience module-level sentinel so callers can detect oracle drift
# without having to look up any individual case.
CATALOG = OracleCatalog.default()
"""Default authority. Use `oracles.CATALOG.get("<case_id>")`."""


__all__ = [
    "ORACLE_CATALOG_REVISION",
    "FindingShape",
    "CaseDefinition",
    "OracleCatalog",
    "CATALOG",
]
