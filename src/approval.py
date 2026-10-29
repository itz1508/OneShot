#!/usr/bin/env python3
"""
OneShot Assignment 08: Authorization Gate

Two layers of authorization:
  1. User authorization — explicit user confirmation (model text rejected)
  2. Host-enforced execution permissions — runtime access control

Removing an invented approval stage does NOT mean removing security enforcement.
Both layers are necessary.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AuthorizationState:
    user_confirmed: bool = False
    host_authorized: bool = False
    bindings_verified: dict = field(default_factory=dict)
    model_text_rejected: bool = False
    missing_bindings: list = field(default_factory=list)


class AuthorizationGate:
    """Two-layer authorization: user confirmation + host enforcement."""

    def __init__(self, host_permissions: dict = None):
        self.state = AuthorizationState()
        self._host_permissions = host_permissions or {}

    def is_model_text(self, value: str) -> bool:
        if not isinstance(value, str):
            return False
        indicators = ["as an ai", "i think", "perhaps", "maybe", "i suggest", "it seems"]
        lower = value.lower().strip()
        return any(lower.startswith(i) for i in indicators)

    def verify_bindings(self, research_revision: str, plan_gaps_pass: bool,
                        fixtures_pass: bool, execution_context: dict) -> dict:
        bindings = {
            "research_revision": research_revision or "",
            "plan_gaps_pass": plan_gaps_pass,
            "fixtures_pass": fixtures_pass,
            "repo": execution_context.get("repo", ""),
            "branch": execution_context.get("branch", ""),
            "commit_sha": execution_context.get("commit_sha", ""),
        }
        self.state.bindings_verified = bindings
        missing = [k for k, v in bindings.items() if not v and k not in ("plan_gaps_pass", "fixtures_pass")]
        if not plan_gaps_pass:
            missing.append("plan_gaps_pass")
        if not fixtures_pass:
            missing.append("fixtures_pass")
        self.state.missing_bindings = missing
        return {"all_present": len(missing) == 0, "missing": missing, "bindings": bindings}

    def confirm_user(self, user_response: str) -> bool:
        """Layer 1: User authorization. Only explicit user input counts."""
        if self.is_model_text(user_response):
            self.state.model_text_rejected = True
            self.state.user_confirmed = False
            return False
        self.state.model_text_rejected = False
        self.state.user_confirmed = user_response.lower() in ("yes", "approve", "confirmed", "proceed", "true")
        return self.state.user_confirmed

    def check_host_permission(self, caller_id: str, required_permission: str) -> bool:
        """Layer 2: Host-enforced execution permissions."""
        caller_perms = self._host_permissions.get(caller_id, [])
        self.state.host_authorized = required_permission in caller_perms
        return self.state.host_authorized

    def set_host_permissions(self, permissions: dict):
        """Configure host permissions for callers."""
        self._host_permissions = permissions

    def can_proceed(self) -> bool:
        """Both layers required: user confirmed AND host authorized."""
        return self.state.user_confirmed and self.state.host_authorized

    def can_proceed_with_bindings(self) -> bool:
        """All three: user confirmed, host authorized, bindings present."""
        return (self.state.user_confirmed and 
                self.state.host_authorized and 
                len(self.state.missing_bindings) == 0)

    def reject(self, reason: str = ""):
        self.state.user_confirmed = False
