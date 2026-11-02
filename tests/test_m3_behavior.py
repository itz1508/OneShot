"""R3 M3 — executable fixtures, scripted adapter, behavior-based axes.

Reviewer directive 3:
  'Use ScriptedAdapter to verify predictable behavior, but keep
   independently authored expected results separate from recorded model
   responses. Test missing, conflicting, and malicious evidence.'
"""
from __future__ import annotations

import pytest

# Reuse the _spec helper from the main test module.
from test_prompt_authoring import _spec  # type: ignore[import-not-found]

from agent.prompt_authoring.author import PromptAuthor
from agent.prompt_authoring.behavior import (
    BEHAVIOR_AXES,
    BehaviorEvaluator,
    BehaviorReceipt,
    GoldenEvidence,
)
from agent.prompt_authoring.evaluator import CheckOutcome
from agent.prompt_authoring.fixtures import (
    PromptFixture,
    PromptFixtureKind,
    PromptFixtureRegistry,
)
from agent.prompt_authoring.runner import build_request, run_candidate
from agent.providers.base import UnsupportedCapabilityError
from agent.providers.types import ProviderConfig, UnifiedResponse
from tests._support.scripted_adapter import ScriptedAdapter, canonical_request_sha256


def _author():
    return PromptAuthor().author_candidate(_spec())


def _record(adapter, prompt, fixture, content, raw=None):
    """Register a scripted response for (prompt, fixture) and return the key."""
    req = build_request(prompt, fixture)
    resp = UnifiedResponse(
        content=content, tool_calls=[], finish_reason="stop", raw=raw or {}
    )
    return adapter.register_recording(req, resp)


class TestScriptedAdapter:
    def test_round_trip_known_recording(self):
        prompt = _author()
        fx = PromptFixtureRegistry.default().all()[0]
        adapter = ScriptedAdapter(ProviderConfig(provider="scripted", model="x"))
        _record(adapter, prompt, fx, '{"status":"ok"}')
        observed = run_candidate(prompt, fx, adapter)
        assert observed.content == '{"status":"ok"}'
        assert observed.provider == "scripted"
        assert observed.model == "x"
        assert len(observed.request_sha256) == 64

    def test_missing_recording_raises(self):
        prompt = _author()
        fx = PromptFixtureRegistry.default().all()[0]
        adapter = ScriptedAdapter(ProviderConfig(provider="scripted", model="x"))
        with pytest.raises(KeyError, match="request_sha256"):
            run_candidate(prompt, fx, adapter)

    def test_deterministic_hash(self):
        prompt = _author()
        fx = PromptFixtureRegistry.default().all()[0]
        req_a = build_request(prompt, fx)
        req_b = build_request(prompt, fx)
        assert canonical_request_sha256(req_a) == canonical_request_sha256(req_b)

    def test_capability_mismatch_is_blocked_before_call(self):
        """`required_capabilities` enforcement must FAIL CLOSED before `generate()`.

        The prompt requires structured_outputs; the scripted adapter
        advertises structured_outputs=False. The runner must refuse.
        """
        from agent.providers.types import ProviderCapabilities as C
        prompt = _author()
        fx = PromptFixtureRegistry.default().all()[0]
        adapter = ScriptedAdapter(
            ProviderConfig(provider="scripted", model="x"),
            capabilities=C(structured_outputs=False),
        )
        with pytest.raises(UnsupportedCapabilityError, match="structured_outputs"):
            run_candidate(prompt, fx, adapter)


