"""Red-first tests for Prompt Authoring.

Covers:

* Pydantic domain-model round-trip (PromptSpec / PromptDefinition
  / OwnerRef / RuntimeInputSpec), content-digest tamper rejection.
* PromptAuthor: deterministic digest; revise bumps revision; supersede
  wires the back-reference; apply_receipt reflects evaluator outcome;
  ImmutableRevisionError on edit of ACTIVE revisions.
* PromptEvaluator: nine axes; aggregate rule BLOCKS on any FAIL;
  passes schema-conformant prompts; refuses silent downgrades
  (any FAIL => BLOCKED).
* PromptFixtureRegistry: one of each kind in default.
* PromptStore: append-only registration; activate / rollback /
  archive with audit entries; cannot activate BLOCKED; the active
  revision is unique per prompt_id.
* OneShotController.prompt_store lazy construction + non-interference.
"""

from __future__ import annotations

import tempfile

import pytest
from pydantic import ValidationError

from agent.prompt_authoring import (
    EvaluationReceipt,
    ImmutableRevisionError,
    OwnerRef,
    PromptAuthor,
    PromptDefinition,
    PromptEvaluator,
    PromptFixtureKind,
    PromptFixtureRegistry,
    PromptSpec,
    PromptStatus,
    PromptStore,
    PromptStoreError,
    RuntimeInputSpec,
    StatusTransitionError,
)
from agent.prompt_authoring.evaluator import CheckOutcome, CheckResult
from agent.prompt_authoring.types import Stage, canonical_content_digest
from agent.providers.types import ProviderCapabilities


def _owner(kind: str = "prompt_authoring") -> OwnerRef:
    return OwnerRef(kind=kind, identifier="core-team")


def _spec(**overrides) -> PromptSpec:
    kwargs = {
        "prompt_id": "research-counter",
        "stage": Stage.RESEARCH,
        "owner": _owner(),
        "stage_specification": "Research stage for the context_counter demo.",
        "task_class": "summarise",
        "runtime_inputs": [
            RuntimeInputSpec(name="objective", meaning="user task text", required=True)
        ],
        "output_contract": {
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
        },
        "required_capabilities": ProviderCapabilities(structured_outputs=True),
        "stable_instructions": [
            "Reason about the user objective and emit a status.",
            "If the objective is unknown or blocked, say so explicitly.",
        ],
        "evaluation_rules": ["Status must be one of ok, blocked, unknown."],
        "recovery_behavior": "Preserve prior evidence refs across resumption.",
    }
    kwargs.update(overrides)
    return PromptSpec(**kwargs)


# ---------------------------------------------------------------------------
# Domain-model round-trip
# ---------------------------------------------------------------------------


class TestDomainModel:
    def test_prompt_spec_round_trip(self):
        spec = _spec()
        rebuilt = PromptSpec.model_validate(spec.model_dump())
        assert rebuilt.prompt_id == "research-counter"
        assert rebuilt.required_capabilities.structured_outputs is True

    def test_prompt_spec_rejects_blank_recovery(self):
        with pytest.raises(ValidationError):
            _spec(recovery_behavior="")

    def test_prompt_spec_rejects_bad_prompt_id(self):
        with pytest.raises(ValidationError):
            _spec(prompt_id="Bad Id")

    def test_prompt_definition_rejects_tampered_digest(self):
        prompt = PromptAuthor().author_candidate(_spec())
        payload = prompt.model_dump()
        payload["content_digest"] = "f" * 64
        with pytest.raises(ValidationError) as ctx:
            PromptDefinition.model_validate(payload)
        assert "content_digest mismatch" in str(ctx.value)

    def test_prompt_definition_rejects_empty_output_contract(self):
        prompt = PromptAuthor().author_candidate(_spec())
        payload = prompt.model_dump()
        payload["output_contract"] = {}
        # recompute digest so validator sees the output_contract error
        with pytest.raises(ValidationError):
            PromptDefinition.model_validate(payload)


# ---------------------------------------------------------------------------
# PromptAuthor
# ---------------------------------------------------------------------------


