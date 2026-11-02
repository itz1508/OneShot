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
from agent.prompt_authoring.evaluator import EvaluationReceipt
from agent.prompt_authoring.types import (
    PromptDefinition,
    PromptStatus,
    Stage,
)

# ---------------------------------------------------------------------------
# Authorization provenance (M1 corrective — reviewer directive)
# ---------------------------------------------------------------------------
#
# The pre-M1 contract let callers supply any string as the "actor". Even with
# `authorized_actors={"release-owner"}`, a caller could just type
# `store.activate(..., actor="release-owner")` and bypass the check. The
# reviewer required the actor identity to come from a trusted authentication
# context, not from the caller.
#
# In-process we implement that via a Principal / IdentityProvider pair:
#   * IdentityProvider.authenticate(name, secret) -> Principal(verified=True)
#       Only an IdentityProvider that already knows the (name, secret) pair
#       returns a verified Principal.
#   * Principal.unverified(name) -> Principal(verified=False)
#       A caller can mint one of these at will. PromptStore refuses them when
#       the store is configured with authorized_actors.
#   * `_issuer_sentinel` is a module-private object(). A Principal is verified
#       only when its `_issuer_sentinel is _ISSUER_SENTINEL` — an attacker who
#       spoofs `Principal(name="...", _issuer_sentinel=object())` fails the
#       identity check.

_ISSUER_SENTINEL = object()


@dataclass(frozen=True)
class Principal:
    """Identity carrier for authorization-gated operations.

    Construct an UNVERIFIED Principal with `Principal.unverified(name)`. The
    store accepts it only when `authorized_actors` is None (backward-compat).

    `issuer_token` is a per-host provenance marker. ToolRegistry generates a
    private `host_token` object at construction and only honours Principals
    carrying that same reference. The M1 PromptStore uses the simpler
    module-level `_issuer_sentinel` and does not inspect `issuer_token` — the
    two gates are complementary.
    """

    name: str
    _issuer_sentinel: object = field(default=None, repr=False, compare=False)
    issuer_token: object | None = field(default=None, repr=False, compare=False)

    @classmethod
    def unverified(cls, name: str) -> Principal:
        return cls(name=name, _issuer_sentinel=None, issuer_token=None)

    @property
    def verified(self) -> bool:
        return self._issuer_sentinel is _ISSUER_SENTINEL