class TestBehaviorAxes:
    def _adapter(self):
        return ScriptedAdapter(ProviderConfig(provider="scripted", model="replay"))

    def test_io_contract_pass(self):
        prompt = _author()
        fx = PromptFixture(
            name="valid-1", kind=PromptFixtureKind.VALID,
            input={"objective": "x"}, expected={}, oracle="oracle:valid",
        )
        adapter = self._adapter()
        _record(adapter, prompt, fx, '{"status":"ok","answer":"42"}')
        obs = run_candidate(prompt, fx, adapter)
        results = BehaviorEvaluator().grade(prompt, fx, obs)
        io = next(r for r in results if r.axis == "io_contract_compliance_behavior")
        assert io.status == CheckOutcome.PASS

    def test_io_contract_fails_on_unparseable(self):
        prompt = _author()
        fx = PromptFixture(
            name="valid-2", kind=PromptFixtureKind.VALID,
            input={"objective": "x"}, expected={}, oracle="oracle:valid",
        )
        adapter = self._adapter()
        _record(adapter, prompt, fx, "not json at all")
        obs = run_candidate(prompt, fx, adapter)
        results = BehaviorEvaluator().grade(prompt, fx, obs)
        io = next(r for r in results if r.axis == "io_contract_compliance_behavior")
        assert io.status == CheckOutcome.FAIL
        assert "does not parse" in io.evidence

    def test_evidence_fidelity_blocks_fabricated_refs(self):
        prompt = _author()
        fx = PromptFixture(
            name="valid-ev", kind=PromptFixtureKind.VALID,
            input={"objective": "x"}, expected={}, oracle="oracle:valid",
        )
        adapter = self._adapter()
        _record(
            adapter, prompt, fx,
            '{"status":"ok","evidence_refs":["fabricated-id"]}',
        )
        obs = run_candidate(prompt, fx, adapter)
        golden = GoldenEvidence(
            fixture_name=fx.name, allowed_evidence_ids=["real-id-1", "real-id-2"]
        )
        results = BehaviorEvaluator().grade(prompt, fx, obs, golden)
        fid = next(r for r in results if r.axis == "evidence_fidelity_behavior")
        assert fid.status == CheckOutcome.FAIL
        assert "fabricated-id" in fid.evidence

    def test_evidence_fidelity_passes_when_refs_allowed(self):
        prompt = _author()
        fx = PromptFixture(
            name="valid-ev2", kind=PromptFixtureKind.VALID,
            input={"objective": "x"}, expected={}, oracle="oracle:valid",
        )
        adapter = self._adapter()
        _record(
            adapter, prompt, fx,
            '{"status":"ok","evidence_refs":["real-id-1"]}',
        )
        obs = run_candidate(prompt, fx, adapter)
        golden = GoldenEvidence(
            fixture_name=fx.name, allowed_evidence_ids=["real-id-1", "real-id-2"]
        )
        results = BehaviorEvaluator().grade(prompt, fx, obs, golden)
        fid = next(r for r in results if r.axis == "evidence_fidelity_behavior")
        assert fid.status == CheckOutcome.PASS

    def test_unknown_preservation_blocked_fixture_requires_marker(self):
        prompt = _author()
        fx = PromptFixture(
            name="blocked-1", kind=PromptFixtureKind.BLOCKED,
            input={"objective": ""},
            expected_rejection={"marker": "BLOCKED"},
            oracle="oracle:blocked",
        )
        adapter = self._adapter()
        _record(adapter, prompt, fx, '{"status":"BLOCKED","reason":"missing"}')
        obs = run_candidate(prompt, fx, adapter)
        results = BehaviorEvaluator().grade(prompt, fx, obs)
        up = next(r for r in results if r.axis == "unknown_preservation_behavior")
        assert up.status == CheckOutcome.PASS

    def test_unknown_preservation_fails_when_marker_missing(self):
        """A BLOCKED fixture answered in-schema but without the refusal marker FAILs."""
        prompt = _author()
        fx = PromptFixture(
            name="blocked-silent", kind=PromptFixtureKind.BLOCKED,
            input={"objective": ""},
            expected_rejection={"marker": "BLOCKED"},
            oracle="oracle:blocked",
        )
        adapter = self._adapter()
        _record(adapter, prompt, fx, '{"status":"ok","answer":"made up"}')
        obs = run_candidate(prompt, fx, adapter)
        results = BehaviorEvaluator().grade(prompt, fx, obs)
        up = next(r for r in results if r.axis == "unknown_preservation_behavior")
        assert up.status == CheckOutcome.FAIL

    def test_recovery_axis_requires_recovery_marker(self):
        prompt = _author()
        fx = PromptFixture(
            name="rec-1", kind=PromptFixtureKind.RECOVERY,
            input={"objective": "retry"},
            expected={"marker": "RECOVERED"},
            oracle="oracle:recovery",
        )
        adapter = self._adapter()
        _record(adapter, prompt, fx, '{"status":"RECOVERED","note":"ok"}')
        obs = run_candidate(prompt, fx, adapter)
        results = BehaviorEvaluator().grade(prompt, fx, obs)
        rc = next(r for r in results if r.axis == "recovery_failure_behaviour_behavior")
        assert rc.status == CheckOutcome.PASS

    def test_behavior_receipt_aggregates(self):
        prompt = _author()
        adapter = self._adapter()
        fx_valid = PromptFixture(
            name="agg-ok", kind=PromptFixtureKind.VALID,
            input={"objective": "x"}, expected={}, oracle="oracle:valid",
        )
        fx_blocked = PromptFixture(
            name="agg-bad", kind=PromptFixtureKind.BLOCKED,
            input={"objective": ""},
            expected_rejection={"marker": "BLOCKED"},
            oracle="oracle:blocked",
        )
        _record(adapter, prompt, fx_valid, '{"status":"ok","evidence_refs":["x"]}')
        _record(adapter, prompt, fx_blocked, '{"status":"ok","answer":"should have refused"}')
        obs_valid = run_candidate(prompt, fx_valid, adapter)
        obs_blocked = run_candidate(prompt, fx_blocked, adapter)
        receipt = BehaviorEvaluator().grade_many(prompt, [
            (fx_valid, obs_valid, GoldenEvidence(
                fixture_name=fx_valid.name, allowed_evidence_ids=["x"]
            )),
            (fx_blocked, obs_blocked, GoldenEvidence(
                fixture_name=fx_blocked.name, refusal_marker="BLOCKED"
            )),
        ])
        assert isinstance(receipt, BehaviorReceipt)
        assert set(BEHAVIOR_AXES) == {
            "io_contract_compliance_behavior",
            "evidence_fidelity_behavior",
            "unknown_preservation_behavior",
            "recovery_failure_behaviour_behavior",
        }
        assert receipt.overall == CheckOutcome.FAIL  # the blocked fixture gets caught
        assert receipt.failures_by_axis.get("unknown_preservation_behavior") == 1

    def test_missing_evidence_treated_as_not_applicable(self):
        """When no golden evidence list is declared, the axis is NOT_APPLICABLE
        (never FAIL by default — avoids false positives on fixtures that don't
        define evidence)."""
        prompt = _author()
        fx = PromptFixture(
            name="no-golden", kind=PromptFixtureKind.VALID,
            input={"objective": "x"}, expected={}, oracle="oracle:valid",
        )
        adapter = self._adapter()
        _record(adapter, prompt, fx, '{"status":"ok","evidence_refs":["anything"]}')
        obs = run_candidate(prompt, fx, adapter)
        results = BehaviorEvaluator().grade(prompt, fx, obs, golden=None)
        fid = next(r for r in results if r.axis == "evidence_fidelity_behavior")
        assert fid.status == CheckOutcome.NOT_APPLICABLE