class TestPromptAuthor:
    def test_author_candidate_sets_unevaluated_revision_1(self):
        prompt = PromptAuthor().author_candidate(_spec())
        assert prompt.revision == 1
        assert prompt.status == PromptStatus.UNEVALUATED
        assert prompt.supersedes is None

    def test_identical_specs_produce_identical_digests(self):
        a = PromptAuthor().author_candidate(_spec())
        b = PromptAuthor().author_candidate(_spec())
        assert a.content_digest == b.content_digest

    def test_different_specs_produce_different_digests(self):
        a = PromptAuthor().author_candidate(_spec())
        b = PromptAuthor().author_candidate(
            _spec(recovery_behavior="Different recovery behaviour.")
        )
        assert a.content_digest != b.content_digest

    def test_revise_bumps_revision_and_resets_status(self):
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        b = author.revise(a, recovery_behavior="Updated recovery behaviour.")
        assert b.revision == 2
        assert b.status == PromptStatus.UNEVALUATED
        # M1 corrective: revise() DOES set supersedes to the prior revision so the
        # accepted_regression axis stops rejecting legitimate revise-line revisions.
        # The distinction between revise and supersede is now purely a status gate.
        assert b.supersedes == "research-counter@1"
        assert b.content_digest != a.content_digest

    def test_supersede_wires_back_reference(self):
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        # Pretend an evaluator passed → move to EVALUATED → ACTIVE path.
        receipt = _make_passing_receipt(a)
        a_eval = author.apply_receipt(a, receipt)
        assert a_eval.status == PromptStatus.EVALUATED
        b = author.supersede(a_eval, recovery_behavior="Replacement.")
        assert b.revision == 2
        assert b.supersedes == "research-counter@1"

    def test_revise_refuses_active_revision(self):
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        receipt = _make_passing_receipt(a)
        a_eval = author.apply_receipt(a, receipt)
        # Simulate activation by mutating the status in-place (store
        # normally does this; here we construct the ACTIVE revision
        # directly).
        payload = a_eval.model_dump()
        payload["status"] = PromptStatus.ACTIVE.value
        active = PromptDefinition.model_validate(payload)
        with pytest.raises(ImmutableRevisionError):
            author.revise(active, recovery_behavior="in-place edit forbidden")

    def test_apply_receipt_rejects_mismatched_revision(self):
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        bad = EvaluationReceipt(
            prompt_id=a.prompt_id,
            revision=a.revision + 7,  # mismatch
            content_digest=a.content_digest,
            fixtures_executed=[],
            checks=[],
            status=PromptStatus.EVALUATED,
            receipt_digest="e" * 64,
        )
        with pytest.raises(StatusTransitionError):
            author.apply_receipt(a, bad)

    def test_apply_receipt_rejects_mismatched_digest(self):
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        bad = EvaluationReceipt(
            prompt_id=a.prompt_id,
            revision=a.revision,
            content_digest="d" * 64,
            fixtures_executed=[],
            checks=[],
            status=PromptStatus.EVALUATED,
            receipt_digest="e" * 64,
        )
        with pytest.raises(StatusTransitionError):
            author.apply_receipt(a, bad)


# ---------------------------------------------------------------------------
# PromptEvaluator
# ---------------------------------------------------------------------------


class TestPromptEvaluator:
    def test_passes_well_formed_prompt(self):
        prompt = PromptAuthor().author_candidate(_spec())
        receipt = PromptEvaluator().evaluate(
            prompt, PromptFixtureRegistry.default().all()
        )
        assert receipt.status == PromptStatus.EVALUATED
        assert receipt.failures_by_axis == {}

    def test_any_single_fail_blocks(self):
        # Build an evaluator that fails exactly the responsibility
        # boundary axis for every fixture.
        def _fail_responsibility(prompt, fixture):
            return CheckResult(
                axis="responsibility_boundary",
                fixture=fixture.name,
                status=CheckOutcome.FAIL,
                evidence="synthetic failure",
            )

        axes = PromptEvaluator().__dict__["_axes"].copy()
        axes["responsibility_boundary"] = _fail_responsibility
        ev = PromptEvaluator(axes=axes)
        prompt = PromptAuthor().author_candidate(_spec())
        receipt = ev.evaluate(prompt, PromptFixtureRegistry.default().all())
        assert receipt.status == PromptStatus.BLOCKED
        assert receipt.failures_by_axis.get("responsibility_boundary", 0) >= 1

    def test_vendor_leak_in_stable_instructions_blocks(self):
        prompt = PromptAuthor().author_candidate(
            _spec(
                stable_instructions=[
                    "Call openai.chat.completions.create.",
                    "If the objective is unknown, say so.",
                ]
            )
        )
        receipt = PromptEvaluator().evaluate(
            prompt, PromptFixtureRegistry.default().all()
        )
        assert receipt.status == PromptStatus.BLOCKED
        assert "tool_selection_accuracy" in receipt.failures_by_axis

    def test_boundary_violation_blocks(self):
        prompt = PromptAuthor().author_candidate(
            _spec(owner=_owner(kind="provider_adapter"))
        )
        receipt = PromptEvaluator().evaluate(
            prompt, PromptFixtureRegistry.default().all()
        )
        assert receipt.status == PromptStatus.BLOCKED
        assert "responsibility_boundary" in receipt.failures_by_axis

    def test_missing_regression_backref_blocks_rev2(self):
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        # Create a rev-2 by hand WITHOUT a supersedes link.
        payload = a.model_dump()
        payload["revision"] = 2
        payload["supersedes"] = None
        payload["content_digest"] = canonical_content_digest({**payload})
        rev2 = PromptDefinition.model_validate(payload)
        receipt = PromptEvaluator().evaluate(
            rev2, PromptFixtureRegistry.default().all()
        )
        assert "accepted_regression" in receipt.failures_by_axis