class IdentityProvider:
    """Issues verified Principals in exchange for the (name, secret) pair.

    This is the in-process substitute for a signed-token flow. In production
    the IdentityProvider would validate a JWT, mutual TLS cert, or OIDC
    assertion; here we validate a secret the host supplies out of band at
    construction. The store trusts the Principal because it carries the
    private `_ISSUER_SENTINEL`, which an attacker cannot reproduce.

    When `issuer_token=<obj>` is supplied, authenticated Principals carry it
    too. The ToolRegistry rejects Principals whose `issuer_token` does not
    match the token it was constructed with — this is the trusted-host-
    identity-provenance gate (reviewer directive #1): an attacker who builds
    their own IdentityProvider with their own secrets still cannot forge the
    registry's private host_token reference.
    """

    def __init__(
        self,
        *,
        credentials: dict[str, str],
        issuer_token: object | None = None,
    ) -> None:
        self._credentials: dict[str, str] = dict(credentials)
        self._issuer_token = issuer_token

    def authenticate(self, name: str, secret: str) -> Principal:
        """Return a verified Principal if (name, secret) matches, else raise."""
        import hmac
        expected = self._credentials.get(name)
        if expected is None or not hmac.compare_digest(expected, secret):
            raise PromptStoreError(
                f"IdentityProvider.authenticate({name!r}): credential mismatch"
            )
        return Principal(
            name=name,
            _issuer_sentinel=_ISSUER_SENTINEL,
            issuer_token=self._issuer_token,
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

    def __init__(self, *, authorized_actors: set[str] | None = None) -> None:
        self._by_key: dict[tuple[str, int], PromptDefinition] = {}
        self._audit: list[AuditEntry] = []
        # Receipt store — keyed by receipt_digest. Populated via
        # register_receipt(). activate() refuses to transition a prompt
        # whose evaluation_receipt_ref is not present here, which closes
        # the gap where a prompt could be marked EVALUATED and then its
        # receipt tampered or dropped without blocking activation.
        self._receipts: dict[str, Any] = {}
        # Authorized-actor allowlist. `None` = any actor allowed (backward
        # compatible). Explicit set = closed-list: activate/rollback refuse
        # unknown actors. `register` and `archive` are intentionally NOT
        # gated here; they are internal bookkeeping, not promotion.
        self._authorized_actors: set[str] | None = authorized_actors

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
    # Receipt store (M1 — independent receipt verification at activate)
    # ------------------------------------------------------------------

    def register_receipt(self, receipt: EvaluationReceipt) -> None:
        """Register an EvaluationReceipt so activate() can independently verify it.

        Callers MUST call this after `PromptAuthor.apply_receipt(prompt, receipt)`
        and BEFORE `activate(...)`. The store refuses to activate a prompt whose
        `evaluation_receipt_ref` was never registered here.

        M1 corrective (reviewer directive): the receipt is now strictly typed
        (`EvaluationReceipt`, not `Any`); its `receipt_digest` is RECOMPUTED
        from canonical fields and compared with the supplied one; and the
        receipt status MUST be EVALUATED. A forged receipt whose identity
        fields happen to match a real prompt is now rejected.
        """
        if not isinstance(receipt, EvaluationReceipt):
            raise PromptStoreError(
                f"register_receipt: expected EvaluationReceipt, got "
                f"{type(receipt).__name__}. Build the receipt with "
                "PromptEvaluator.evaluate(...)."
            )
        if receipt.status != PromptStatus.EVALUATED:
            raise PromptStoreError(
                f"register_receipt: receipt.status is {receipt.status.value!r}, "
                "not 'evaluated' — only passing receipts may authorise activation."
            )
        from agent.prompt_authoring.evaluator import canonical_receipt_digest
        recomputed = canonical_receipt_digest(receipt)
        if recomputed != receipt.receipt_digest:
            raise PromptStoreError(
                "register_receipt: receipt.receipt_digest does not match the "
                "digest recomputed from the receipt\'s canonical fields — the "
                "receipt was tampered with or was produced by a non-canonical "
                "evaluator."
            )
        rd = receipt.receipt_digest
        existing = self._receipts.get(rd)
        if (
            existing is not None
            and existing is not receipt
            and (
                getattr(existing, "prompt_id", None) != getattr(receipt, "prompt_id", None)
                or getattr(existing, "revision", None) != getattr(receipt, "revision", None)
                or getattr(existing, "content_digest", None)
                != getattr(receipt, "content_digest", None)
            )
        ):
            raise PromptStoreError(
                f"register_receipt: a different receipt is already registered under "
                f"digest {rd!r} — refusing to overwrite."
            )
        self._receipts[rd] = receipt
        self._audit.append(
            AuditEntry(
                at=time.time(),
                actor="system",
                action="register_receipt",
                prompt_id=getattr(receipt, "prompt_id", "?"),
                revision=getattr(receipt, "revision", 0),
                details={"receipt_digest": rd},
            )
        )

    def _resolve_actor_identity(
        self,
        principal: Principal | None,
        actor: str | None,
        action: str,
    ) -> str:
        """Resolve the effective actor identity.

        Precedence: `principal` wins; `actor` is accepted only when the store
        has no `authorized_actors` allowlist (backward-compat with pre-M1
        callers). An untrusted caller cannot bypass authorization by supplying
        a free-form string once the store is configured.
        """
        if principal is None and actor is None:
            raise PromptStoreError(
                f"{action}: pass a Principal (preferred) or actor= (bc only)"
            )
        if principal is not None:
            if self._authorized_actors is not None:
                if not principal.verified:
                    raise PromptStoreError(
                        f"{action}: principal {principal.name!r} is unverified "
                        "— obtain a verified Principal via an IdentityProvider."
                    )
                if principal.name not in self._authorized_actors:
                    raise PromptStoreError(
                        f"{action}: principal {principal.name!r} is not in the "
                        f"authorized_actors set configured on this store."
                    )
            return principal.name
        # actor-string path. Allowed only when no allowlist is set.
        if self._authorized_actors is not None:
            raise PromptStoreError(
                f"{action}: this store requires a verified Principal; "
                "`actor=` strings are refused once authorized_actors is set."
            )
        return actor  # type: ignore[return-value]

    def _authorize(self, actor: str, action: str) -> None:  # retained for bc
        """Legacy entry point. New code should use _resolve_actor_identity."""
        if self._authorized_actors is None:
            return
        if actor not in self._authorized_actors:
            raise PromptStoreError(
                f"{action}: actor {actor!r} is not in the authorized_actors set "
                f"configured on this store. Add the actor to the set at store "
                f"construction time, or construct the store without an allowlist "
                f"to disable actor gating."
            )

    def _require_registered_receipt(
        self, prompt: PromptDefinition
    ) -> None:
        """Independent receipt verification required by activate() / rollback().

        A prompt whose status is EVALUATED carries an evaluation_receipt_ref
        (set by `PromptAuthor.apply_receipt`). The ref MUST be present in the
        store's receipt dict AND the receipt's own fields must match the
        prompt's identity+digest. Otherwise the receipt is missing / tampered
        and activation refuses.
        """
        ref = prompt.evaluation_receipt_ref
        if not ref:
            raise PromptStoreError(
                f"activate/rollback({prompt.prompt_id}@{prompt.revision}): prompt has "
                f"no evaluation_receipt_ref — cannot verify receipt."
            )
        receipt = self._receipts.get(ref)
        if receipt is None:
            raise PromptStoreError(
                f"activate/rollback({prompt.prompt_id}@{prompt.revision}): "
                f"evaluation_receipt_ref {ref!r} is not registered in this store. "
                f"Call store.register_receipt(receipt) after apply_receipt."
            )
        if (
            getattr(receipt, "prompt_id", None) != prompt.prompt_id
            or getattr(receipt, "revision", None) != prompt.revision
            or getattr(receipt, "content_digest", None) != prompt.content_digest
        ):
            raise PromptStoreError(
                f"activate/rollback({prompt.prompt_id}@{prompt.revision}): "
                f"registered receipt identity/digest does not match the prompt — "
                f"receipt may be tampered or belongs to a different revision."
            )


    # ------------------------------------------------------------------
    # Activation / rollback
    # ------------------------------------------------------------------

    def activate(
        self,
        prompt_id: str,
        revision: int,
        *,
        principal: Principal | None = None,
        actor: str | None = None,
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
        actor_name = self._resolve_actor_identity(
            principal, actor, f"activate({prompt_id}@{revision})"
        )
        self._require_registered_receipt(prompt)
        # Supersede any current ACTIVE revision.
        for other in self.list_revisions(prompt_id):
            if other.status == PromptStatus.ACTIVE:
                self._by_key[(other.prompt_id, other.revision)] = _with_status(
                    other, status=PromptStatus.SUPERSEDED
                )
                self._audit.append(
                    AuditEntry(
                        at=time.time(),
                        actor=actor_name,
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
                actor=actor_name,
                action="activate",
                prompt_id=prompt_id,
                revision=revision,
            )
        )
        return activated

    def rollback(
        self,
        prompt_id: str,
        revision: int,
        *,
        principal: Principal | None = None,
        actor: str | None = None,
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
        actor_name = self._resolve_actor_identity(
            principal, actor, f"rollback({prompt_id}@{revision})"
        )
        self._require_registered_receipt(target)

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
                        actor=actor_name,
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
                actor=actor_name,
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
