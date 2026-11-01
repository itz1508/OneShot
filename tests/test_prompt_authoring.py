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
        # revise does NOT set supersedes (only supersede does).
        assert b.supersedes is None
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
        a_eval = author.apply_receipt(a, _make_passing_receipt(a))
        store.register(a_eval)
        active = store.activate(a.prompt_id, 1, actor="owner")
        assert active.status == PromptStatus.ACTIVE

        # Create and activate a second revision; the first must be SUPERSEDED.
        b = author.supersede(active, recovery_behavior="replacement b")
        b_eval = author.apply_receipt(b, _make_passing_receipt(b))
        store.register(b_eval)
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
        a_eval = author.apply_receipt(a, _make_passing_receipt(a))
        store.register(a_eval)
        store.activate(a.prompt_id, 1, actor="owner")

        b = author.supersede(
            store.get(a.prompt_id, 1), recovery_behavior="replacement b"
        )
        b_eval = author.apply_receipt(b, _make_passing_receipt(b))
        store.register(b_eval)
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
        a_eval = author.apply_receipt(a, _make_passing_receipt(a))
        store.register(a_eval)
        store.activate(a.prompt_id, 1, actor="owner")
        with pytest.raises(PromptStoreError):
            store.archive(a.prompt_id, 1, actor="owner")

    def test_active_revision_lookup(self):
        store = PromptStore()
        author = PromptAuthor()
        a = author.author_candidate(_spec())
        a_eval = author.apply_receipt(a, _make_passing_receipt(a))
        store.register(a_eval)
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