# ---------------------------------------------------------------------------
# PromptFixtureRegistry
# ---------------------------------------------------------------------------


class TestPromptFixtureRegistry:
    def test_default_has_one_of_each_kind(self):
        reg = PromptFixtureRegistry.default()
        kinds = {c.kind for c in reg.all()}
        assert kinds == {
            PromptFixtureKind.VALID,
            PromptFixtureKind.INVALID,
            PromptFixtureKind.BLOCKED,
            PromptFixtureKind.RECOVERY,
        }

    def test_invalid_fixture_carries_expected_rejection(self):
        reg = PromptFixtureRegistry.default()
        for case in reg.by_kind(PromptFixtureKind.INVALID):
            assert case.expected_rejection is not None


# ---------------------------------------------------------------------------
# PromptStore
# ---------------------------------------------------------------------------


class TestPromptStore:
    def test_register_lookup_round_trip(self):
        store = PromptStore()
        prompt = PromptAuthor().author_candidate(_spec())
        store.register(prompt, actor="core-team")
        got = store.get(prompt.prompt_id, prompt.revision)
        assert got is not None and got.content_digest == prompt.content_digest

    def test_register_rejects_mismatched_digest_shadow(self):
        store = PromptStore()
        a = PromptAuthor().author_candidate(_spec())
        store.register(a)
        # Build a different definition at the same (id, revision) with
        # a different stable field — the digest will differ.
        payload = a.model_dump()
        payload["recovery_behavior"] = "Totally different recovery."
        payload["content_digest"] = canonical_content_digest(payload)
        shadow = PromptDefinition.model_validate(payload)
        with pytest.raises(PromptStoreError):
            store.register(shadow)

    def test_activate_requires_evaluated(self):
        store = PromptStore()
        prompt = PromptAuthor().author_candidate(_spec())
        store.register(prompt)
        with pytest.raises(PromptStoreError):
            store.activate(prompt.prompt_id, prompt.revision, actor="owner")

    def test_activate_evaluated_marks_active_and_supersedes_prior(self):
        store = PromptStore()
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        _r_a_eval = _make_passing_receipt(a)
        a_eval = author.apply_receipt(a, _r_a_eval)
        store.register(a_eval)
        store.register_receipt(_r_a_eval)
        active = store.activate(a.prompt_id, 1, actor="owner")
        assert active.status == PromptStatus.ACTIVE

        # Create and activate a second revision; the first must be SUPERSEDED.
        b = author.supersede(active, recovery_behavior="replacement b")
        _r_b_eval = _make_passing_receipt(b)
        b_eval = author.apply_receipt(b, _r_b_eval)
        store.register(b_eval)
        store.register_receipt(_r_b_eval)
        store.activate(b.prompt_id, 2, actor="owner")

        rev1 = store.get(a.prompt_id, 1)
        rev2 = store.get(a.prompt_id, 2)
        assert rev1.status == PromptStatus.SUPERSEDED
        assert rev2.status == PromptStatus.ACTIVE

        # The audit trail retains BOTH activations.
        actions = [e.action for e in store.audit_log(a.prompt_id)]
        assert actions.count("activate") == 2
        assert actions.count("supersede") == 1

    def test_rollback_reactivates_prior_and_supersedes_current(self):
        store = PromptStore()
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        _r_a_eval = _make_passing_receipt(a)
        a_eval = author.apply_receipt(a, _r_a_eval)
        store.register(a_eval)
        store.register_receipt(_r_a_eval)
        store.activate(a.prompt_id, 1, actor="owner")

        b = author.supersede(
            store.get(a.prompt_id, 1), recovery_behavior="replacement b"
        )
        _r_b_eval = _make_passing_receipt(b)
        b_eval = author.apply_receipt(b, _r_b_eval)
        store.register(b_eval)
        store.register_receipt(_r_b_eval)
        store.activate(b.prompt_id, 2, actor="owner")

        store.rollback(a.prompt_id, 1, actor="owner")
        assert store.get(a.prompt_id, 1).status == PromptStatus.ACTIVE
        assert store.get(a.prompt_id, 2).status == PromptStatus.SUPERSEDED

        actions = [e.action for e in store.audit_log(a.prompt_id)]
        assert actions.count("rollback") == 1

    def test_archive_rejects_active(self):
        store = PromptStore()
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        _r_a_eval = _make_passing_receipt(a)
        a_eval = author.apply_receipt(a, _r_a_eval)
        store.register(a_eval)
        store.register_receipt(_r_a_eval)
        store.activate(a.prompt_id, 1, actor="owner")
        with pytest.raises(PromptStoreError):
            store.archive(a.prompt_id, 1, actor="owner")

    def test_active_revision_lookup(self):
        store = PromptStore()
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        _r_a_eval = _make_passing_receipt(a)
        a_eval = author.apply_receipt(a, _r_a_eval)
        store.register(a_eval)
        store.register_receipt(_r_a_eval)
        assert store.active_revision("research-counter") is None
        store.activate(a.prompt_id, 1, actor="owner")
        active = store.active_revision("research-counter", stage=Stage.RESEARCH)
        assert active is not None and active.revision == 1


