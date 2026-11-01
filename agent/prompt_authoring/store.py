"""`PromptStore` — append-only in-process registry.

Preserves prompt definitions, evaluation receipts, and supersession
links. Audit entries record every activate / rollback / supersede
decision with timestamp + actor; history is never modified.

The store is deliberately small and in-process; a future
TaskManager-backed implementation can replace it without changing
callers (same operations, same signatures).
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from agent.prompt_authoring.author import (
    _with_status,
    check_transition_allowed,
)
from agent.prompt_authoring.types import (
    PromptDefinition,
    PromptStatus,
    Stage,
)


class PromptStoreError(RuntimeError):
    """Raised by the store when a caller attempts an operation its
    append-only / status-machine contract refuses."""


@dataclass(frozen=True)
class AuditEntry:
    """One entry in the audit log."""

    at: float
    actor: str
    action: str  # "register" | "activate" | "rollback" | "supersede" | "archive"
    prompt_id: str
    revision: int
    details: dict[str, Any] = field(default_factory=dict)


class PromptStore:
    """Append-only in-memory revision store.

    Operations:
      * `register(prompt)`              → add a candidate revision
      * `get(prompt_id, revision)`      → look up a revision
      * `list_revisions(prompt_id)`     → all revisions, sorted ascending
      * `activate(prompt_id, revision, actor)` → mark EVALUATED → ACTIVE
      * `rollback(prompt_id, revision, actor)` → re-activate an older
                                                 EVALUATED / SUPERSEDED revision
      * `active_revision(prompt_id)`    → the single ACTIVE revision (or None)
    """

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, int], PromptDefinition] = {}
        self._audit: list[AuditEntry] = []

    # ------------------------------------------------------------------
    # Register / lookup
    # ------------------------------------------------------------------

    def register(self, prompt: PromptDefinition, *, actor: str = "system") -> None:
        """Register a new revision. Idempotent on identical content_digest."""
        key = (prompt.prompt_id, prompt.revision)
        existing = self._by_key.get(key)
        if existing is not None:
            if existing.content_digest != prompt.content_digest:
                raise PromptStoreError(
                    f"register({prompt.prompt_id}@{prompt.revision}): a different "
                    f"content_digest is already registered under this key "
                    f"({existing.content_digest!r} vs {prompt.content_digest!r})."
                )
            return  # idempotent
        if prompt.revision > 1:
            prior = self._by_key.get((prompt.prompt_id, prompt.revision - 1))
            if prior is None:
                raise PromptStoreError(
                    f"register({prompt.prompt_id}@{prompt.revision}): revision "
                    f"{prompt.revision - 1} is not registered; register the "
                    "prior revision first."
                )
            expected_supersedes = f"{prompt.prompt_id}@{prompt.revision - 1}"
            if prompt.supersedes is not None and prompt.supersedes != expected_supersedes:
                raise PromptStoreError(
                    f"register({prompt.prompt_id}@{prompt.revision}): supersedes "
                    f"= {prompt.supersedes!r} does not reference the prior "
                    f"revision {expected_supersedes!r}."
                )
        self._by_key[key] = prompt
        self._audit.append(
            AuditEntry(
                at=time.time(),
                actor=actor,
                action="register",
                prompt_id=prompt.prompt_id,
                revision=prompt.revision,
                details={
                    "status": prompt.status.value,
                    "content_digest": prompt.content_digest,
                },
            )
        )

    def get(self, prompt_id: str, revision: int) -> PromptDefinition | None:
        return self._by_key.get((prompt_id, revision))

    def list_revisions(self, prompt_id: str) -> list[PromptDefinition]:
        return [
            v
            for k, v in sorted(self._by_key.items(), key=lambda kv: kv[0][1])
            if k[0] == prompt_id
        ]

    def audit_log(self, prompt_id: str | None = None) -> list[AuditEntry]:
        """Return the audit log, optionally filtered by prompt_id."""
        if prompt_id is None:
            return list(self._audit)
        return [e for e in self._audit if e.prompt_id == prompt_id]

    # ------------------------------------------------------------------
    # Activation / rollback
    # ------------------------------------------------------------------

    def activate(
        self, prompt_id: str, revision: int, *, actor: str
    ) -> PromptDefinition:
        """Mark an EVALUATED revision ACTIVE.

        Any previously-ACTIVE revision of the same prompt_id is
        SUPERSEDED at the same moment, with an audit entry.
        """
        prompt = self._require(prompt_id, revision)
        if prompt.status != PromptStatus.EVALUATED:
            raise PromptStoreError(
                f"activate({prompt_id}@{revision}): source status must be "
                f"EVALUATED, got {prompt.status.value}."
            )
        # Supersede any current ACTIVE revision.
        for other in self.list_revisions(prompt_id):
            if other.status == PromptStatus.ACTIVE:
                self._by_key[(other.prompt_id, other.revision)] = _with_status(
                    other, status=PromptStatus.SUPERSEDED
                )
                self._audit.append(
                    AuditEntry(
                        at=time.time(),
                        actor=actor,
                        action="supersede",
                        prompt_id=other.prompt_id,
                        revision=other.revision,
                        details={"replaced_by_revision": revision},
                    )
                )
        activated = _with_status(prompt, status=PromptStatus.ACTIVE)
        self._by_key[(prompt_id, revision)] = activated
        self._audit.append(
            AuditEntry(
                at=time.time(),
                actor=actor,
                action="activate",
                prompt_id=prompt_id,
                revision=revision,
            )
        )
        return activated

    def rollback(
        self, prompt_id: str, revision: int, *, actor: str
    ) -> PromptDefinition:
        """Re-activate an older revision after it was superseded.

        Allowed when target status is SUPERSEDED and the revision was
        previously EVALUATED or ACTIVE. The current ACTIVE revision is
        marked SUPERSEDED. The historical status chain is preserved —
        we never rewrite past audit entries.
        """
        target = self._require(prompt_id, revision)
        if target.status not in {
            PromptStatus.SUPERSEDED,
            PromptStatus.EVALUATED,
        }:
            raise PromptStoreError(
                f"rollback({prompt_id}@{revision}): target status must be "
                f"SUPERSEDED or EVALUATED, got {target.status.value}."
            )

        # Transition target: SUPERSEDED is terminal in the forward
        # machine, so we build the ACTIVE revision via a direct model
        # construction rather than `_with_status` (which refuses
        # SUPERSEDED → ACTIVE). The audit log makes the rollback
        # transparent.
        data = target.model_dump()
        data["status"] = PromptStatus.ACTIVE.value
        reactivated = PromptDefinition.model_validate(data)

        # Supersede the current ACTIVE revision (if any) that is NOT
        # the target.
        for other in self.list_revisions(prompt_id):
            if (
                other.status == PromptStatus.ACTIVE
                and other.revision != revision
            ):
                self._by_key[(other.prompt_id, other.revision)] = _with_status(
                    other, status=PromptStatus.SUPERSEDED
                )
                self._audit.append(
                    AuditEntry(
                        at=time.time(),
                        actor=actor,
                        action="supersede",
                        prompt_id=other.prompt_id,
                        revision=other.revision,
                        details={
                            "replaced_by_revision": revision,
                            "cause": "rollback",
                        },
                    )
                )

        self._by_key[(prompt_id, revision)] = reactivated
        self._audit.append(
            AuditEntry(
                at=time.time(),
                actor=actor,
                action="rollback",
                prompt_id=prompt_id,
                revision=revision,
                details={"from_status": target.status.value},
            )
        )
        return reactivated

    def archive(
        self, prompt_id: str, revision: int, *, actor: str
    ) -> PromptDefinition:
        """Terminal archive of a revision. Only EVALUATED / SUPERSEDED
        / BLOCKED / UNEVALUATED revisions may be archived; ACTIVE must
        be superseded first (archive would silently remove the active
        prompt otherwise).
        """
        target = self._require(prompt_id, revision)
        if target.status == PromptStatus.ACTIVE:
            raise PromptStoreError(
                f"archive({prompt_id}@{revision}): cannot archive an ACTIVE "
                "revision. Activate another revision first (which supersedes "
                "this one), then archive."
            )
        check_transition_allowed(target.status, PromptStatus.ARCHIVED)
        data = target.model_dump()
        data["status"] = PromptStatus.ARCHIVED.value
        archived = PromptDefinition.model_validate(data)
        self._by_key[(prompt_id, revision)] = archived
        self._audit.append(
            AuditEntry(
                at=time.time(),
                actor=actor,
                action="archive",
                prompt_id=prompt_id,
                revision=revision,
            )
        )
        return archived

    # ------------------------------------------------------------------
    # Convenience lookups
    # ------------------------------------------------------------------

    def active_revision(
        self, prompt_id: str, *, stage: Stage | None = None
    ) -> PromptDefinition | None:
        for v in self.list_revisions(prompt_id):
            if v.status != PromptStatus.ACTIVE:
                continue
            if stage is not None and v.stage != stage:
                continue
            return v
        return None

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require(self, prompt_id: str, revision: int) -> PromptDefinition:
        got = self._by_key.get((prompt_id, revision))
        if got is None:
            raise PromptStoreError(
                f"{prompt_id}@{revision}: revision not registered."
            )
        return got

    def __contains__(self, key: Iterable) -> bool:
        try:
            prompt_id, revision = key
        except Exception:
            return False
        return (prompt_id, revision) in self._by_key

    def __len__(self) -> int:  # pragma: no cover - debug helper
        return len(self._by_key)
