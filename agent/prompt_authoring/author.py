"""`PromptAuthor` — generate, revise, supersede candidate prompts.

Side-effect-free: every operation returns a new `PromptDefinition`
instance. Persistence is the caller's job (see `PromptStore`).

Status machine (upheld by `_transition`):

    UNEVALUATED  → EVALUATED | BLOCKED
    BLOCKED      → EVALUATED (post revise+evaluate)
    EVALUATED    → ACTIVE | SUPERSEDED | ARCHIVED
    ACTIVE       → SUPERSEDED | ARCHIVED
    SUPERSEDED   → terminal
    ARCHIVED     → terminal

A revision never jumps directly to ACTIVE — activation is the
authorized-owner-only path owned by `PromptStore.activate`.

An ACTIVE revision is immutable: any `revise()` call that targets one
goes through `supersede()` instead, which emits a NEW revision whose
`supersedes` field points at the ACTIVE one.
"""

from __future__ import annotations

from agent.prompt_authoring.evaluator import EvaluationReceipt
from agent.prompt_authoring.types import (
    PromptDefinition,
    PromptSpec,
    PromptStatus,
    Stage,
    canonical_content_digest,
)

# ---------------------------------------------------------------------------
# Typed errors
# ---------------------------------------------------------------------------


class StatusTransitionError(RuntimeError):
    """Raised when a status transition is not allowed by the state machine."""


class ImmutableRevisionError(RuntimeError):
    """Raised when a caller tries to edit an ACTIVE / SUPERSEDED /
    ARCHIVED revision in place.

    The caller must `supersede()` to produce a new revision instead.
    """


# Allowed forward transitions.
_ALLOWED: dict[PromptStatus, frozenset[PromptStatus]] = {
    PromptStatus.UNEVALUATED: frozenset(
        {PromptStatus.EVALUATED, PromptStatus.BLOCKED, PromptStatus.ARCHIVED}
    ),
    PromptStatus.BLOCKED: frozenset(
        {PromptStatus.EVALUATED, PromptStatus.ARCHIVED}
    ),
    PromptStatus.EVALUATED: frozenset(
        {PromptStatus.ACTIVE, PromptStatus.SUPERSEDED, PromptStatus.ARCHIVED}
    ),
    PromptStatus.ACTIVE: frozenset(
        {PromptStatus.SUPERSEDED, PromptStatus.ARCHIVED}
    ),
    PromptStatus.SUPERSEDED: frozenset(),
    PromptStatus.ARCHIVED: frozenset(),
}


# ---------------------------------------------------------------------------
# PromptAuthor
# ---------------------------------------------------------------------------