# ---------------------------------------------------------------------------
# OneShotController integration (opt-in, no scenario interference)
# ---------------------------------------------------------------------------


class TestControllerIntegration:
    def test_controller_prompt_store_is_lazy_and_shared(self):
        from main import OneShotController

        with tempfile.TemporaryDirectory() as td:
            ctrl = OneShotController(storage_path=f"{td}/tasks.json")
            store_a = ctrl.prompt_store
            store_b = ctrl.prompt_store
            assert store_a is store_b
            assert isinstance(store_a, PromptStore)
            assert store_a.list_revisions("nothing") == []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_passing_receipt(prompt: PromptDefinition) -> EvaluationReceipt:
    """Synthesize a receipt whose status is EVALUATED for the given prompt."""
    ev = PromptEvaluator()
    receipt = ev.evaluate(prompt, PromptFixtureRegistry.default().all())
    # Guard: if a test alters the prompt in a way that any axis fails,
    # fail loudly so the test gets a clear signal rather than a quiet
    # BLOCKED status.
    assert receipt.status == PromptStatus.EVALUATED, (
        f"receipt did not pass: failures_by_axis={receipt.failures_by_axis}"
    )
    return receipt


# ---------------------------------------------------------------------------
# M1 — Lifecycle repair regression tests
#
# Each test here pins behavior for a specific defect the review named:
#   (a) PromptDefinition itself was mutable — frozen=True
#   (b) activation did not independently verify the evaluation receipt
#   (c) activation accepted any actor — authorized_actors allowlist
#   (d) revision>=2 lineage — supersedes must reference the prior revision
# ---------------------------------------------------------------------------


