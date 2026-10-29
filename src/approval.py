#!/usr/bin/env python3
"""
OneShot Assignment 08: User-Confirmed Approval

User retains authority over research findings and build decisions.
Approval is user-confirmed, not system-enforced. Model text is never
accepted as authorization — only explicit user confirmation counts.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ApprovalState:
    """State of build approval."""
    user_confirmed: bool = False
    bindings_verified: dict = field(default_factory=dict)
    model_text_rejected: bool = False


class ApprovalGate:
    """User-confirmed approval gate. User retains authority."""

    def __init__(self):
        self.state = ApprovalState()

    def verify_bindings(self, research_revision: str, plan_gaps_pass: bool,
                        fixtures_pass: bool, execution_context: dict) -> dict:
        """Verify all bindings are present before requesting user approval."""
        bindings = {
            "research_revision": research_revision or "",
            "plan_gaps_pass": plan_gaps_pass,
            "fixtures_pass": fixtures_pass,
            "repo": execution_context.get("repo", ""),
            "branch": execution_context.get("branch", ""),
            "commit_sha": execution_context.get("commit_sha", ""),
        }
        self.state.bindings_verified = bindings
        missing = [k for k, v in bindings.items() if not v and k != "plan_gaps_pass" and k != "fixtures_pass"]
        if not plan_gaps_pass:
            missing.append("plan_gaps_pass")
        if not fixtures_pass:
            missing.append("fixtures_pass")
        return {"all_present": len(missing) == 0, "missing": missing, "bindings": bindings}

    def is_model_text(self, value: str) -> bool:
        """Check if value appears to be model-generated text."""
        if not isinstance(value, str):
            return False
        indicators = ["as an ai", "i think", "perhaps", "maybe", "i suggest", "it seems"]
        lower = value.lower().strip()
        return any(lower.startswith(i) for i in indicators)

    def request_user_approval(self) -> dict:
        """Request approval from the user. Returns structured request."""
        return {
            "action": "request_user_approval",
            "bindings": self.state.bindings_verified,
            "message": "Please confirm to proceed with Build execution.",
        }

    def confirm(self, user_response: str) -> bool:
        """Process user confirmation. Only explicit user input counts."""
        if self.is_model_text(user_response):
            self.state.model_text_rejected = True
            self.state.user_confirmed = False
            return False
        # Explicit user confirmation (not model text)
        self.state.model_text_rejected = False
        self.state.user_confirmed = user_response.lower() in ("yes", "approve", "confirmed", "proceed", "true")
        return self.state.user_confirmed

    def can_proceed(self) -> bool:
        """Check if build can proceed (user confirmed, no model text)."""
        return self.state.user_confirmed and not self.state.model_text_rejected

    def reject(self, reason: str = ""):
        """Explicitly reject approval."""
        self.state.user_confirmed = False
