"""Default-deny authorization enforcement.

Every tool, subprocess, and path access must be explicitly authorized.
No role guidance or model response can expand capabilities.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class AuthorizationError(Exception):
    pass


class Capability(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    SCANNER = "scanner"
    SUBPROCESS = "subprocess"
    NETWORK = "network"
    DELEGATE = "delegate"


class PermissionGrant(BaseModel):
    """An authorized permission grant."""

    principal: str = Field(min_length=1)
    capability: Capability
    scope: str = Field(min_length=1)
    authorized: bool = False

    model_config = {"frozen": True}


class EmptyGrant(PermissionGrant):
    """Default-deny grant — no capability authorized."""

    principal: str = "deny"
    capability: Capability = Capability.READ
    scope: str = "none"
    authorized: bool = False


class AuthorizationEngine:
    """Host-owned authorization with default-deny enforcement.

    All permissions must be explicitly granted. No permission means no access.
    Path safety checks prevent traversal, symlinks, and escapes.
    """

    def __init__(self, allowed_roots: tuple[str, ...] = ()) -> None:
        self._allowed_roots = tuple(Path(r).resolve() for r in allowed_roots)
        self._grants: dict[tuple[str, Capability, str], PermissionGrant] = {}

    def authorize_tool(
        self,
        principal: str,
        capability: Capability,
        scope: str,
    ) -> PermissionGrant:
        """Authorize a tool/action. Returns a grant or raises AuthorizationError."""
        key = (principal, capability, scope)
        grant = self._grants.get(key)
        if grant is None or not grant.authorized:
            raise AuthorizationError(f"denied: principal={principal} capability={capability} scope={scope}")
        return grant

    def grant(
        self,
        principal: str,
        capability: Capability,
        scope: str,
    ) -> PermissionGrant:
        """Explicitly grant a permission."""
        grant = PermissionGrant(
            principal=principal,
            capability=capability,
            scope=scope,
            authorized=True,
        )
        self._grants[(principal, capability, scope)] = grant
        return grant

    def revoke(
        self,
        principal: str,
        capability: Capability,
        scope: str,
    ) -> None:
        """Revoke a permission."""
        self._grants.pop((principal, capability, scope), None)

    def check_path_safety(self, path: str | Path) -> Path:
        """Check that a path is within allowed roots and has no traversal or symlink escape.

        Returns the resolved path if safe. Raises AuthorizationError otherwise.
        """
        resolved = Path(path).resolve()
        if not self._allowed_roots:
            raise AuthorizationError("no allowed roots configured")
        for root in self._allowed_roots:
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue
        raise AuthorizationError(f"path outside allowed roots: {path}")

    def is_authorized(self, principal: str, capability: Capability, scope: str) -> bool:
        """Check if a capability is authorized without raising."""
        key = (principal, capability, scope)
        grant = self._grants.get(key)
        return grant is not None and grant.authorized


class RolePolicy(BaseModel):
    """Role-based policy with allowed tools and path scopes."""

    role: str = Field(min_length=1)
    allowed_tools: frozenset[str] = Field(default_factory=frozenset)
    read_roots: tuple[Path, ...] = ()
    write_roots: tuple[Path, ...] = ()
    scan_roots: tuple[Path, ...] = ()

    model_config = {"arbitrary_types_allowed": True}


class PathAuthorizer:
    """Path-based authorization using a RolePolicy."""

    def __init__(self, policy: RolePolicy) -> None:
        self.policy = policy
        self._resolved_read = tuple(Path(r).resolve() for r in policy.read_roots)
        self._resolved_write = tuple(Path(r).resolve() for r in policy.write_roots)
        self._resolved_scan = tuple(Path(r).resolve() for r in policy.scan_roots)

    def authorize_tool(self, tool: str) -> None:
        """Authorize a tool by name. Raises AuthorizationError if not allowed."""
        if tool not in self.policy.allowed_tools:
            raise AuthorizationError(f"Tool {tool!r} not authorized for role {self.policy.role!r}")

    def authorize_write(self, path: str | Path) -> Path:
        """Authorize a write path. Returns resolved path or raises AuthorizationError."""
        resolved = Path(path).resolve()
        for root in self._resolved_write:
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue
        raise AuthorizationError(f"Write path outside allowed roots: {path}")

    def authorize_read(self, path: str | Path) -> Path:
        """Authorize a read path. Returns resolved path or raises AuthorizationError."""
        resolved = Path(path).resolve()
        for root in self._resolved_read:
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue
        raise AuthorizationError(f"Read path outside allowed roots: {path}")