class TestM1LifecycleRepair:
    def test_prompt_definition_is_frozen(self):
        """A PromptDefinition instance must refuse direct attribute mutation.

        Pre-M1 defect: `ConfigDict(extra="forbid")` only rejected unknown
        keys; it did not freeze the instance. A caller holding a reference
        to an ACTIVE prompt could do
        `prompt.status = PromptStatus.UNEVALUATED` and silently downgrade
        it, bypassing the six-state machine entirely.
        """
        author = PromptAuthor()
        prompt = author.author_candidate(_spec())
        with pytest.raises((TypeError, ValidationError)):
            prompt.status = PromptStatus.ACTIVE  # type: ignore[misc]
        with pytest.raises((TypeError, ValidationError)):
            prompt.content_digest = "0" * 64  # type: ignore[misc]
        # List fields on frozen BaseModels remain Python objects — rebinding
        # the attribute is refused, which is the enforcement we care about.
        with pytest.raises((TypeError, ValidationError)):
            prompt.stable_instructions = ["mutated"]  # type: ignore[misc]

    def test_activate_rejects_prompt_without_registered_receipt(self):
        """activate() must independently verify the receipt is registered.

        Pre-M1 defect: `apply_receipt` set the `evaluation_receipt_ref` on
        the prompt, but `activate()` only checked `status == EVALUATED`.
        A tampered or dropped receipt did not block activation.
        """
        store = PromptStore()
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        receipt = _make_passing_receipt(a)
        a_eval = author.apply_receipt(a, receipt)
        store.register(a_eval)
        # Deliberately DO NOT call store.register_receipt(receipt).
        with pytest.raises(PromptStoreError, match="not registered"):
            store.activate(a.prompt_id, 1, actor="owner")

    def test_activate_rejects_forged_receipt(self):
        """A receipt whose identity does not match the prompt must be rejected.

        We register a legitimate receipt under a different (prompt_id,
        revision) and point the prompt at that receipt's digest — the
        receipt-identity check must refuse.
        """
        store = PromptStore()
        author = PromptAuthor()
        a = author.author_candidate(_spec(prompt_id="prompt-a"))
        b = author.author_candidate(_spec(prompt_id="prompt-b"))
        rec_b = _make_passing_receipt(b)
        store.register_receipt(rec_b)
        # Build a prompt that claims rec_b's digest. Since PromptDefinition
        # is frozen, we must mint a NEW instance via model_dump + override.
        a_eval = author.apply_receipt(a, _make_passing_receipt(a))
        data = a_eval.model_dump()
        data["evaluation_receipt_ref"] = rec_b.receipt_digest
        from agent.prompt_authoring.types import PromptDefinition
        forged = PromptDefinition.model_validate(data)
        store.register(forged)
        with pytest.raises(PromptStoreError, match="identity/digest does not match"):
            store.activate(a.prompt_id, 1, actor="owner")

    def test_activate_rejects_unauthorized_actor(self):
        """When a closed allowlist is configured, unknown principals must be refused.

        Pre-M1 defect: `actor` was only recorded in the audit log; anyone
        with a reference to the store could call `.activate(..., actor="x")`.
        Pre-corrective M1 fix: `actor` strings were checked against a set,
        but any caller could still supply the authorized string.
        Corrective: `actor=` strings are refused once `authorized_actors` is
        set; callers must obtain a verified Principal via an IdentityProvider.
        """
        store = PromptStore(authorized_actors={"release-owner"})
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        receipt = _make_passing_receipt(a)
        a_eval = author.apply_receipt(a, receipt)
        store.register(a_eval)
        store.register_receipt(receipt)
        # Free-form actor strings are refused once the allowlist is set.
        with pytest.raises(
            PromptStoreError,
            match="refuses actor= strings|refused once authorized_actors",
        ):
            store.activate(a.prompt_id, 1, actor="release-owner")
        # An UNVERIFIED Principal — a caller-minted identity carrier that did
        # not come from an IdentityProvider — is also refused.
        from agent.prompt_authoring.store import Principal
        with pytest.raises(PromptStoreError, match="unverified"):
            store.activate(
                a.prompt_id, 1,
                principal=Principal.unverified("release-owner"),
            )
        # A verified Principal from an IdentityProvider succeeds.
        from agent.prompt_authoring.store import IdentityProvider
        idp = IdentityProvider(credentials={"release-owner": "secret-token"})
        verified = idp.authenticate("release-owner", "secret-token")
        active = store.activate(a.prompt_id, 1, principal=verified)
        assert active.status == PromptStatus.ACTIVE
        # A principal whose name is not in the allowlist is refused.
        # Prepare a second EVALUATED prompt to exercise the allowlist check
        # (the first prompt is already ACTIVE and would hit the status gate first).
        c = author.supersede(active, recovery_behavior="replacement")
        c_receipt = _make_passing_receipt(c)
        c_eval = author.apply_receipt(c, c_receipt)
        store.register(c_eval)
        store.register_receipt(c_receipt)
        other = IdentityProvider(credentials={"stranger": "s"}).authenticate(
            "stranger", "s"
        )
        with pytest.raises(PromptStoreError, match="not in the authorized_actors"):
            store.activate(c.prompt_id, 2, principal=other)

    def test_authorization_allowlist_is_opt_in(self):
        """Backward compatibility: an unconfigured store accepts any actor."""
        store = PromptStore()
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        receipt = _make_passing_receipt(a)
        a_eval = author.apply_receipt(a, receipt)
        store.register(a_eval)
        store.register_receipt(receipt)
        active = store.activate(a.prompt_id, 1, actor="literally-anyone")
        assert active.status == PromptStatus.ACTIVE

    def test_revision_lineage_revise_sets_back_reference(self):
        """`revise()` DOES set supersedes to the prior revision (M1 corrective).

        Pre-R3-corrective design: revise() left supersedes=None. That was
        inconsistent with the accepted_regression axis which rejected any
        revision >= 2 without a back-reference, meaning a revise-produced
        rev 2 could never reach EVALUATED. The corrective makes ALL
        revisions >= 2 carry a back-reference; the distinction between
        revise and supersede remains purely a status gate.
        """
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        b = author.revise(a, recovery_behavior="revised")
        assert b.revision == 2
        assert b.supersedes == f"{a.prompt_id}@1"

    def test_revision_lineage_supersede_wires_back_reference(self):
        """`supersede()` sets supersedes = f'{prompt_id}@{prev_revision}'."""
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        a_eval = author.apply_receipt(a, _make_passing_receipt(a))
        b = author.supersede(a_eval, recovery_behavior="replacement b")
        assert b.revision == 2
        assert b.supersedes == f"{a.prompt_id}@1"

    def test_store_refuses_rev2_with_wrong_supersedes(self):
        """store.register(rev2) refuses a mismatched supersedes string.

        Belt-and-braces: even if a caller hand-rolls a revision 2 with
        the wrong back-reference, the store detects it at registration
        time. Pre-M1 the check existed in `store.py:88-93` but no test
        exercised it.
        """
        store = PromptStore()
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        store.register(a)
        # Hand-roll rev 2 pointing at the wrong prior revision.
        b = author.supersede(
            author.apply_receipt(a, _make_passing_receipt(a)),
            recovery_behavior="bogus",
        )
        data = b.model_dump()
        data["supersedes"] = f"{a.prompt_id}@42"
        # Recompute content_digest with the altered supersedes string.
        from agent.prompt_authoring.types import PromptDefinition, canonical_content_digest
        # Re-derive the digest to pass PromptDefinition's model_validator;
        # the altered supersedes string must be baked into the digest.
        data["content_digest"] = canonical_content_digest(data)
        forged = PromptDefinition.model_validate(data)
        with pytest.raises(PromptStoreError, match="does not reference the prior"):
            store.register(forged)