class PromptAuthor:
    """Pure authoring surface.

    Operations:
      * `author_candidate(spec)` — spec → initial revision=1 UNEVALUATED prompt.
      * `revise(prompt, …)` — produce a new revision=N+1 that incorporates
        evaluator findings. If the caller's prompt is ACTIVE / SUPERSEDED /
        ARCHIVED, use `supersede` instead.
      * `supersede(active_prompt, …)` — produce a new revision superseding
        an ACTIVE revision.
      * `apply_receipt(prompt, receipt)` — map an evaluator receipt
        onto the status machine. UNEVALUATED → EVALUATED / BLOCKED.
    """

    def author_candidate(self, spec: PromptSpec) -> PromptDefinition:
        """Spec → initial (revision=1, status=UNEVALUATED) candidate."""
        payload = {
            "prompt_id": spec.prompt_id,
            "revision": 1,
            "stage": spec.stage,
            "owner": spec.owner,
            "runtime_inputs": [ri.model_dump() for ri in spec.runtime_inputs],
            "stable_instructions": list(spec.stable_instructions),
            "required_capabilities": spec.required_capabilities.model_dump(),
            "output_contract": dict(spec.output_contract),
            "evaluation_rules": list(spec.evaluation_rules),
            "recovery_behavior": spec.recovery_behavior,
            "supersedes": None,
        }
        digest = canonical_content_digest(payload)
        return PromptDefinition(
            prompt_id=spec.prompt_id,
            revision=1,
            content_digest=digest,
            stage=spec.stage,
            owner=spec.owner,
            runtime_inputs=list(spec.runtime_inputs),
            stable_instructions=list(spec.stable_instructions),
            required_capabilities=spec.required_capabilities,
            output_contract=dict(spec.output_contract),
            evaluation_rules=list(spec.evaluation_rules),
            recovery_behavior=spec.recovery_behavior,
            fixture_refs=list(spec.fixture_refs),
            evaluation_receipt_ref=None,
            supersedes=None,
            status=PromptStatus.UNEVALUATED,
        )

    def revise(
        self,
        prompt: PromptDefinition,
        *,
        stable_instructions: list[str] | None = None,
        output_contract: dict | None = None,
        evaluation_rules: list[str] | None = None,
        recovery_behavior: str | None = None,
    ) -> PromptDefinition:
        """Produce a successor revision of a NON-ACTIVE candidate.

        For an ACTIVE revision, use `supersede(…)`. In-place edit of
        an ACTIVE revision raises `ImmutableRevisionError`.
        """
        if prompt.status in {
            PromptStatus.ACTIVE,
            PromptStatus.SUPERSEDED,
            PromptStatus.ARCHIVED,
        }:
            raise ImmutableRevisionError(
                f"Cannot revise an immutable revision "
                f"({prompt.prompt_id}@{prompt.revision}, status={prompt.status.value}). "
                "Use PromptAuthor.supersede(...) to produce a new revision."
            )
        # M1 corrective: revise()-line revisions must carry a back-reference
        # so the accepted_regression axis does not reject them. The DIFFERENCE
        # between revise and supersede is a STATUS-GATE distinction (revise
        # refuses ACTIVE; supersede requires EVALUATED/ACTIVE), not a lineage
        # distinction. ALL revisions >= 2 carry the back-reference, uniformly.
        return self._next_revision(
            prompt,
            supersedes=f"{prompt.prompt_id}@{prompt.revision}",
            stable_instructions=stable_instructions,
            output_contract=output_contract,
            evaluation_rules=evaluation_rules,
            recovery_behavior=recovery_behavior,
            initial_status=PromptStatus.UNEVALUATED,
        )

    def supersede(
        self,
        prompt: PromptDefinition,
        *,
        stable_instructions: list[str] | None = None,
        output_contract: dict | None = None,
        evaluation_rules: list[str] | None = None,
        recovery_behavior: str | None = None,
    ) -> PromptDefinition:
        """Emit a NEW revision that supersedes `prompt`.

        Allowed when `prompt.status` is EVALUATED or ACTIVE. The new
        revision carries `supersedes=f"{prompt.prompt_id}@{prompt.revision}"`.
        """
        if prompt.status not in {PromptStatus.EVALUATED, PromptStatus.ACTIVE}:
            raise StatusTransitionError(
                f"supersede({prompt.prompt_id}@{prompt.revision}): source "
                f"status must be EVALUATED or ACTIVE, got {prompt.status.value}."
            )
        return self._next_revision(
            prompt,
            supersedes=f"{prompt.prompt_id}@{prompt.revision}",
            stable_instructions=stable_instructions,
            output_contract=output_contract,
            evaluation_rules=evaluation_rules,
            recovery_behavior=recovery_behavior,
            initial_status=PromptStatus.UNEVALUATED,
        )

    def apply_receipt(
        self, prompt: PromptDefinition, receipt: EvaluationReceipt
    ) -> PromptDefinition:
        """Return the same prompt with status updated from receipt.

        Only UNEVALUATED → EVALUATED / BLOCKED is handled here.
        Activation and supersession remain owner-driven (store).
        """
        if receipt.prompt_id != prompt.prompt_id or receipt.revision != prompt.revision:
            raise StatusTransitionError(
                "apply_receipt: receipt does not match this prompt "
                f"({receipt.prompt_id}@{receipt.revision} vs "
                f"{prompt.prompt_id}@{prompt.revision})"
            )
        if receipt.content_digest != prompt.content_digest:
            raise StatusTransitionError(
                "apply_receipt: receipt.content_digest does not match "
                "prompt.content_digest — the receipt belongs to a different "
                "revision."
            )
        if prompt.status not in {PromptStatus.UNEVALUATED, PromptStatus.BLOCKED}:
            raise StatusTransitionError(
                f"apply_receipt: prompt status {prompt.status.value} does not "
                "accept a new evaluation receipt."
            )
        new_status = receipt.status
        allowed_eval_outcomes = {
            PromptStatus.EVALUATED,
            PromptStatus.BLOCKED,
            PromptStatus.UNEVALUATED,
        }
        if new_status not in allowed_eval_outcomes:
            raise StatusTransitionError(
                f"apply_receipt: receipt.status {new_status.value} is not a "
                "valid evaluation outcome. The receipt may only report "
                "EVALUATED, BLOCKED, or UNEVALUATED."
            )
        return _with_status(
            prompt,
            status=new_status,
            evaluation_receipt_ref=receipt.receipt_digest,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _next_revision(
        self,
        prompt: PromptDefinition,
        *,
        supersedes: str | None,
        stable_instructions: list[str] | None,
        output_contract: dict | None,
        evaluation_rules: list[str] | None,
        recovery_behavior: str | None,
        initial_status: PromptStatus,
    ) -> PromptDefinition:
        new_rev = prompt.revision + 1
        new_instr = (
            list(stable_instructions)
            if stable_instructions is not None
            else list(prompt.stable_instructions)
        )
        new_contract = (
            dict(output_contract)
            if output_contract is not None
            else dict(prompt.output_contract)
        )
        new_rules = (
            list(evaluation_rules)
            if evaluation_rules is not None
            else list(prompt.evaluation_rules)
        )
        new_recovery = (
            recovery_behavior
            if recovery_behavior is not None
            else prompt.recovery_behavior
        )

        payload = {
            "prompt_id": prompt.prompt_id,
            "revision": new_rev,
            "stage": prompt.stage,
            "owner": prompt.owner,
            "runtime_inputs": [ri.model_dump() for ri in prompt.runtime_inputs],
            "stable_instructions": new_instr,
            "required_capabilities": prompt.required_capabilities.model_dump(),
            "output_contract": new_contract,
            "evaluation_rules": new_rules,
            "recovery_behavior": new_recovery,
            "supersedes": supersedes,
        }
        digest = canonical_content_digest(payload)
        return PromptDefinition(
            prompt_id=prompt.prompt_id,
            revision=new_rev,
            content_digest=digest,
            stage=prompt.stage,
            owner=prompt.owner,
            runtime_inputs=list(prompt.runtime_inputs),
            stable_instructions=new_instr,
            required_capabilities=prompt.required_capabilities,
            output_contract=new_contract,
            evaluation_rules=new_rules,
            recovery_behavior=new_recovery,
            fixture_refs=list(prompt.fixture_refs),
            evaluation_receipt_ref=None,
            supersedes=supersedes,
            status=initial_status,
        )


# ---------------------------------------------------------------------------
# Shared helpers (used by store too)
# ---------------------------------------------------------------------------


def check_transition_allowed(
    from_status: PromptStatus, to_status: PromptStatus
) -> None:
    """Raise `StatusTransitionError` if the move is not permitted."""
    if to_status == from_status:
        return
    allowed = _ALLOWED.get(from_status, frozenset())
    if to_status not in allowed:
        raise StatusTransitionError(
            f"Status transition {from_status.value} → {to_status.value} is "
            f"not allowed; permitted targets: "
            f"{sorted(a.value for a in allowed)}"
        )


def _with_status(
    prompt: PromptDefinition,
    *,
    status: PromptStatus,
    evaluation_receipt_ref: str | None = None,
) -> PromptDefinition:
    """Return a copy of `prompt` with status / receipt-ref updated.

    Status transition is validated by `check_transition_allowed`.
    """
    check_transition_allowed(prompt.status, status)
    data = prompt.model_dump()
    data["status"] = status.value
    if evaluation_receipt_ref is not None:
        data["evaluation_receipt_ref"] = evaluation_receipt_ref
    return PromptDefinition.model_validate(data)


# Re-export Stage for callers importing from `author`.
__all__ = [
    "PromptAuthor",
    "StatusTransitionError",
    "ImmutableRevisionError",
    "Stage",
    "check_transition_allowed",
]
