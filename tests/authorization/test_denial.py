"""Authorization denial tests — AUTH01-AUTH16."""

import pytest

from agent.runtime.authorization import (
    AuthorizationEngine,
    AuthorizationError,
    Capability,
    EmptyGrant,
    PermissionGrant,
)


class TestDefaultDeny:
    def test_unauthorized_denied(self):
        """AUTH01: Unauthorized access denied by default."""
        engine = AuthorizationEngine(allowed_roots=("/tmp",))
        with pytest.raises(AuthorizationError):
            engine.authorize_tool("agent", Capability.WRITE, "/tmp/test")

    def test_authorized_allowed(self):
        """AUTH02: Explicitly authorized access allowed."""
        engine = AuthorizationEngine(allowed_roots=("/tmp",))
        engine.grant("agent", Capability.WRITE, "/tmp/test")
        grant = engine.authorize_tool("agent", Capability.WRITE, "/tmp/test")
        assert grant.authorized

    def test_empty_grant_denied(self):
        """AUTH03: EmptyGrant is always denied."""
        grant = EmptyGrant()
        assert not grant.authorized

    def test_revoked_permission_denied(self):
        """AUTH04: Revoked permission is denied."""
        engine = AuthorizationEngine(allowed_roots=("/tmp",))
        engine.grant("agent", Capability.READ, "/tmp")
        engine.revoke("agent", Capability.READ, "/tmp")
        with pytest.raises(AuthorizationError):
            engine.authorize_tool("agent", Capability.READ, "/tmp")

    def test_path_outside_roots_denied(self):
        """AUTH05: Path outside allowed roots denied."""
        engine = AuthorizationEngine(allowed_roots=("/tmp",))
        with pytest.raises(AuthorizationError):
            engine.check_path_safety("/etc/passwd")

    def test_path_within_roots_allowed(self, tmp_path):
        """AUTH06: Path within allowed roots allowed."""
        engine = AuthorizationEngine(allowed_roots=(str(tmp_path),))
        path = engine.check_path_safety(tmp_path / "test")
        assert path == (tmp_path / "test").resolve()

    def test_symlink_escape_is_denied_by_resolved_containment(self, tmp_path):
        root = tmp_path / "root"
        outside = tmp_path / "outside"
        root.mkdir()
        outside.mkdir()
        link = root / "link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("directory symlinks are unavailable")
        engine = AuthorizationEngine(allowed_roots=(str(root),))
        with pytest.raises(AuthorizationError, match="outside allowed roots"):
            engine.check_path_safety(link / "file.txt")

    def test_no_allowed_roots_denies_all(self):
        """AUTH07: No allowed roots denies all paths."""
        engine = AuthorizationEngine(allowed_roots=())
        with pytest.raises(AuthorizationError):
            engine.check_path_safety("/tmp/test")

    def test_is_authorized_check(self):
        """AUTH08: is_authorized returns bool without raising."""
        engine = AuthorizationEngine(allowed_roots=("/tmp",))
        assert engine.is_authorized("agent", Capability.READ, "/tmp") is False
        engine.grant("agent", Capability.READ, "/tmp")
        assert engine.is_authorized("agent", Capability.READ, "/tmp") is True

    def test_different_scope_not_authorized(self):
        """AUTH09: Grant for one scope doesn't authorize another."""
        engine = AuthorizationEngine(allowed_roots=("/tmp",))
        engine.grant("agent", Capability.WRITE, "/tmp/a")
        with pytest.raises(AuthorizationError):
            engine.authorize_tool("agent", Capability.WRITE, "/tmp/b")

    def test_different_capability_not_authorized(self):
        """AUTH10: Grant for READ doesn't authorize WRITE."""
        engine = AuthorizationEngine(allowed_roots=("/tmp",))
        engine.grant("agent", Capability.READ, "/tmp")
        with pytest.raises(AuthorizationError):
            engine.authorize_tool("agent", Capability.WRITE, "/tmp")

    def test_different_principal_not_authorized(self):
        """AUTH11: Grant for one principal doesn't authorize another."""
        engine = AuthorizationEngine(allowed_roots=("/tmp",))
        engine.grant("planner", Capability.WRITE, "/tmp")
        with pytest.raises(AuthorizationError):
            engine.authorize_tool("builder", Capability.WRITE, "/tmp")

    def test_path_traversal_blocked(self, tmp_path):
        """AUTH12: Path traversal blocked."""
        engine = AuthorizationEngine(allowed_roots=(str(tmp_path),))
        with pytest.raises(AuthorizationError):
            engine.check_path_safety(f"{tmp_path}/../../../etc/passwd")

    def test_capability_enum_values(self):
        """AUTH13: All capability types defined."""
        assert Capability.READ.value == "read"
        assert Capability.WRITE.value == "write"
        assert Capability.EXECUTE.value == "execute"
        assert Capability.SCANNER.value == "scanner"
        assert Capability.SUBPROCESS.value == "subprocess"
        assert Capability.NETWORK.value == "network"
        assert Capability.DELEGATE.value == "delegate"

    def test_permission_grant_immutable(self):
        """AUTH14: PermissionGrant is immutable."""
        grant = PermissionGrant(principal="test", capability=Capability.READ, scope="/tmp", authorized=True)
        with pytest.raises(Exception):
            grant.authorized = False

    def test_multiple_grants(self):
        """AUTH15: Multiple grants coexist."""
        engine = AuthorizationEngine(allowed_roots=("/tmp",))
        engine.grant("a", Capability.READ, "/tmp")
        engine.grant("b", Capability.WRITE, "/tmp")
        assert engine.is_authorized("a", Capability.READ, "/tmp")
        assert engine.is_authorized("b", Capability.WRITE, "/tmp")
        assert not engine.is_authorized("a", Capability.WRITE, "/tmp")