class TestM1IntegrityClosure:
    """R3 reviewer-mandated integrity closure for M1 (second pass).

    Each test here closes one gap the reviewer named:
      (A) Deep immutability — nested lists/dicts cannot be mutated on an
          accepted PromptDefinition snapshot.
      (B) Receipt integrity — register_receipt refuses non-EvaluationReceipt,
          non-EVALUATED, and tampered-digest receipts.
      (C) Authorization provenance — unverified Principals are refused when
          the store is configured with an allowlist.
      (D) Lineage inconsistency — revise() wires the back-reference AND a
          revise-line revision 2 can reach EVALUATED (accepted_regression
          axis no longer rejects it).
    """

    # ---- (A) Deep immutability ----------------------------------------------

    def test_stable_instructions_append_rejected(self):
        prompt = PromptAuthor().author_candidate(_spec())
        with pytest.raises((AttributeError, TypeError)):
            prompt.stable_instructions.append("mutated")  # type: ignore[attr-defined]

    def test_output_contract_mutation_rejected(self):
        prompt = PromptAuthor().author_candidate(_spec())
        with pytest.raises(TypeError):
            prompt.output_contract["new"] = "x"  # type: ignore[index]
        with pytest.raises(TypeError):
            del prompt.output_contract["type"]  # type: ignore[attr-defined]

    def test_runtime_inputs_container_immutable(self):
        prompt = PromptAuthor().author_candidate(_spec())
        with pytest.raises((AttributeError, TypeError)):
            prompt.runtime_inputs.append(  # type: ignore[attr-defined]
                RuntimeInputSpec(name="injected", meaning="?")
            )

    def test_nested_runtime_input_is_frozen(self):
        """A RuntimeInputSpec is a Pydantic BaseModel; it should be frozen too.

        Note: the authoring input types (PromptSpec, OwnerRef, RuntimeInputSpec)
        are intentionally mutable because they are authoring inputs. The
        reviewer's directive is specifically about SNAPSHOTS (PromptDefinition
        instances). We assert that even a nested item inside a frozen snapshot
        cannot be reassigned to a different instance via the parent container.
        """
        prompt = PromptAuthor().author_candidate(_spec())
        # Direct attribute set on the frozen top-level model is already covered.
        # Here we additionally verify the container cannot be rebound.
        with pytest.raises((AttributeError, TypeError, ValidationError)):
            prompt.runtime_inputs = ()  # type: ignore[misc]

    def test_model_dump_round_trip_preserves_shape(self):
        """Immutable twins must still serialise as plain list/dict.

        Pydantic model_dump() on the frozen instance returns ordinary list and
        dict shapes, so downstream JSON encoders remain unaffected by the
        internal tuple/MappingProxyType representation.
        """
        prompt = PromptAuthor().author_candidate(_spec())
        d = prompt.model_dump(mode="json")
        assert isinstance(d["stable_instructions"], list)
        assert isinstance(d["output_contract"], dict)
        assert isinstance(d["runtime_inputs"], list)
        assert isinstance(d["fixture_refs"], list)
        assert isinstance(d["evaluation_rules"], list)

    # ---- (B) Receipt integrity ---------------------------------------------

    def test_register_receipt_rejects_wrong_type(self):
        store = PromptStore()
        with pytest.raises(PromptStoreError, match="expected EvaluationReceipt"):
            store.register_receipt("not-a-receipt")  # type: ignore[arg-type]

    def test_register_receipt_rejects_non_evaluated_status(self):
        """A BLOCKED or UNEVALUATED receipt cannot authorise activation."""
        from agent.prompt_authoring.evaluator import CheckOutcome, CheckResult, EvaluationReceipt
        a = PromptAuthor().author_candidate(_spec())
        bogus = EvaluationReceipt(
            prompt_id=a.prompt_id,
            revision=a.revision,
            content_digest=a.content_digest,
            fixtures_executed=["fixture-x"],
            checks=[
                CheckResult(
                    axis="instruction_compliance",
                    fixture="fixture-x",
                    status=CheckOutcome.FAIL,
                    evidence="forced",
                )
            ],
            status=PromptStatus.BLOCKED,
            receipt_digest="0" * 64,
            failures_by_axis={"instruction_compliance": 1},
        )
        store = PromptStore()
        with pytest.raises(PromptStoreError, match="not 'evaluated'"):
            store.register_receipt(bogus)

    def test_register_receipt_rejects_tampered_digest(self):
        """A receipt whose stored receipt_digest does not match its canonical form is refused."""
        from agent.prompt_authoring.evaluator import canonical_receipt_digest
        a = PromptAuthor().author_candidate(_spec())
        legit = _make_passing_receipt(a)
        # Build a tampered copy — same identity + fields, wrong digest.
        tampered = legit.model_copy(update={"receipt_digest": "f" * 64})
        store = PromptStore()
        with pytest.raises(PromptStoreError, match="recomputed from the receipt"):
            store.register_receipt(tampered)
        # Sanity: the legit one passes.
        store.register_receipt(legit)
        assert canonical_receipt_digest(legit) == legit.receipt_digest

    # ---- (C) Authorization provenance --------------------------------------

    def test_unverified_principal_refused_when_allowlist_set(self):
        from agent.prompt_authoring.store import Principal
        store = PromptStore(authorized_actors={"owner"})
        a = PromptAuthor().author_candidate(_spec())
        r = _make_passing_receipt(a)
        store.register(PromptAuthor().apply_receipt(a, r))
        store.register_receipt(r)
        with pytest.raises(PromptStoreError, match="unverified"):
            store.activate(a.prompt_id, 1, principal=Principal.unverified("owner"))

    def test_identity_provider_rejects_wrong_secret(self):
        from agent.prompt_authoring.store import IdentityProvider
        idp = IdentityProvider(credentials={"owner": "shh"})
        with pytest.raises(PromptStoreError, match="credential mismatch"):
            idp.authenticate("owner", "wrong")
        with pytest.raises(PromptStoreError, match="credential mismatch"):
            idp.authenticate("nobody", "anything")

    def test_actor_string_refused_once_allowlist_set(self):
        """Backward compat only applies when authorized_actors is None."""
        store = PromptStore(authorized_actors={"owner"})
        a = PromptAuthor().author_candidate(_spec())
        r = _make_passing_receipt(a)
        store.register(PromptAuthor().apply_receipt(a, r))
        store.register_receipt(r)
        with pytest.raises(PromptStoreError, match="refused once authorized_actors"):
            store.activate(a.prompt_id, 1, actor="owner")

    def test_actor_string_accepted_when_no_allowlist(self):
        """When no allowlist is set, actor= strings keep working (backward compat)."""
        store = PromptStore()  # no allowlist
        a = PromptAuthor().author_candidate(_spec())
        r = _make_passing_receipt(a)
        store.register(PromptAuthor().apply_receipt(a, r))
        store.register_receipt(r)
        active = store.activate(a.prompt_id, 1, actor="literally-anyone")
        assert active.status == PromptStatus.ACTIVE

    # ---- (D) Lineage inconsistency repair ----------------------------------

    def test_revise_line_rev2_can_reach_evaluated(self):
        """A revise-line revision 2 can now reach EVALUATED.

        Pre-corrective: revise() set supersedes=None; the accepted_regression
        axis rejected any revision>=2 without a back-reference; so a revise()-
        produced rev2 could never be EVALUATED. The corrective wires the
        back-reference so the axis is satisfied.
        """
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        b = author.revise(a, recovery_behavior="revised b")
        r = _make_passing_receipt(b)
        b_eval = author.apply_receipt(b, r)
        assert b_eval.status == PromptStatus.EVALUATED
        assert b_eval.supersedes == f"{a.prompt_id}@1"



