#!/usr/bin/env python3
"""Tests for user-approval enforcement in OneShotController.

The retired tools/approval.py AuthorizationGate combined four responsibilities
behind one class:

  (a) one-off user confirmation (string in/boolean out),
  (b) model-text rejection (reject "As an AI, ..." style confirmations),
  (c) host permission (role→effects map),
  (d) binding verification (sha + repo/branch/commit).

This module exercises what current OneShot source actually implements for the
first responsibility (the "approval gate" of the Builder role in the
specialist architecture). The relevant surface is OneShotController's
request_user_decision / provide_user_decision / has_pending_decision triplet
(agent/main.py:240-283), which already enforces:

  - exact revision binding (stale approvals rejected),
  - single-use consumption (duplicate approvals rejected),
  - permissible-answer whitelisting,
  - task_id scoping (approvals for other tasks rejected).

Responsibilities (b), (c), (d) have no equivalent surface in current source.
They are flagged in the ExecPlan under D1 as user-owned "restore vs new
surface" decisions, and this test file does NOT silently restore them.
Tests exercising those behaviors are retained below with explicit skip
reasons so coverage status is visible rather than hidden.
"""

from __future__ import annotations

import unittest
from pathlib import Path

# agent/ is added to sys.path by conftest.py — no manual sys.path manipulation.
from main import OneShotController


class TestUserApprovalLayer(unittest.TestCase):
    """Controller's user-approval surface (a) — the single implemented layer."""

    def setUp(self) -> None:
        self.tmp = Path(f"/tmp/oneshot_test_{id(self)}.json")
        if self.tmp.exists():
            self.tmp.unlink()
        self.ctrl = OneShotController(storage_path=str(self.tmp))
        self.task_id = self.ctrl.start_task("test request")

    def tearDown(self) -> None:
        if self.tmp.exists():
            self.tmp.unlink()

    def test_user_approval_accepted(self):
        rid = self.ctrl.request_user_decision(self.task_id, "proceed?", ["yes", "no"])
        self.assertTrue(self.ctrl.provide_user_decision(self.task_id, rid, "yes"))

    def test_user_approval_rejects_wrong_task(self):
        """Approval scoped to the task it was requested on."""
        other = self.ctrl.start_task("other request")
        rid = self.ctrl.request_user_decision(self.task_id, "proceed?", ["yes"])
        self.assertFalse(self.ctrl.provide_user_decision(other, rid, "yes"))

    def test_user_approval_rejects_duplicate_consumption(self):
        """One approval, one consumption — second attempt fails closed."""
        rid = self.ctrl.request_user_decision(self.task_id, "proceed?", ["yes"])
        self.assertTrue(self.ctrl.provide_user_decision(self.task_id, rid, "yes"))
        self.assertFalse(self.ctrl.provide_user_decision(self.task_id, rid, "yes"))

    def test_user_approval_rejects_outside_permissible_answers(self):
        """Permissible-answer whitelist enforced."""
        rid = self.ctrl.request_user_decision(self.task_id, "proceed?", ["yes", "no"])
        self.assertFalse(self.ctrl.provide_user_decision(self.task_id, rid, "maybe"))

    def test_user_approval_rejects_stale_revision(self):
        """Approval pins to task revision at request time. Later revision bump invalidates."""
        rid = self.ctrl.request_user_decision(self.task_id, "proceed?", ["yes"])
        # Bump task revision via the TaskManager directly — simulates an edit on the task
        # that happened after the approval was requested but before it was answered.
        task = self.ctrl.tm.get_task(self.task_id)
        task.metadata["revision"] = (task.metadata.get("revision", 1) or 1) + 1

        self.assertFalse(self.ctrl.provide_user_decision(self.task_id, rid, "yes"))

    def test_has_pending_decision_round_trip(self):
        """has_pending_decision reflects the queue state before and after approval."""
        self.assertIsNone(self.ctrl.has_pending_decision(self.task_id))
        rid = self.ctrl.request_user_decision(self.task_id, "proceed?", ["yes"])
        self.assertIsNotNone(self.ctrl.has_pending_decision(self.task_id))
        self.ctrl.provide_user_decision(self.task_id, rid, "yes")
        self.assertIsNone(self.ctrl.has_pending_decision(self.task_id))


class TestCapabilityMetadata(unittest.TestCase):
    """CapabilityRegistry's effect-metadata surface — distinct from authorization.

    The registry stores metadata about capabilities (owner, effects, invocation
    paths) and exposes check_effect() for lookup. The code is explicit that
    this is NOT a permission service (agent/main.py:115, 137). These tests
    pin that distinction so future callers don't mistake metadata for a gate.
    """

    def setUp(self) -> None:
        self.ctrl = OneShotController(storage_path=f"/tmp/oneshot_metadata_{id(self)}.json")

    def test_check_effect_is_lookup_only(self):
        """check_effect reports whether a capability declares an effect; it does NOT authorize."""
        # text_metrics is registered with ['read'] effect; see _register_default_capabilities.
        self.assertTrue(self.ctrl.registry.check_effect("text_metrics", "read"))
        self.assertFalse(self.ctrl.registry.check_effect("text_metrics", "external_write"))
        # A missing capability is reported as effect-absent, not an auth failure.
        self.assertFalse(self.ctrl.registry.check_effect("nonexistent", "read"))


class TestLegacyGateUnmigrated(unittest.TestCase):
    """Behaviors from the retired AuthorizationGate that have NO equivalent in current source.

    These tests are retained as explicit skips so coverage status is visible.
    Each one documents a specific capability the retired module provided that
    the current controller/registry layer does NOT. Resolving them is a
    user-owned decision tracked under ExecPlan D1.
    """

    @unittest.skip("D1: no host-permission surface in current source — ExecPlan D1.")
    def test_host_permission_role_to_effects(self):
        """AuthorizationGate.check_host_permission(actor, effect) — not implemented."""

    @unittest.skip("D1: no binding verification surface in current source — ExecPlan D1.")
    def test_binding_verification_commit_branch_repo_sha(self):
        """AuthorizationGate.verify_bindings — not implemented."""

    @unittest.skip("D1: no model-text rejection surface in current source — ExecPlan D1.")
    def test_model_text_rejected(self):
        """AuthorizationGate.confirm_user rejecting LLM-looking confirmations — not implemented."""


if __name__ == "__main__":
    unittest.main()
