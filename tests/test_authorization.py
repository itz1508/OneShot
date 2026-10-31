#!/usr/bin/env python3
"""Tests for Authorization Gate — user confirmation + host enforcement."""
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools"))

from approval import AuthorizationGate


class TestAuthorization:
    def setup_method(self):
        self.gate = AuthorizationGate(host_permissions={"agent_01": ["execute"], "guest": ["read"]})

    def test_user_confirmation_accepted(self):
        assert self.gate.confirm_user("yes")
        assert self.gate.state.user_confirmed

    def test_model_text_rejected(self):
        assert not self.gate.confirm_user("As an AI, I think you should proceed")
        assert self.gate.state.model_text_rejected

    def test_host_permission_granted(self):
        assert self.gate.check_host_permission("agent_01", "execute")
        assert self.gate.state.host_authorized

    def test_host_permission_denied(self):
        assert not self.gate.check_host_permission("guest", "execute")
        assert not self.gate.state.host_authorized

    def test_both_layers_required(self):
        self.gate.confirm_user("yes")
        self.gate.check_host_permission("agent_01", "execute")
        assert self.gate.can_proceed()

    def test_user_only_not_enough(self):
        self.gate.confirm_user("yes")
        assert not self.gate.can_proceed()

    def test_host_only_not_enough(self):
        self.gate.check_host_permission("agent_01", "execute")
        assert not self.gate.can_proceed()

    def test_bindings_verified(self):
        result = self.gate.verify_bindings("sha123", True, True, {"repo": "url", "branch": "main", "commit_sha": "abc"})
        assert result["all_present"]

    def test_bindings_missing(self):
        result = self.gate.verify_bindings("", False, True, {})
        assert not result["all_present"]

    def test_can_proceed_with_bindings(self):
        self.gate.confirm_user("approve")
        self.gate.check_host_permission("agent_01", "execute")
        self.gate.verify_bindings("sha", True, True, {"repo": "url", "branch": "main", "commit_sha": "abc"})
        assert self.gate.can_proceed_with_bindings()