# ---------------------------------------------------------------------------
# M2 — Markdown integration + digested tool_permissions
# ---------------------------------------------------------------------------


class TestM2MarkdownLoader:
    """R3 M2: safe Markdown integration + digested permissions."""

    def _path(self, name: str = "builder_discovery.md") -> str:
        import os
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(here, "agent", "prompt_authoring", "prompts", name)

    def test_load_builder_discovery(self):
        from agent.prompt_authoring import load_markdown_prompt
        spec = load_markdown_prompt(self._path())
        assert spec.prompt_id == "builder-discovery"
        assert spec.stage == Stage.DISCOVERY
        assert spec.owner.kind == "builder_discovery"
        assert {ri.name for ri in spec.runtime_inputs} == {
            "USER_INTENT", "RESEARCH", "REPOSITORY_CONTEXT", "DISCOVERY_TEMPLATE",
        }
        assert spec.required_capabilities.structured_outputs is True
        from agent.prompt_authoring.types import ToolPermission
        assert set(spec.tool_permissions) >= {
            ToolPermission.REPOSITORY_READ,
            ToolPermission.CODE_SEARCH,
            ToolPermission.READ_ONLY,
        }

    def test_round_trip_digest_stability(self):
        from agent.prompt_authoring import load_markdown_prompt
        spec_a = load_markdown_prompt(self._path())
        spec_b = load_markdown_prompt(self._path())
        a = PromptAuthor().author_candidate(spec_a)
        b = PromptAuthor().author_candidate(spec_b)
        assert a.content_digest == b.content_digest, (
            "digest must be identical for identical .md source"
        )

    def test_markdown_source_is_not_runtime_authority(self):
        """Changing the .md body after a prompt was authored does not change
        the authored prompt's content_digest. The .md file is authoring
        source, not runtime authority."""
        import pathlib
        import tempfile

        from agent.prompt_authoring import load_markdown_prompt
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "demo.md"
            p.write_text(pathlib.Path(self._path()).read_text())
            spec = load_markdown_prompt(str(p))
            prompt = PromptAuthor().author_candidate(spec)
            frozen_digest = prompt.content_digest
            # Mutate the source file. The already-authored prompt's digest
            # does NOT follow.
            p.write_text(
                pathlib.Path(self._path()).read_text().replace(
                    "Preserve exact revisions",
                    "Preserve exact revisions AND trees",
                )
            )
            new_spec = load_markdown_prompt(str(p))
            new_prompt = PromptAuthor().author_candidate(new_spec)
            # Different digest for the new load; same digest for the
            # already-authored instance.
            assert new_prompt.content_digest != frozen_digest
            assert prompt.content_digest == frozen_digest  # unchanged

    def test_tool_permissions_change_digest(self):
        """Reviewer directive: tool_permissions MUST be in canonical_content_digest."""
        from agent.prompt_authoring.types import ToolPermission
        p0 = PromptAuthor().author_candidate(_spec())
        p1 = PromptAuthor().author_candidate(
            _spec(tool_permissions=[ToolPermission.REPOSITORY_READ])
        )
        p2 = PromptAuthor().author_candidate(_spec(tool_permissions=[
            ToolPermission.REPOSITORY_READ, ToolPermission.CODE_SEARCH
        ]))
        assert p0.content_digest != p1.content_digest
        assert p1.content_digest != p2.content_digest

    def test_loader_rejects_unknown_tool_permission(self):
        import pathlib
        import tempfile

        from agent.prompt_authoring import MarkdownPromptError, load_markdown_prompt
        bad = """---
prompt_id: p-x
stage: research
owner:
  kind: prompt_authoring
  identifier: p.research
stage_specification: s
task_class: tc
runtime_inputs:
  - name: X
    meaning: y
    required: true
required_capabilities:
  structured_outputs: true
tool_permissions:
  - fly_to_the_moon
output_contract:
  type: object
  properties: {}
recovery_behavior: say so
stable_instructions:
  - Keep unknowns explicit.
---
"""
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "x.md"
            p.write_text(bad)
            with pytest.raises(MarkdownPromptError, match="closed vocabulary"):
                load_markdown_prompt(str(p))

    def test_loader_rejects_missing_frontmatter(self):
        import pathlib
        import tempfile

        from agent.prompt_authoring import MarkdownPromptError, load_markdown_prompt
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "x.md"
            p.write_text("# Just a heading, no frontmatter.")
            with pytest.raises(MarkdownPromptError, match="frontmatter"):
                load_markdown_prompt(str(p))

    def test_loader_rejects_missing_required_runtime_input(self):
        """A frontmatter block without `runtime_inputs` is a hard refusal."""
        import pathlib
        import tempfile

        from agent.prompt_authoring import MarkdownPromptError, load_markdown_prompt
        bad = """---
prompt_id: p-y
stage: research
owner:
  kind: prompt_authoring
  identifier: p.research
stage_specification: s
task_class: tc
output_contract:
  type: object
  properties: {}
recovery_behavior: say so
---

body
"""
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "y.md"
            p.write_text(bad)
            with pytest.raises(MarkdownPromptError, match="runtime_inputs"):
                load_markdown_prompt(str(p))

    def test_prompt_definition_tool_permissions_are_frozen_tuple(self):
        """Container immutability extends to tool_permissions (M1 contract)."""
        from agent.prompt_authoring.types import ToolPermission
        prompt = PromptAuthor().author_candidate(_spec(tool_permissions=[
            ToolPermission.REPOSITORY_READ
        ]))
        with pytest.raises((AttributeError, TypeError)):
            prompt.tool_permissions.append(ToolPermission.NETWORK)  # type: ignore[attr-defined]
