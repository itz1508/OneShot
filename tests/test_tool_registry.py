"""R3 addon — Toolkit / Tools discovery.

Reviewer requirements covered by this file:
  * schema validation (invalid inputs refused at dispatch)
  * unknown-toolkit rejection
  * permission-filtering (list and dispatch share the filter)
  * discovery failure handling (unknown tool, missing permission, missing MCP connector)
  * actual dispatch integration (FUNCTION path exercised end-to-end)
  * host-native + MCP + Function tools stay distinctly typed
  * list_tools returns only PERMITTED + AVAILABLE tools
  * Discovery NEVER executes a tool
  * update_plan is advisory; update_task_progress is the durable path
"""
from __future__ import annotations

import pytest

from agent.tools_registry import (
    HostCapabilities,
    ToolDescriptor,
    ToolKind,
    ToolkitDescriptor,
    ToolRegistry,
    ToolRegistryError,
)
from agent.tools_registry.defaults import register_default_toolkits
from agent.tools_registry.types import EmptyGrant, StaticGrant


class _FakeTaskManager:
    """Minimal TaskManager stand-in — tracks revisions in-memory."""

    class _Task:
        def __init__(self, metadata):
            from types import SimpleNamespace
            self.state = SimpleNamespace(value="running")
            self.metadata = metadata

    def __init__(self):
        self._tasks: dict[str, _FakeTaskManager._Task] = {}

    def create_task(self, task_id: str, metadata: dict | None = None) -> None:
        self._tasks[task_id] = self._Task(metadata or {"revision": 1})

    def get_task(self, task_id: str):
        return self._tasks.get(task_id)

    def set_task_metadata(self, task_id, metadata, *, if_revision):
        task = self._tasks[task_id]
        current = int((task.metadata or {}).get("revision", 1))
        if current != if_revision:
            from tools.task_management import StaleRevisionError
            raise StaleRevisionError(f"if_revision={if_revision} != {current}")
        task.metadata = metadata


# ---------------------------------------------------------------------------
# Registration + discovery contract
# ---------------------------------------------------------------------------


class TestRegistrationContract:
    def test_unknown_toolkit_on_tool_registration_is_refused(self):
        reg = ToolRegistry(trust_actor_strings=True)
        with pytest.raises(ToolRegistryError, match="unknown_toolkit"):
            reg.register_function_tool(
                ToolDescriptor(
                    id="x", toolkit="nope", kind=ToolKind.FUNCTION,
                    description="d", input_schema={}, owner="t",
                ),
                lambda inputs: {},
            )

    def test_duplicate_toolkit_refused(self):
        reg = ToolRegistry(trust_actor_strings=True)
        tk = ToolkitDescriptor(id="t", description="d")
        reg.register_toolkit(tk)
        with pytest.raises(ToolRegistryError, match="duplicate_toolkit"):
            reg.register_toolkit(tk)

    def test_duplicate_tool_refused(self):
        reg = ToolRegistry(trust_actor_strings=True)
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        reg.register_function_tool(
            ToolDescriptor(
                id="x", toolkit="t", kind=ToolKind.FUNCTION,
                description="d", input_schema={}, owner="o",
            ),
            lambda inputs: {},
        )
        with pytest.raises(ToolRegistryError, match="duplicate_tool"):
            reg.register_function_tool(
                ToolDescriptor(
                    id="x", toolkit="t", kind=ToolKind.FUNCTION,
                    description="d", input_schema={}, owner="o",
                ),
                lambda inputs: {},
            )

    def test_wrong_kind_refused_on_registration_path(self):
        """Registering a HOST_NATIVE tool via register_function_tool() refuses."""
        reg = ToolRegistry(trust_actor_strings=True)
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        with pytest.raises(ToolRegistryError, match="wrong_kind"):
            reg.register_function_tool(
                ToolDescriptor(
                    id="x", toolkit="t", kind=ToolKind.HOST_NATIVE,
                    description="d", input_schema={}, owner="o",
                ),
                lambda inputs: {},
            )


# ---------------------------------------------------------------------------
# list_toolkits / list_tools permission filter
# ---------------------------------------------------------------------------


class TestDiscoveryFilter:
    def _registry(self, grant):
        reg = ToolRegistry(permission_grant=grant, trust_actor_strings=True)
        register_default_toolkits(
            reg,
            host=HostCapabilities(apply_patch=True, shell=True, update_plan=True),
            task_manager=_FakeTaskManager(),
            repo_root="/tmp",
            host_plan_sink=lambda payload: {"forwarded": True, "payload": payload},
        )
        return reg

    def test_list_toolkits_visible_set(self):
        """Caller sees toolkits they have at least one tool in; empty toolkits visible."""
        grant = StaticGrant(permissions={"caller": frozenset({"read_only"})})
        reg = self._registry(grant)
        toolkits = reg.list_toolkits("caller")
        ids = sorted(tk.id for tk in toolkits)
        # task_management + workspace have read_only-only tools; repository does not.
        assert "task_management" in ids
        assert "workspace" in ids
        assert "repository" not in ids  # requires repository_read / code_search
        assert "mcp" in ids  # empty toolkits still visible (hint to the host)

    def test_list_tools_filters_by_permission(self):
        # R3 corrective: get_task_status requires task_read; update_task_progress
        # requires task_write.
        grant = StaticGrant(permissions={
            "caller": frozenset({"read_only", "task_read", "task_write"})
        })
        reg = self._registry(grant)
        ids = {t.id for t in reg.list_tools("caller")}
        # Permitted tools:
        assert "get_task_status" in ids
        assert "update_task_progress" in ids
        assert "update_plan" in ids
        assert "read_file" in ids
        # Permissions missing -> not visible:
        assert "list_files" not in ids           # repository_read
        assert "search_sources" not in ids       # code_search
        assert "search_files" not in ids         # read_only + code_search
        assert "apply_patch" not in ids          # filesystem_write
        assert "shell" not in ids                # filesystem_write + network
        # Without task_write/task_read, task-management tools are dropped.
        grant_ro = StaticGrant(permissions={"caller": frozenset({"read_only"})})
        reg_ro = self._registry(grant_ro)
        ids_ro = {t.id for t in reg_ro.list_tools("caller")}
        assert "update_task_progress" not in ids_ro
        assert "get_task_status" not in ids_ro

    def test_list_tools_scoped_to_toolkit(self):
        grant = StaticGrant(permissions={
            "caller": frozenset({"read_only", "task_read", "task_write", "task_admin"})
        })
        reg = self._registry(grant)
        ids = {t.id for t in reg.list_tools("caller", toolkit_id="task_management")}
        assert ids == {
            "get_task_status",
            "update_task_progress",
            "adopt_task_owner",
            "update_plan",
        }

    def test_list_tools_rejects_unknown_toolkit(self):
        reg = self._registry(StaticGrant(permissions={"c": frozenset()}))
        with pytest.raises(ToolRegistryError, match="unknown_toolkit"):
            reg.list_tools("c", toolkit_id="imaginary")

    def test_empty_grant_sees_nothing(self):
        """Default EmptyGrant refuses every permission."""
        reg = ToolRegistry(permission_grant=EmptyGrant(), trust_actor_strings=True)
        register_default_toolkits(
            reg,
            host=HostCapabilities(apply_patch=False, shell=False, update_plan=False),
            task_manager=_FakeTaskManager(),
            repo_root="/tmp",
        )
        tools = reg.list_tools("anyone")
        assert tools == []  # nothing permitted
        # But toolkits are still enumerated (empty mcp + the four seeded).
        tk_ids = {tk.id for tk in reg.list_toolkits("anyone")}
        assert "mcp" in tk_ids  # empty toolkit remains visible to the host


# ---------------------------------------------------------------------------
# Host capabilities gate host-native + update_plan registration
# ---------------------------------------------------------------------------


class TestHostCapabilityGating:
    def test_apply_patch_shell_omitted_without_host_support(self):
        reg = ToolRegistry(permission_grant=StaticGrant(permissions={
                "owner": frozenset({
                    "read_only", "code_search", "repository_read",
                    "filesystem_write", "network",
                    "task_read", "task_write", "task_admin",
                }),
            }),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg,
            host=HostCapabilities(apply_patch=False, shell=False, update_plan=False),
            task_manager=_FakeTaskManager(),
            repo_root="/tmp",
        )
        ids = {t.id for t in reg.list_tools("owner")}
        assert "apply_patch" not in ids
        assert "shell" not in ids
        assert "update_plan" not in ids
        # These stay in regardless.
        assert "get_task_status" in ids
        assert "update_task_progress" in ids
        assert "read_file" in ids

    def test_host_native_tools_tagged_distinctly(self):
        reg = ToolRegistry(permission_grant=StaticGrant(permissions={
                "o": frozenset({"filesystem_write", "network"})
            }),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg,
            host=HostCapabilities(apply_patch=True, shell=True),
            task_manager=_FakeTaskManager(),
            repo_root="/tmp",
        )
        kinds = {t.id: t.kind for t in reg.list_tools("o")}
        assert kinds["apply_patch"] == ToolKind.HOST_NATIVE
        assert kinds["shell"] == ToolKind.HOST_NATIVE


# ---------------------------------------------------------------------------
# Dispatch — the authorized boundary
# ---------------------------------------------------------------------------


class TestDispatchBoundary:
    def _registry(self, grant):
        reg = ToolRegistry(permission_grant=grant, trust_actor_strings=True)
        register_default_toolkits(
            reg,
            host=HostCapabilities(apply_patch=True, shell=True, update_plan=True),
            task_manager=self._tm,
            repo_root="/tmp",
            host_plan_sink=lambda payload: {"forwarded": True, "payload": payload},
        )
        return reg

    def setup_method(self):
        self._tm = _FakeTaskManager()
        # R3 corrective (C2): tasks carry an owner for update_task_progress.
        self._tm.create_task("tid-1", {"revision": 1, "stage": "plan", "owner": "o"})

    def test_dispatch_function_tool_round_trip(self):
        reg = self._registry(StaticGrant(permissions={"o": frozenset({"task_read"})}))
        out = reg.dispatch("o", "get_task_status", {"task_id": "tid-1"})
        assert out["found"] is True
        assert out["task_id"] == "tid-1"
        assert out["state"] == "running"
        assert out["metadata_revision"] == 1
        assert out["stage"] == "plan"

    def test_dispatch_refuses_unknown_tool(self):
        reg = self._registry(StaticGrant(permissions={"o": frozenset({"read_only"})}))
        with pytest.raises(ToolRegistryError, match="unknown_tool"):
            reg.dispatch("o", "nope", {})

    def test_dispatch_refuses_without_permission(self):
        """Visibility == dispatchability: caller without the right grant cannot dispatch."""
        reg = self._registry(StaticGrant(permissions={"o": frozenset()}))
        # The caller has no permissions, so even a tool whose required_permissions
        # is a strict subset of what the DEFAULT grant would have is refused.
        with pytest.raises(ToolRegistryError, match="unknown_tool"):
            reg.dispatch("o", "get_task_status", {"task_id": "tid-1"})

    def test_dispatch_schema_validation_missing_required(self):
        reg = self._registry(StaticGrant(permissions={"o": frozenset({"task_read"})}))
        with pytest.raises(ToolRegistryError, match="invalid_input"):
            reg.dispatch("o", "get_task_status", {})  # missing task_id

    def test_dispatch_host_native_refused(self):
        """HOST_NATIVE tools: discoverable, but dispatch is NOT the registry's job."""
        reg = self._registry(StaticGrant(permissions={
            "o": frozenset({"filesystem_write", "network"})
        }))
        with pytest.raises(ToolRegistryError, match="host_native_dispatch"):
            reg.dispatch("o", "shell", {"command": "echo hi"})

    def test_update_task_progress_writes_to_task_manager(self):
        reg = self._registry(
            StaticGrant(permissions={"o": frozenset({"read_only", "task_write"})})
        )
        out = reg.dispatch(
            "o", "update_task_progress",
            {"task_id": "tid-1", "progress_note": "half-way", "if_revision": 1},
        )
        assert out["new_revision"] == 2
        assert out["owner"] == "o"
        task = self._tm.get_task("tid-1")
        assert task.metadata["revision"] == 2
        trail = task.metadata.get("progress_trail", [])
        assert len(trail) == 1
        assert trail[0]["note"] == "half-way"
        assert trail[0]["actor"] == "o"

    def test_update_plan_is_advisory_only(self):
        """update_plan forwards to host_plan_sink; preserves ownership boundary."""
        reg = self._registry(
            StaticGrant(permissions={"o": frozenset({"read_only", "task_write"})})
        )
        before = self._tm.get_task("tid-1").metadata["revision"]
        out = reg.dispatch(
            "o", "update_plan",
            {"task_id": "tid-1", "step": "sketch", "note": "advisory only"},
        )
        after = self._tm.get_task("tid-1").metadata["revision"]
        assert before == after  # TaskManager state unchanged
        assert out["advisory"] is True
        # host_plan_sink returns {"forwarded": True, "payload": …} per the
        # fixture in _registry(). Confirm the registry forwarded verbatim.
        assert out["host_return"]["forwarded"] is True
        assert out["host_return"]["payload"]["step"] == "sketch"


# ---------------------------------------------------------------------------
# MCP tool category: registration, dispatch forwarding, missing connector
# ---------------------------------------------------------------------------


class TestMCPTools:
    def test_mcp_tool_registration_requires_connector(self):
        reg = ToolRegistry(trust_actor_strings=True)
        reg.register_toolkit(ToolkitDescriptor(id="mcp", description="d"))
        with pytest.raises(ToolRegistryError, match="invalid_mcp_connector"):
            reg.register_mcp_tool(
                ToolDescriptor(
                    id="x", toolkit="mcp", kind=ToolKind.MCP,
                    description="d", input_schema={}, owner="o",
                ),
                object(),  # no .invoke
            )

    def test_mcp_dispatch_forwards_to_connector(self):
        class FakeConnector:
            def __init__(self):
                self.calls = []

            def invoke(self, tool_id, inputs):
                self.calls.append((tool_id, inputs))
                return {"ok": True, "tool": tool_id, "inputs": inputs}

        reg = ToolRegistry(permission_grant=StaticGrant(permissions={"o": frozenset({"mcp"})}),
            trust_actor_strings=True,
        )
        reg.register_toolkit(ToolkitDescriptor(id="mcp", description="d"))
        connector = FakeConnector()
        reg.register_mcp_tool(
            ToolDescriptor(
                id="mcp.calc.add",
                toolkit="mcp",
                kind=ToolKind.MCP,
                description="add two ints",
                input_schema={
                    "type": "object",
                    "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                    "required": ["a", "b"],
                },
                owner="(mcp connector)",
                effects=("read",),
                required_permissions=("mcp",),
            ),
            connector,
        )
        out = reg.dispatch("o", "mcp.calc.add", {"a": 1, "b": 2})
        assert out == {"ok": True, "tool": "mcp.calc.add", "inputs": {"a": 1, "b": 2}}
        assert connector.calls == [("mcp.calc.add", {"a": 1, "b": 2})]

    def test_mcp_tool_discoverable_only_with_mcp_permission(self):
        class FakeConnector:
            def invoke(self, tool_id, inputs):
                return {}

        reg = ToolRegistry(permission_grant=StaticGrant(permissions={
                "with-mcp": frozenset({"mcp"}),
                "without-mcp": frozenset(),
            }),
            trust_actor_strings=True,
        )
        reg.register_toolkit(ToolkitDescriptor(id="mcp", description="d"))
        reg.register_mcp_tool(
            ToolDescriptor(
                id="mcp.x", toolkit="mcp", kind=ToolKind.MCP,
                description="d", input_schema={}, owner="o",
                required_permissions=("mcp",),
            ),
            FakeConnector(),
        )
        assert {t.id for t in reg.list_tools("with-mcp")} == {"mcp.x"}
        assert reg.list_tools("without-mcp") == []


# ---------------------------------------------------------------------------
# Availability — a tool marked unavailable is dropped from BOTH discovery
# and dispatch, as a single filter.
# ---------------------------------------------------------------------------


class TestAvailabilityFilter:
    def test_unavailable_tool_dropped(self):
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={"o": frozenset({"read_only"})}),
            trust_actor_strings=True,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        reg.register_function_tool(
            ToolDescriptor(
                id="x", toolkit="t", kind=ToolKind.FUNCTION,
                description="d", input_schema={}, owner="o",
                available=False,
                required_permissions=("read_only",),
            ),
            lambda inputs: {"should": "never"},
        )
        assert reg.list_tools("o") == []
        with pytest.raises(ToolRegistryError, match="unknown_tool"):
            reg.dispatch("o", "x")

    def test_discovery_does_not_execute(self):
        """Discovery is read-only — a tool whose impl would raise is still listable."""
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={"o": frozenset({"read_only"})}),
            trust_actor_strings=True,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))

        calls = []

        def bomb(inputs):
            calls.append(inputs)
            raise RuntimeError("should never run")

        reg.register_function_tool(
            ToolDescriptor(
                id="x", toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={"type": "object", "properties": {}},
                owner="o",
                required_permissions=("read_only",),
            ),
            bomb,
        )
        # Discovery runs with no side effects.
        tools = reg.list_tools("o")
        assert len(tools) == 1
        assert tools[0].id == "x"
        assert calls == []


# ---------------------------------------------------------------------------
# R3 corrective — authenticated Principal gating (C1)
# ---------------------------------------------------------------------------


class TestPrincipalGating:
    """Verifies ToolRegistry now trusts the M1 Principal rather than caller strings."""

    def _reg(self):
        from agent.prompt_authoring.store import Principal  # noqa: F401
        return ToolRegistry(
            permission_grant=StaticGrant(permissions={"o": frozenset({"read_only"})}),
        )  # trust_actor_strings defaults to False — production contract

    def _bootstrap(self, reg):
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        reg.register_function_tool(
            ToolDescriptor(
                id="x", toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={"type": "object", "properties": {}},
                owner="o",
                required_permissions=("read_only",),
            ),
            lambda inputs: {"out": "ok"},
        )

    def test_bare_string_refused(self):
        reg = self._reg()
        self._bootstrap(reg)
        with pytest.raises(ToolRegistryError, match="untrusted_identity"):
            reg.list_toolkits("o")
        with pytest.raises(ToolRegistryError, match="untrusted_identity"):
            reg.list_tools("o")
        with pytest.raises(ToolRegistryError, match="untrusted_identity"):
            reg.dispatch("o", "x")

    def test_unverified_principal_refused(self):
        from agent.prompt_authoring.store import Principal
        reg = self._reg()
        self._bootstrap(reg)
        with pytest.raises(ToolRegistryError, match="untrusted_identity"):
            reg.list_tools(Principal.unverified("o"))

    def test_verified_principal_accepted(self):
        """R3-corrective reviewer directive #1: Principals must carry the
        registry's host_token. Only `registry.identity_provider(...)` produces
        a Principal the registry trusts."""
        reg = self._reg()
        self._bootstrap(reg)
        idp = reg.identity_provider(credentials={"o": "s"})
        p = idp.authenticate("o", "s")
        tools = reg.list_tools(p)
        assert [t.id for t in tools] == ["x"]
        assert reg.dispatch(p, "x") == {"out": "ok"}

    def test_independently_minted_identity_refused(self):
        """A Principal from a BARE IdentityProvider (no host_token) is refused."""
        from agent.prompt_authoring.store import IdentityProvider
        reg = self._reg()
        self._bootstrap(reg)
        rogue_idp = IdentityProvider(credentials={"o": "s"})  # no issuer_token
        rogue_principal = rogue_idp.authenticate("o", "s")
        with pytest.raises(ToolRegistryError, match="different host"):
            reg.list_tools(rogue_principal)

    def test_cross_registry_identity_refused(self):
        """A Principal from registry A cannot authenticate against registry B."""
        reg_a = self._reg()
        self._bootstrap(reg_a)
        reg_b = self._reg()
        self._bootstrap(reg_b)
        p_a = reg_a.identity_provider(credentials={"o": "s"}).authenticate("o", "s")
        # Works on A.
        assert reg_a.list_tools(p_a)
        # Refused on B — different host_token.
        with pytest.raises(ToolRegistryError, match="different host"):
            reg_b.list_tools(p_a)


# ---------------------------------------------------------------------------
# R3 corrective — unauthorized write + task ownership (C2)
# ---------------------------------------------------------------------------


class TestUpdateTaskProgressContract:
    def _reg_with_owner(self, owner, perms):
        tm = _FakeTaskManager()
        tm.create_task("tid-x", {"revision": 1, "stage": "plan", "owner": owner})
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "alice": frozenset(perms),
                "bob": frozenset(perms),
            }),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg,
            host=HostCapabilities(),
            task_manager=tm,
            repo_root=None,
        )
        return reg, tm

    def test_read_only_without_task_write_cannot_see_update_task_progress(self):
        reg, _ = self._reg_with_owner("alice", {"read_only"})
        ids = {t.id for t in reg.list_tools("alice")}
        assert "update_task_progress" not in ids

    def test_task_write_without_ownership_refused(self):
        reg, _ = self._reg_with_owner("alice", {"task_write"})
        with pytest.raises(PermissionError, match="owned by 'alice', not 'bob'"):
            reg.dispatch("bob", "update_task_progress", {
                "task_id": "tid-x",
                "progress_note": "attempt",
                "if_revision": 1,
            })

    def test_stale_if_revision_refused(self):
        reg, _ = self._reg_with_owner("alice", {"task_write"})
        with pytest.raises(PermissionError, match="if_revision=99"):
            reg.dispatch("alice", "update_task_progress", {
                "task_id": "tid-x",
                "progress_note": "attempt",
                "if_revision": 99,
            })

    def test_update_task_progress_refuses_ownerless_task(self):
        """R3-corrective #5: update_task_progress no longer adopts ownership.

        A legacy owner-less task must be adopted via `adopt_task_owner`
        (requires task_admin) before any progress write.
        """
        tm = _FakeTaskManager()
        tm.create_task("legacy", {"revision": 1, "stage": "plan"})
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "alice": frozenset({"task_write"}),
            }),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg, host=HostCapabilities(), task_manager=tm, repo_root=None,
        )
        with pytest.raises(PermissionError, match="no recorded owner"):
            reg.dispatch("alice", "update_task_progress", {
                "task_id": "legacy",
                "progress_note": "first write",
                "if_revision": 1,
            })

    def test_adopt_task_owner_requires_task_admin(self):
        """R3-corrective #5: owner adoption lives behind task_admin."""
        tm = _FakeTaskManager()
        tm.create_task("legacy", {"revision": 1, "stage": "plan"})
        # Caller with task_write but NO task_admin cannot even see adopt_task_owner.
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "alice": frozenset({"task_write"}),
            }),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg, host=HostCapabilities(), task_manager=tm, repo_root=None,
        )
        with pytest.raises(ToolRegistryError, match="unknown_tool"):
            reg.dispatch("alice", "adopt_task_owner", {
                "task_id": "legacy",
                "new_owner": "alice",
                "if_revision": 1,
            })

    def test_adopt_task_owner_assigns_owner(self):
        """A task_admin caller can assign an owner (which may be another identity)."""
        tm = _FakeTaskManager()
        tm.create_task("legacy", {"revision": 1, "stage": "plan"})
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "admin": frozenset({"task_admin"}),
            }),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg, host=HostCapabilities(), task_manager=tm, repo_root=None,
        )
        out = reg.dispatch("admin", "adopt_task_owner", {
            "task_id": "legacy",
            "new_owner": "alice",  # admin assigns Alice as owner
            "if_revision": 1,
        })
        assert out["owner"] == "alice"
        assert out["assigned_by"] == "admin"
        assert tm.get_task("legacy").metadata["owner"] == "alice"
        # Second adoption is refused — owner already assigned.
        with pytest.raises(PermissionError, match="already has owner"):
            reg.dispatch("admin", "adopt_task_owner", {
                "task_id": "legacy",
                "new_owner": "bob",
                "if_revision": 2,
            })


# ---------------------------------------------------------------------------
# R3 corrective — deny-policy + symlink enforcement on read_file / search_files
# ---------------------------------------------------------------------------


class TestWorkspaceSafety:
    def _tmp_registry(self, tmp_path, allow_perms):
        import json
        # Minimal .agents/settings.json with deny policy
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        (agents_dir / "settings.json").write_text(json.dumps({
            "permissions": {
                "deny": [
                    "Read(./**/dist/**/*)",
                    "Read(./**/*.generated.*)",
                ]
            }
        }))
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={"o": frozenset(allow_perms)}),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg,
            host=HostCapabilities(),
            task_manager=_FakeTaskManager(),
            repo_root=str(tmp_path),
        )
        return reg

    def test_read_file_denied_path_refused(self, tmp_path):
        (tmp_path / "dist").mkdir()
        (tmp_path / "dist" / "x.js").write_text("secret")
        reg = self._tmp_registry(tmp_path, {"read_only"})
        with pytest.raises(PermissionError, match="deny policy"):
            reg.dispatch("o", "read_file", {"path": "dist/x.js"})

    def test_read_file_generated_pattern_refused(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "schema.generated.ts").write_text("generated")
        reg = self._tmp_registry(tmp_path, {"read_only"})
        with pytest.raises(PermissionError, match="deny policy"):
            reg.dispatch("o", "read_file", {"path": "src/schema.generated.ts"})

    def test_read_file_escaped_root_refused(self, tmp_path):
        reg = self._tmp_registry(tmp_path, {"read_only"})
        with pytest.raises(PermissionError, match="escapes workspace root"):
            reg.dispatch("o", "read_file", {"path": "../etc/passwd"})

    def test_read_file_symlink_refused(self, tmp_path):
        import os
        (tmp_path / "safe.txt").write_text("ok")
        os.symlink(tmp_path / "safe.txt", tmp_path / "linked.txt")
        reg = self._tmp_registry(tmp_path, {"read_only"})
        with pytest.raises(PermissionError, match="crosses a symlink"):
            reg.dispatch("o", "read_file", {"path": "linked.txt"})

    def test_search_files_excludes_denied(self, tmp_path):
        (tmp_path / "dist").mkdir()
        (tmp_path / "dist" / "x.txt").write_text("needle in haystack")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "y.txt").write_text("needle in haystack")
        reg = self._tmp_registry(tmp_path, {"read_only", "code_search"})
        out = reg.dispatch("o", "search_files", {"pattern": "needle"})
        paths = {m["path"] for m in out["matches"]}
        assert "src/y.txt" in paths
        assert all("dist/" not in p for p in paths)

    def test_search_files_redacts_secrets(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "cfg.txt").write_text("api = sk-abcdefghijklmnopqrstuvwxyz123456\n")
        reg = self._tmp_registry(tmp_path, {"read_only", "code_search"})
        out = reg.dispatch("o", "search_files", {"pattern": "api"})
        assert out["matches"]
        for m in out["matches"]:
            assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in m["excerpt"]
            assert "<REDACTED>" in m["excerpt"]


# ---------------------------------------------------------------------------
# R3 corrective — search_sources dispatch (H1)
# ---------------------------------------------------------------------------


class TestSearchSourcesDispatch:
    def test_search_sources_by_name(self):
        import pathlib
        # Use the actual OneShot repo as the workspace — it has agent/, tools/, etc.
        repo = str(pathlib.Path(__file__).resolve().parent.parent)
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "o": frozenset({"code_search"}),
            }),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg,
            host=HostCapabilities(),
            task_manager=_FakeTaskManager(),
            repo_root=repo,
        )
        # SearchSources.search_by_pattern uses substring matching, not glob.
        out = reg.dispatch("o", "search_sources", {"pattern": "test_tool_registry"})
        assert out["kind"] == "name"
        assert any("test_tool_registry" in m for m in out["matches"])


# ---------------------------------------------------------------------------
# R3 corrective — full schema validation (H2)
# ---------------------------------------------------------------------------


class TestFullSchemaValidation:
    def test_invalid_schema_declared_by_tool_rejected_at_dispatch(self):
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={"o": frozenset()}),
            trust_actor_strings=True,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        # Invalid JSON Schema: `type` must be string or list, not int.
        reg.register_function_tool(
            ToolDescriptor(
                id="broken", toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={"type": 42},
                owner="o",
            ),
            lambda inputs: {},
        )
        with pytest.raises(ToolRegistryError, match="invalid_schema"):
            reg.dispatch("o", "broken", {})

    def test_rich_schema_type_check(self):
        """Full jsonschema catches type mismatches, not just missing keys."""
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={"o": frozenset()}),
            trust_actor_strings=True,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        reg.register_function_tool(
            ToolDescriptor(
                id="strict", toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer", "minimum": 0}
                    },
                    "required": ["count"],
                },
                owner="o",
            ),
            lambda inputs: {"count": inputs["count"]},
        )
        with pytest.raises(ToolRegistryError, match="invalid_input"):
            reg.dispatch("o", "strict", {"count": "not an int"})
        with pytest.raises(ToolRegistryError, match="invalid_input"):
            reg.dispatch("o", "strict", {"count": -1})
        assert reg.dispatch("o", "strict", {"count": 5}) == {"count": 5}


# ---------------------------------------------------------------------------
# R3 corrective — host-native tools: discoverable != dispatchable (M2)
# ---------------------------------------------------------------------------


class TestHostNativeDispatchability:
    def test_host_native_marked_not_dispatchable_in_registry(self):
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "o": frozenset({"filesystem_write", "network"})
            }),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg,
            host=HostCapabilities(apply_patch=True, shell=True),
            task_manager=_FakeTaskManager(),
            repo_root="/tmp",
        )
        tools = {t.id: t for t in reg.list_tools("o")}
        assert tools["apply_patch"].dispatchable_in_registry is False
        assert tools["shell"].dispatchable_in_registry is False

    def test_function_tool_still_dispatchable_flag_true(self):
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "o": frozenset({"read_only", "task_write"}),
            }),
            trust_actor_strings=True,
        )
        tm = _FakeTaskManager()
        tm.create_task("t", {"revision": 1, "owner": "o"})
        register_default_toolkits(
            reg,
            host=HostCapabilities(),
            task_manager=tm,
            repo_root=None,
        )
        for t in reg.list_tools("o"):
            if t.kind == ToolKind.FUNCTION:
                assert t.dispatchable_in_registry is True


# ---------------------------------------------------------------------------
# R3 corrective (round 2) — fail-closed, concurrent, restart, cross-identity
# ---------------------------------------------------------------------------


class TestPolicyLoadFailsClosed:
    """Reviewer directive #2: malformed deny policy must fail closed."""

    def _reg(self, tmp_path):
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={"o": frozenset({"read_only"})}),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg,
            host=HostCapabilities(),
            task_manager=_FakeTaskManager(),
            repo_root=str(tmp_path),
        )
        return reg

    def test_missing_policy_file_allows_reads(self, tmp_path):
        (tmp_path / "safe.txt").write_text("ok")
        reg = self._reg(tmp_path)
        out = reg.dispatch("o", "read_file", {"path": "safe.txt"})
        assert out["found"] is True

    def test_malformed_policy_denies_all(self, tmp_path):
        agents = tmp_path / ".agents"
        agents.mkdir()
        (agents / "settings.json").write_text("{ not valid json")
        (tmp_path / "safe.txt").write_text("ok")
        # Clear the lru_cache so this test's policy actually loads.
        from agent.tools_registry.defaults import _deny_patterns
        _deny_patterns.cache_clear()
        reg = self._reg(tmp_path)
        with pytest.raises(PermissionError, match="deny policy"):
            reg.dispatch("o", "read_file", {"path": "safe.txt"})

    def test_wrong_type_policy_denies_all(self, tmp_path):
        agents = tmp_path / ".agents"
        agents.mkdir()
        (agents / "settings.json").write_text('{"permissions": {"deny": "not-a-list"}}')
        (tmp_path / "safe.txt").write_text("ok")
        from agent.tools_registry.defaults import _deny_patterns
        _deny_patterns.cache_clear()
        reg = self._reg(tmp_path)
        with pytest.raises(PermissionError, match="deny policy"):
            reg.dispatch("o", "read_file", {"path": "safe.txt"})


class TestConsistentRepoAndListFileSafety:
    """Reviewer directive #3: list_files + search_sources also honour deny policy."""

    def _reg(self, tmp_path, perms):
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={"o": frozenset(perms)}),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg,
            host=HostCapabilities(),
            task_manager=_FakeTaskManager(),
            repo_root=str(tmp_path),
        )
        return reg

    def _write_dist_and_safe(self, tmp_path):
        import json
        agents = tmp_path / ".agents"
        agents.mkdir()
        (agents / "settings.json").write_text(json.dumps({
            "permissions": {"deny": ["Read(./**/dist/**/*)"]}
        }))
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "ok.py").write_text("print('ok')\n")
        (tmp_path / "dist").mkdir()
        (tmp_path / "dist" / "bundle.js").write_text("danger")
        # Clear cache so the policy loads for this workspace.
        from agent.tools_registry.defaults import _deny_patterns
        _deny_patterns.cache_clear()

    def test_list_files_filters_denied(self, tmp_path):
        self._write_dist_and_safe(tmp_path)
        # Need to initialise git in tmp_path so SearchSources (git ls-tree) works.
        import subprocess
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "-c", "user.email=x@y",
             "-c", "user.name=x", "commit", "-q", "-m", "init"],
            check=True,
        )
        reg = self._reg(tmp_path, {"repository_read"})
        out = reg.dispatch("o", "list_files", {})
        files = set(out["files"])
        assert "src/ok.py" in files
        assert all("dist/" not in f for f in files)
        assert out["filtered_out"] >= 1

    def test_search_sources_filters_denied(self, tmp_path):
        import subprocess
        self._write_dist_and_safe(tmp_path)
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "-c", "user.email=x@y",
             "-c", "user.name=x", "commit", "-q", "-m", "init"],
            check=True,
        )
        reg = self._reg(tmp_path, {"code_search"})
        out = reg.dispatch("o", "search_sources", {"pattern": "bundle", "kind": "name"})
        assert all("dist/" not in m for m in out["matches"])


class TestConcurrentUpdateProgress:
    """Reviewer directive #8: concurrent writes with revision checks."""

    def test_cas_second_write_refused(self):
        """Two writers against the same revision — only the first wins."""
        tm = _FakeTaskManager()
        tm.create_task("t1", {"revision": 1, "stage": "plan", "owner": "alice"})
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "alice": frozenset({"task_write"}),
            }),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg, host=HostCapabilities(), task_manager=tm, repo_root=None,
        )
        # First writer at if_revision=1 succeeds; task bumps to revision=2.
        out = reg.dispatch("alice", "update_task_progress", {
            "task_id": "t1", "progress_note": "first", "if_revision": 1,
        })
        assert out["new_revision"] == 2
        # Second writer still thinks revision=1 — stale CAS.
        with pytest.raises(PermissionError, match="does not match committed"):
            reg.dispatch("alice", "update_task_progress", {
                "task_id": "t1", "progress_note": "second", "if_revision": 1,
            })

    def test_if_revision_required(self):
        """R3-corrective #6: if_revision has no fallback — the schema enforces it."""
        tm = _FakeTaskManager()
        tm.create_task("t1", {"revision": 1, "stage": "plan", "owner": "alice"})
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "alice": frozenset({"task_write"}),
            }),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg, host=HostCapabilities(), task_manager=tm, repo_root=None,
        )
        with pytest.raises(ToolRegistryError, match="invalid_input"):
            reg.dispatch("alice", "update_task_progress", {
                "task_id": "t1", "progress_note": "no revision",
            })


class TestRealTaskManagerPersistence:
    """Reviewer directive #6: verify real TaskManager, including restart recovery."""

    def test_update_task_progress_persists_across_restart(self, tmp_path):
        """Write via a real TaskManager, open a fresh TaskManager, trail persists."""
        from tools.task_management import TaskManager
        snapshot = tmp_path / "tasks.json"
        tm = TaskManager(storage_path=str(snapshot))
        # Create a task that we own.
        task = tm.create_task(metadata={"revision": 1, "stage": "plan", "owner": "alice"})
        task_id = str(task.task_id)
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "alice": frozenset({"task_write"}),
            }),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg, host=HostCapabilities(), task_manager=tm, repo_root=None,
        )
        out = reg.dispatch("alice", "update_task_progress", {
            "task_id": task_id,
            "progress_note": "crossing restart",
            "if_revision": 1,
        })
        assert out["new_revision"] == 2
        # Restart: a brand-new TaskManager points at the same snapshot.
        tm2 = TaskManager(storage_path=str(snapshot))
        task2 = tm2.get_task(task_id)
        assert task2 is not None
        trail = task2.metadata.get("progress_trail", [])
        assert len(trail) == 1
        assert trail[0]["note"] == "crossing restart"
        assert task2.metadata["revision"] == 2
        assert task2.metadata["owner"] == "alice"

    def test_adopt_task_owner_persists_across_restart(self, tmp_path):
        from tools.task_management import TaskManager
        snapshot = tmp_path / "tasks.json"
        tm = TaskManager(storage_path=str(snapshot))
        task = tm.create_task(metadata={"revision": 1, "stage": "plan"})
        task_id = str(task.task_id)
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "admin": frozenset({"task_admin"}),
            }),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg, host=HostCapabilities(), task_manager=tm, repo_root=None,
        )
        reg.dispatch("admin", "adopt_task_owner", {
            "task_id": task_id,
            "new_owner": "alice",
            "if_revision": 1,
        })
        # Fresh TaskManager reads the owner back.
        tm2 = TaskManager(storage_path=str(snapshot))
        task2 = tm2.get_task(task_id)
        assert task2.metadata["owner"] == "alice"


class TestTaskReadACL:
    """Reviewer directive #4: task-level ACL for reads."""

    def _reg(self, tm, perms):
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions=perms),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg, host=HostCapabilities(), task_manager=tm, repo_root=None,
        )
        return reg

    def test_owner_sees_own_task(self):
        tm = _FakeTaskManager()
        tm.create_task("t", {"revision": 1, "owner": "alice", "stage": "plan"})
        reg = self._reg(tm, {"alice": frozenset({"task_read"})})
        out = reg.dispatch("alice", "get_task_status", {"task_id": "t"})
        assert out["found"] is True
        assert out["owner"] == "alice"

    def test_non_owner_sees_not_found_by_default(self):
        """Owner mismatch is opaque unless cross_owner=True is supplied."""
        tm = _FakeTaskManager()
        tm.create_task("t", {"revision": 1, "owner": "alice", "stage": "plan"})
        reg = self._reg(tm, {"bob": frozenset({"task_read"})})
        out = reg.dispatch("bob", "get_task_status", {"task_id": "t"})
        assert out == {"found": False, "task_id": "t"}

    def test_cross_owner_opt_in_reveals_task(self):
        tm = _FakeTaskManager()
        tm.create_task("t", {"revision": 1, "owner": "alice", "stage": "plan"})
        reg = self._reg(tm, {"bob": frozenset({"task_read"})})
        out = reg.dispatch("bob", "get_task_status", {
            "task_id": "t", "cross_owner": True,
        })
        assert out["found"] is True
        assert out["owner"] == "alice"


class TestMCPEffectsAndConnectorPerms:
    """Reviewer directive #7: MCP effects + connector permissions enforced."""

    def test_empty_effects_refused(self):
        reg = ToolRegistry(trust_actor_strings=True)
        reg.register_toolkit(ToolkitDescriptor(id="mcp", description="d"))
        class C:
            required_connector_permissions = ("mcp",)
            def invoke(self, tool_id, inputs):
                return {}
        with pytest.raises(ToolRegistryError, match="non-empty effects"):
            reg.register_mcp_tool(
                ToolDescriptor(
                    id="mcp.x", toolkit="mcp", kind=ToolKind.MCP,
                    description="d",
                    input_schema={},
                    owner="o",
                    effects=(),  # empty — refused
                    required_permissions=("mcp",),
                ),
                C(),
            )

    def test_connector_permissions_union_into_descriptor(self):
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "bob": frozenset({"mcp"}),
                "alice": frozenset({"mcp", "network"}),
            }),
            trust_actor_strings=True,
        )
        reg.register_toolkit(ToolkitDescriptor(id="mcp", description="d"))
        class C:
            required_connector_permissions = ("network",)  # connector needs network
            def invoke(self, tool_id, inputs):
                return {"ok": True}
        reg.register_mcp_tool(
            ToolDescriptor(
                id="mcp.net", toolkit="mcp", kind=ToolKind.MCP,
                description="network tool",
                input_schema={"type": "object", "properties": {}},
                owner="o",
                effects=("external_write",),
                required_permissions=("mcp",),
            ),
            C(),
        )
        # Bob only has `mcp` — the UNION (mcp + network) now gates discovery.
        assert reg.list_tools("bob") == []
        # Alice has both — discoverable and dispatchable.
        tools = {t.id: t for t in reg.list_tools("alice")}
        assert "mcp.net" in tools
        # Permissions on the stored descriptor include BOTH.
        assert set(tools["mcp.net"].required_permissions) == {"mcp", "network"}
        out = reg.dispatch("alice", "mcp.net", {})
        assert out == {"ok": True}

    def test_mcp_function_hostnative_stay_distinctly_typed(self):
        """A tool in `mcp` toolkit must be ToolKind.MCP — kind mismatch refused."""
        reg = ToolRegistry(trust_actor_strings=True)
        reg.register_toolkit(ToolkitDescriptor(id="mcp", description="d"))
        with pytest.raises(ToolRegistryError, match="wrong_kind"):
            reg.register_function_tool(
                ToolDescriptor(
                    id="mcp.not", toolkit="mcp", kind=ToolKind.FUNCTION,
                    description="pretend MCP", input_schema={}, owner="o",
                    effects=("read",),
                ),
                lambda inputs: {},
            )


# ---------------------------------------------------------------------------
# R3 best-practice follow-up — audit log + input cap + timeout
# ---------------------------------------------------------------------------


class TestAuditLog:
    def _make(self):
        reg = ToolRegistry(
            permission_grant=StaticGrant(
                permissions={"o": frozenset({"read_only", "audit_read"})}
            ),
            trust_actor_strings=True,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        reg.register_function_tool(
            ToolDescriptor(
                id="x", toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={
                    "type": "object",
                    "properties": {"flag": {"type": "boolean"}},
                },
                owner="o",
                required_permissions=("read_only",),
            ),
            lambda inputs: {"flag": bool(inputs.get("flag", False))},
        )
        return reg

    def test_successful_dispatch_recorded(self):
        reg = self._make()
        reg.dispatch("o", "x", {"flag": True})
        log = reg.audit_log("o")
        assert len(log) == 1
        entry = log[0]
        assert entry.status == "ok"
        assert entry.principal == "o"
        assert entry.tool_id == "x"
        assert entry.error_class is None
        assert entry.input_bytes > 0
        assert entry.duration_ms >= 0

    def test_unknown_tool_recorded(self):
        reg = self._make()
        with pytest.raises(ToolRegistryError, match="unknown_tool"):
            reg.dispatch("o", "nope", {})
        log = reg.audit_log("o")
        assert log[-1].status == "unknown_tool"
        assert log[-1].error_class is None

    def test_invalid_input_recorded(self):
        reg = self._make()
        with pytest.raises(ToolRegistryError, match="invalid_input"):
            reg.dispatch("o", "x", {"flag": "not-a-bool"})
        log = reg.audit_log("o")
        assert log[-1].status == "invalid_input"

    def test_impl_exception_recorded(self):
        reg = self._make()
        # Replace the impl with one that raises a PermissionError at call time.
        reg._impls["x"] = lambda inputs: (_ for _ in ()).throw(
            PermissionError("boom")
        )
        with pytest.raises(PermissionError, match="boom"):
            reg.dispatch("o", "x", {})
        log = reg.audit_log("o")
        assert log[-1].status == "error"
        assert log[-1].error_class == "PermissionError"

    def test_audit_log_filter(self):
        reg = self._make()
        reg.dispatch("o", "x", {})
        with pytest.raises(ToolRegistryError):
            reg.dispatch("o", "missing", {})
        oks = reg.audit_log("o", status="ok")
        err = reg.audit_log("o", status="unknown_tool")
        assert len(oks) == 1
        assert len(err) == 1
        assert reg.audit_log("o", tool_id="x") == oks
        assert reg.audit_log("o", principal="not-o") == []


class TestInputByteCap:
    def test_oversize_payload_refused(self):
        reg = ToolRegistry(
            permission_grant=StaticGrant(
                permissions={"o": frozenset({"read_only", "audit_read"})}
            ),
            trust_actor_strings=True,
            input_byte_limit=512,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        reg.register_function_tool(
            ToolDescriptor(
                id="x", toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={"type": "object"},
                owner="o",
                required_permissions=("read_only",),
            ),
            lambda inputs: {"ok": True},
        )
        big = {"blob": "A" * 5_000}
        with pytest.raises(ToolRegistryError, match="input_too_large"):
            reg.dispatch("o", "x", big)
        log = reg.audit_log("o")
        assert log[-1].status == "input_too_large"

    def test_cap_zero_disables(self):
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={"o": frozenset({"read_only"})}),
            trust_actor_strings=True,
            input_byte_limit=0,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        reg.register_function_tool(
            ToolDescriptor(
                id="x", toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={"type": "object"},
                owner="o",
                required_permissions=("read_only",),
            ),
            lambda inputs: {"ok": True},
        )
        # No cap -> huge payloads pass.
        reg.dispatch("o", "x", {"blob": "A" * 100_000})


class TestDispatchTimeout:
    def _reg(self, timeout_s):
        reg = ToolRegistry(
            permission_grant=StaticGrant(
                permissions={"o": frozenset({"read_only", "audit_read"})}
            ),
            trust_actor_strings=True,
            default_timeout_s=timeout_s,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        return reg

    def test_slow_tool_times_out(self):
        import time
        reg = self._reg(0.15)
        reg.register_function_tool(
            ToolDescriptor(
                id="slow", toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={"type": "object"},
                owner="o",
                required_permissions=("read_only",),
            ),
            lambda inputs: (time.sleep(2.0) or {"ok": True}),
        )
        with pytest.raises(ToolRegistryError, match="tool_timeout"):
            reg.dispatch("o", "slow", {})
        log = reg.audit_log("o")
        assert log[-1].status == "tool_timeout"

    def test_per_call_override(self):
        import time
        reg = self._reg(5.0)  # generous default
        reg.register_function_tool(
            ToolDescriptor(
                id="slow", toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={"type": "object"},
                owner="o",
                required_permissions=("read_only",),
            ),
            lambda inputs: (time.sleep(1.5) or {"ok": True}),
        )
        # Per-call override shrinks it.
        with pytest.raises(ToolRegistryError, match="tool_timeout"):
            reg.dispatch("o", "slow", {}, timeout_s=0.1)

    def test_timeout_zero_disables(self):
        reg = self._reg(0.0)
        reg.register_function_tool(
            ToolDescriptor(
                id="fast", toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={"type": "object"},
                owner="o",
                required_permissions=("read_only",),
            ),
            lambda inputs: {"ok": True},
        )
        assert reg.dispatch("o", "fast", {}) == {"ok": True}



class TestTimeoutDeadlineAndReconciliation:
    """R3 corrective — the caller must return at the configured deadline,
    regardless of the worker's progress, and tool_timeout audit entries
    must carry side-effect uncertainty until reconcile_pending observes
    the Future complete."""

    def _reg(self, timeout_s=0.1):
        reg = ToolRegistry(
            permission_grant=StaticGrant(
                permissions={"o": frozenset({"read_only", "audit_read"})}
            ),
            trust_actor_strings=True,
            default_timeout_s=timeout_s,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        return reg

    def _register(self, reg, impl):
        reg.register_function_tool(
            ToolDescriptor(
                id="slow", toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={"type": "object"},
                owner="o",
                required_permissions=("read_only",),
            ),
            impl,
        )

    def test_caller_returns_at_deadline_not_after_worker_finishes(self):
        """Reviewer: `shutdown(wait=True)` on the executor must not block
        the caller past the configured timeout."""
        import threading
        import time
        reg = self._reg(0.15)
        released = threading.Event()
        def _impl(inputs):
            # Hold the worker thread for 1.5s regardless of caller fate.
            time.sleep(1.5)
            released.set()
            return {"late": True}
        self._register(reg, _impl)

        t0 = time.monotonic()
        with pytest.raises(ToolRegistryError, match="tool_timeout"):
            reg.dispatch("o", "slow", {})
        elapsed = time.monotonic() - t0
        # Caller must have returned by now — i.e. before the worker's
        # sleep finishes (1.5s). We give an upper bound well below 1.5s
        # to prove shutdown(wait=True) is NOT in effect.
        assert elapsed < 0.9, (
            f"dispatch blocked for {elapsed:.3f}s; expected < 0.9s"
        )
        assert not released.is_set(), (
            "worker should still be running; caller returned too late"
        )
        reg.close()

    def test_timeout_audit_entry_marks_uncertain_before_reconcile(self):
        import time
        reg = self._reg(0.1)
        self._register(reg, lambda inputs: (time.sleep(0.8) or {"ok": True}))
        with pytest.raises(ToolRegistryError, match="tool_timeout"):
            reg.dispatch("o", "slow", {})
        log = reg.audit_log("o")
        assert log[-1].status == "tool_timeout"
        assert log[-1].side_effect_state == "uncertain"
        assert log[-1].worker_termination_confirmed is False
        assert log[-1].entry_id > 0
        pending = reg.pending_timeouts("o")
        assert log[-1].entry_id in pending
        reg.close()

    def test_reconcile_pending_settles_successful_worker(self):
        import time
        reg = self._reg(0.1)
        self._register(reg, lambda inputs: (time.sleep(0.5) or {"ok": True}))
        with pytest.raises(ToolRegistryError, match="tool_timeout"):
            reg.dispatch("o", "slow", {})
        # Wait for the worker to actually finish.
        time.sleep(0.9)
        updated = reg.reconcile_pending("o")
        assert len(updated) == 1
        assert updated[0].side_effect_state == "settled"
        assert updated[0].worker_termination_confirmed is True
        # The audit log view is also updated.
        log = reg.audit_log("o")
        assert log[-1].side_effect_state == "settled"
        assert log[-1].worker_termination_confirmed is True
        # Pending set drained.
        assert reg.pending_timeouts("o") == []
        reg.close()

    def test_reconcile_pending_settles_failing_worker(self):
        import time
        reg = self._reg(0.1)
        def _impl(inputs):
            time.sleep(0.5)
            raise RuntimeError("worker exploded late")
        self._register(reg, _impl)
        with pytest.raises(ToolRegistryError, match="tool_timeout"):
            reg.dispatch("o", "slow", {})
        time.sleep(0.9)
        updated = reg.reconcile_pending("o")
        assert len(updated) == 1
        assert updated[0].side_effect_state == "settled_error"
        assert updated[0].error_class == "RuntimeError"
        assert updated[0].worker_termination_confirmed is True
        # Exception message is NOT recorded anywhere on the entry.
        for field_value in updated[0].__dict__.values():
            if isinstance(field_value, str):
                assert "exploded" not in field_value
        reg.close()

    def test_reconcile_pending_leaves_live_worker_uncertain(self):
        import time
        reg = self._reg(0.1)
        self._register(reg, lambda inputs: (time.sleep(2.0) or {"ok": True}))
        with pytest.raises(ToolRegistryError, match="tool_timeout"):
            reg.dispatch("o", "slow", {})
        # Reconcile too early — worker still running.
        updated = reg.reconcile_pending("o")
        assert updated == []
        # Entry is still uncertain.
        log = reg.audit_log("o")
        assert log[-1].side_effect_state == "uncertain"
        reg.close()

    def test_reconcile_pending_requires_audit_read(self):
        import time
        reg = ToolRegistry(
            permission_grant=StaticGrant(
                permissions={
                    "o": frozenset({"read_only", "audit_read"}),
                    "n": frozenset({"read_only"}),
                }
            ),
            trust_actor_strings=True,
            default_timeout_s=0.1,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        reg.register_function_tool(
            ToolDescriptor(
                id="slow", toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={"type": "object"},
                owner="o",
                required_permissions=("read_only",),
            ),
            lambda inputs: (time.sleep(0.5) or {"ok": True}),
        )
        with pytest.raises(ToolRegistryError, match="tool_timeout"):
            reg.dispatch("o", "slow", {})
        # Caller "n" lacks audit_read.
        with pytest.raises(ToolRegistryError, match="insufficient_permission"):
            reg.reconcile_pending("n")
        # Missing caller when grants are set.
        with pytest.raises(ToolRegistryError, match="untrusted_identity"):
            reg.reconcile_pending()
        reg.close()


class TestAuditRetentionAndAccessControl:
    """R3 corrective — audit retention bounds, thread safety, and
    read-side access control."""

    def _make(self, *, audit_max_entries=10_000, grants=None):
        if grants is None:
            grants = {"o": frozenset({"read_only", "audit_read"})}
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions=grants),
            trust_actor_strings=True,
            audit_max_entries=audit_max_entries,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        reg.register_function_tool(
            ToolDescriptor(
                id="x", toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={"type": "object"},
                owner="o",
                required_permissions=("read_only",),
            ),
            lambda inputs: {"ok": True},
        )
        return reg

    def test_ring_buffer_eviction_keeps_most_recent(self):
        reg = self._make(audit_max_entries=5)
        for _ in range(50):
            reg.dispatch("o", "x", {})
        log = reg.audit_log("o")
        assert len(log) == 5
        # Entry ids are monotonic — most recent are the highest.
        ids = [e.entry_id for e in log]
        assert ids == sorted(ids)
        assert ids[0] == 46 and ids[-1] == 50
        reg.close()

    def test_concurrent_dispatch_appends_are_lossless(self):
        import threading
        reg = self._make(audit_max_entries=10_000)
        n_threads = 8
        per_thread = 50
        errors: list[BaseException] = []
        def _worker():
            try:
                for _ in range(per_thread):
                    reg.dispatch("o", "x", {})
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
        threads = [threading.Thread(target=_worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        log = reg.audit_log("o")
        assert len(log) == n_threads * per_thread, (
            f"expected {n_threads * per_thread} entries, got {len(log)}"
        )
        # All status=ok, principal=o.
        assert {e.status for e in log} == {"ok"}
        # entry_ids are unique.
        assert len({e.entry_id for e in log}) == len(log)
        reg.close()

    def test_audit_log_requires_caller_when_grant_set(self):
        reg = self._make()
        with pytest.raises(ToolRegistryError, match="untrusted_identity"):
            reg.audit_log()
        reg.close()

    def test_audit_log_refuses_caller_without_audit_read(self):
        reg = self._make(
            grants={
                "o": frozenset({"read_only", "audit_read"}),
                "n": frozenset({"read_only"}),  # no audit_read
            }
        )
        reg.dispatch("o", "x", {})
        with pytest.raises(ToolRegistryError, match="insufficient_permission"):
            reg.audit_log("n")
        reg.close()

    def test_audit_log_allows_task_admin(self):
        reg = self._make(
            grants={
                "o": frozenset({"read_only"}),
                "admin": frozenset({"task_admin"}),
            }
        )
        # 'o' can dispatch but not read; 'admin' can read via task_admin.
        reg.dispatch("o", "x", {})
        log = reg.audit_log("admin")
        assert len(log) == 1
        reg.close()

    def test_audit_log_open_when_grant_absent(self):
        # No permission_grant => legacy un-gated behaviour; audit_log()
        # with no caller returns the view.
        reg = ToolRegistry(trust_actor_strings=True)
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        reg.register_function_tool(
            ToolDescriptor(
                id="x", toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={"type": "object"},
                owner="o",
                required_permissions=(),
            ),
            lambda inputs: {"ok": True},
        )
        reg.dispatch("o", "x", {})
        assert len(reg.audit_log()) == 1
        reg.close()

    def test_close_refuses_further_dispatch(self):
        reg = self._make()
        reg.dispatch("o", "x", {})
        reg.close()
        with pytest.raises(ToolRegistryError, match="registry_closed"):
            reg.dispatch("o", "x", {})



class TestCloseDispatchRaceAndCleanCancel:
    """R3 reviewer corrections (round 2) — two cases on commit c09d918.

    Case 1: close() and dispatch() must not race. A dispatch that passes
    the top-of-method _closed check must either successfully submit before
    the executor shutdown, or raise ToolRegistryError('registry_closed')
    — never the raw RuntimeError('cannot schedule new futures after
    shutdown') leaked from the executor.

    Case 2: tool_timeout where Future.cancel() returns True (worker was
    still queued and never ran) must be classified as side_effect_state
    'settled' with worker_termination_confirmed=True — the worker is
    guaranteed never to execute, so there are no uncertain side effects
    and no reconcile_pending call is required.
    """

    def _reg(self, timeout_s=0.1, workers=4):
        return self._build(timeout_s=timeout_s, workers=workers)

    @staticmethod
    def _build(timeout_s=0.1, workers=4):
        reg = ToolRegistry(
            permission_grant=StaticGrant(
                permissions={"o": frozenset({"read_only", "audit_read"})}
            ),
            trust_actor_strings=True,
            default_timeout_s=timeout_s,
            dispatch_workers=workers,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        return reg

    def _register(self, reg, impl, *, tool_id="x"):
        reg.register_function_tool(
            ToolDescriptor(
                id=tool_id, toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={"type": "object"},
                owner="o",
                required_permissions=("read_only",),
            ),
            impl,
        )

    # ---- Case 1: close()/dispatch() race -------------------------------

    def test_close_during_dispatch_submit_raises_registry_closed(self):
        """Reviewer: a close() firing between the dispatch-level _closed
        check and ThreadPoolExecutor.submit must surface
        ToolRegistryError('registry_closed'), NOT a leaked
        RuntimeError from the shut-down executor."""
        import threading
        import time
        reg = self._reg(timeout_s=5.0, workers=1)
        self._register(reg, lambda inputs: {"ok": True})

        # Prime the single worker so the next dispatch has to queue.
        gate = threading.Event()
        self._register(
            reg,
            lambda inputs: (gate.wait() or {"blocked": True}),
            tool_id="blocker",
        )
        blocker_done = threading.Event()
        def _blocker():
            try:
                reg.dispatch("o", "blocker", {})
            finally:
                blocker_done.set()
        tb = threading.Thread(target=_blocker)
        tb.start()
        # Give the blocker time to start executing on the sole worker.
        time.sleep(0.1)

        # Now call close() concurrently with a fresh dispatch. We can't
        # perfectly force the race, so run several iterations and assert
        # that whichever outcome happens is a graceful one — never a
        # bare RuntimeError.
        caught = []
        def _closer():
            # Small delay so the dispatch has a chance to race.
            time.sleep(0.01)
            reg.close()
        for _ in range(20):
            tc = threading.Thread(target=_closer)
            tc.start()
            try:
                reg.dispatch("o", "x", {}, timeout_s=0.05)
            except ToolRegistryError as exc:
                caught.append(str(exc))
            except Exception as exc:  # noqa: BLE001
                tc.join()
                raise AssertionError(
                    f"dispatch leaked non-ToolRegistryError: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            tc.join()
            if reg._closed:
                break

        # Release the blocker so the thread can finish.
        gate.set()
        tb.join(timeout=5)

        # Every post-close dispatch must have been reported as
        # registry_closed OR tool_timeout; we never want a raw
        # RuntimeError or anything else.
        for msg in caught:
            assert (
                msg.startswith("registry_closed")
                or msg.startswith("tool_timeout")
                or msg.startswith("unknown_tool")
            ), f"unexpected error message: {msg!r}"
        # The registry is now closed.
        assert reg._closed is True

    def test_dispatch_after_close_always_registry_closed(self):
        """After close() returns, every subsequent dispatch must raise
        registry_closed with a safe ToolRegistryError. Deterministic
        companion to the race test."""
        reg = self._reg(timeout_s=5.0, workers=1)
        self._register(reg, lambda inputs: {"ok": True})
        reg.close()
        for _ in range(5):
            with pytest.raises(ToolRegistryError, match="registry_closed"):
                reg.dispatch("o", "x", {})

    # ---- Case 2: fut.cancel() succeeded path --------------------------

    def test_cancelled_before_start_is_settled_not_uncertain(self):
        """Reviewer: when the Future is cancelled cleanly before the
        worker runs, side_effect_state must be 'settled' (never-ran) and
        worker_termination_confirmed must be True. The entry must NOT
        appear in _pending_timeouts and reconcile_pending must have
        nothing to do."""
        import threading
        import time

        # One worker, saturate it with a blocker that holds the pool.
        reg = self._reg(timeout_s=5.0, workers=1)
        gate = threading.Event()
        self._register(
            reg,
            lambda inputs: (gate.wait() or {"blocked": True}),
            tool_id="blocker",
        )
        self._register(
            reg,
            lambda inputs: {"ok": True},
            tool_id="x",
        )
        blocker_done = threading.Event()
        def _blocker():
            try:
                reg.dispatch("o", "blocker", {})
            finally:
                blocker_done.set()
        tb = threading.Thread(target=_blocker)
        tb.start()
        time.sleep(0.1)  # let blocker enter the worker

        # Now dispatch x with a tiny timeout. The single worker is busy;
        # x stays queued, times out, and fut.cancel() succeeds.
        t0 = time.monotonic()
        with pytest.raises(ToolRegistryError, match="tool_timeout") as excinfo:
            reg.dispatch("o", "x", {}, timeout_s=0.05)
        elapsed = time.monotonic() - t0
        # Caller returned at the deadline.
        assert elapsed < 0.5

        # Error message must distinguish the clean-cancel case.
        assert "cancelled before starting" in str(excinfo.value)

        # Audit entry: side_effect_state='settled', confirmed=True.
        log = reg.audit_log("o")
        x_entries = [e for e in log if e.tool_id == "x"]
        assert len(x_entries) == 1
        entry = x_entries[0]
        assert entry.status == "tool_timeout"
        assert entry.side_effect_state == "settled", (
            f"expected 'settled' for cleanly-cancelled worker, "
            f"got {entry.side_effect_state!r}"
        )
        assert entry.worker_termination_confirmed is True

        # No entry queued for reconcile_pending — the cleanly-cancelled
        # Future had no side effects to reconcile.
        assert entry.entry_id not in reg.pending_timeouts("o")
        assert reg.pending_timeouts("o") == []
        assert reg.reconcile_pending("o") == []

        # Release the blocker; teardown.
        gate.set()
        tb.join(timeout=5)
        reg.close()

    def test_detached_worker_still_uncertain_and_tracked(self):
        """Regression companion to the clean-cancel test: when the
        worker DOES start before the timeout fires (fut.cancel() returns
        False), the audit entry stays 'uncertain' and the entry_id is
        tracked for reconcile_pending — the previous behaviour is
        preserved for the ordinary detached-worker case."""
        import time
        reg = self._reg(timeout_s=0.1, workers=4)
        # Worker starts immediately and runs past the deadline.
        self._register(
            reg,
            lambda inputs: (time.sleep(0.6) or {"late": True}),
        )
        with pytest.raises(ToolRegistryError, match="tool_timeout"):
            reg.dispatch("o", "x", {})
        log = reg.audit_log("o")
        entry = log[-1]
        assert entry.status == "tool_timeout"
        assert entry.side_effect_state == "uncertain"
        assert entry.worker_termination_confirmed is False
        assert entry.entry_id in reg.pending_timeouts("o")
        reg.close()



class TestWriteSideEffectVerification:
    """R3 reviewer directive (round 3) — a completed worker does not prove
    its write succeeded. reconcile_pending must consult a registered
    side-effect probe for write-type tools and refuse to claim
    ``settled`` without probe evidence.

    Reuses the existing audit-registry harness and ToolDescriptor
    conventions — no new fixture files.
    """

    def _build(self, *, probe=None, effects=("internal_write",)):
        reg = ToolRegistry(
            permission_grant=StaticGrant(
                permissions={"o": frozenset({"task_write", "audit_read"})}
            ),
            trust_actor_strings=True,
            default_timeout_s=0.1,
            dispatch_workers=4,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        descriptor = ToolDescriptor(
            id="writer",
            toolkit="t",
            kind=ToolKind.FUNCTION,
            description="d",
            input_schema={"type": "object"},
            owner="o",
            effects=effects,
            required_permissions=("task_write",),
        )
        kwargs = {}
        if probe is not None:
            kwargs["side_effect_probe"] = probe
        import time as _time
        reg.register_function_tool(
            descriptor,
            lambda inputs: (_time.sleep(0.5) or {"ok": True}),
            **kwargs,
        )
        return reg

    def _trigger_timeout(self, reg):
        with pytest.raises(ToolRegistryError, match="tool_timeout"):
            reg.dispatch("o", "writer", {})

    def test_write_tool_without_probe_is_settled_unverified(self):
        """Reviewer: a write-type tool with no probe MUST NOT be labelled
        \"settled\" when the worker completes. The registry refuses to
        claim safety without evidence."""
        import time
        reg = self._build(probe=None)
        self._trigger_timeout(reg)
        time.sleep(0.9)
        updated = reg.reconcile_pending("o")
        assert len(updated) == 1
        assert updated[0].side_effect_state == "settled_unverified"
        assert updated[0].worker_termination_confirmed is True
        # No probe evidence recorded.
        assert updated[0].probe_evidence is None
        reg.close()

    def test_probe_confirming_write_landed_marks_settled(self):
        import time
        def probe(payload, principal):
            return {"applied": True, "evidence": "revision_advanced:task=T1 revision=2"}
        reg = self._build(probe=probe)
        self._trigger_timeout(reg)
        time.sleep(0.9)
        updated = reg.reconcile_pending("o")
        assert len(updated) == 1
        assert updated[0].side_effect_state == "settled"
        assert updated[0].worker_termination_confirmed is True
        assert updated[0].probe_evidence == (
            "revision_advanced:task=T1 revision=2"
        )
        reg.close()

    def test_probe_denying_write_marks_settled_no_effect(self):
        import time
        def probe(payload, principal):
            return {"applied": False, "evidence": "revision_unchanged:task=T1 revision=1"}
        reg = self._build(probe=probe)
        self._trigger_timeout(reg)
        time.sleep(0.9)
        updated = reg.reconcile_pending("o")
        assert len(updated) == 1
        assert updated[0].side_effect_state == "settled_no_effect"
        assert updated[0].probe_evidence == (
            "revision_unchanged:task=T1 revision=1"
        )
        reg.close()

    def test_probe_returning_none_marks_settled_unverified(self):
        """A probe that cannot determine the outcome returns None — the
        registry must refuse to claim settled."""
        import time
        def probe(payload, principal):
            return None
        reg = self._build(probe=probe)
        self._trigger_timeout(reg)
        time.sleep(0.9)
        updated = reg.reconcile_pending("o")
        assert len(updated) == 1
        assert updated[0].side_effect_state == "settled_unverified"
        reg.close()

    def test_probe_that_raises_marks_settled_unverified(self):
        """A probe that itself raises records the probe's error class but
        does NOT advance the entry past settled_unverified."""
        import time
        def probe(payload, principal):
            raise RuntimeError("probe exploded with secret: nope")
        reg = self._build(probe=probe)
        self._trigger_timeout(reg)
        time.sleep(0.9)
        updated = reg.reconcile_pending("o")
        assert len(updated) == 1
        assert updated[0].side_effect_state == "settled_unverified"
        assert updated[0].error_class == "RuntimeError"
        # The exception message must not appear anywhere on the entry.
        for value in updated[0].__dict__.values():
            if isinstance(value, str):
                assert "nope" not in value
        reg.close()

    def test_read_only_tool_still_settled_without_probe(self):
        """Backward-compat: a tool whose effects list is only (\"read\",)
        reaches ``settled`` on worker completion with no probe required
        — reading has no side effect to verify."""
        import time
        reg = self._build(probe=None, effects=("read",))
        self._trigger_timeout(reg)
        time.sleep(0.9)
        updated = reg.reconcile_pending("o")
        assert len(updated) == 1
        assert updated[0].side_effect_state == "settled"
        reg.close()


class TestWriteSideEffectVerificationOnError:
    """Companion to TestWriteSideEffectVerification — same contract,
    this time the worker RAISED instead of returning."""

    def _build(self, *, probe=None, effects=("internal_write",)):
        reg = ToolRegistry(
            permission_grant=StaticGrant(
                permissions={"o": frozenset({"task_write", "audit_read"})}
            ),
            trust_actor_strings=True,
            default_timeout_s=0.1,
            dispatch_workers=4,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        descriptor = ToolDescriptor(
            id="writer_err",
            toolkit="t",
            kind=ToolKind.FUNCTION,
            description="d",
            input_schema={"type": "object"},
            owner="o",
            effects=effects,
            required_permissions=("task_write",),
        )
        import time as _time
        def _impl(inputs):
            _time.sleep(0.5)
            raise RuntimeError("worker exploded late (SECRET=xyz)")
        kwargs = {}
        if probe is not None:
            kwargs["side_effect_probe"] = probe
        reg.register_function_tool(descriptor, _impl, **kwargs)
        return reg

    def _trigger_timeout(self, reg):
        with pytest.raises(ToolRegistryError, match="tool_timeout"):
            reg.dispatch("o", "writer_err", {})

    def test_worker_raised_probe_says_landed_marks_partial_write(self):
        """Half-finished write: effect landed, worker raised during
        cleanup. DO NOT retry — must surface as settled_partial_write."""
        import time
        def probe(payload, principal):
            return {"applied": True, "evidence": "revision_advanced"}
        reg = self._build(probe=probe)
        self._trigger_timeout(reg)
        time.sleep(0.9)
        updated = reg.reconcile_pending("o")
        assert len(updated) == 1
        assert updated[0].side_effect_state == "settled_partial_write"
        assert updated[0].error_class == "RuntimeError"
        # Secret from exception message must NEVER leak.
        for value in updated[0].__dict__.values():
            if isinstance(value, str):
                assert "SECRET" not in value and "xyz" not in value
        reg.close()

    def test_worker_raised_probe_says_not_landed_marks_settled_error(self):
        import time
        def probe(payload, principal):
            return {"applied": False, "evidence": "revision_unchanged"}
        reg = self._build(probe=probe)
        self._trigger_timeout(reg)
        time.sleep(0.9)
        updated = reg.reconcile_pending("o")
        assert len(updated) == 1
        assert updated[0].side_effect_state == "settled_error"
        assert updated[0].error_class == "RuntimeError"
        reg.close()

    def test_worker_raised_no_probe_marks_settled_error_unverified(self):
        """A write-type tool with no probe can neither confirm nor deny
        the half-write; reconciliation must refuse to label the entry
        as safely retryable."""
        import time
        reg = self._build(probe=None)
        self._trigger_timeout(reg)
        time.sleep(0.9)
        updated = reg.reconcile_pending("o")
        assert len(updated) == 1
        assert updated[0].side_effect_state == "settled_error_unverified"
        assert updated[0].error_class == "RuntimeError"
        reg.close()



class TestDefaultProbesWiring:
    """Verify register_default_toolkits wires probes for the two write-type
    task-management tools and that each probe answers correctly against a
    real TaskManager."""

    def test_update_task_progress_probe_registered_and_detects_applied(self, tmp_path):
        from tools.task_management import TaskManager
        snapshot = tmp_path / "tasks.json"
        tm = TaskManager(storage_path=str(snapshot))
        task = tm.create_task(metadata={"revision": 1, "stage": "plan", "owner": "alice"})
        task_id = str(task.task_id)
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "alice": frozenset({"task_write", "audit_read"}),
            }),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg, host=HostCapabilities(), task_manager=tm, repo_root=None,
        )
        probe = reg._side_effect_probes.get("update_task_progress")
        assert callable(probe), "probe must be registered for write-type tool"
        # Simulate a successful write: dispatch normally, then query probe
        # with the SAME payload the caller used.
        payload = {
            "task_id": task_id,
            "progress_note": "verified-landing",
            "if_revision": 1,
        }
        reg.dispatch("alice", "update_task_progress", payload)
        result = probe(payload, "alice")
        assert isinstance(result, dict)
        assert result["applied"] is True
        assert "revision_advanced" in result["evidence"]
        assert "evidence" in result and "secret" not in result["evidence"].lower()

    def test_update_task_progress_probe_detects_unchanged_revision(self, tmp_path):
        from tools.task_management import TaskManager
        snapshot = tmp_path / "tasks.json"
        tm = TaskManager(storage_path=str(snapshot))
        task = tm.create_task(metadata={"revision": 1, "stage": "plan", "owner": "alice"})
        task_id = str(task.task_id)
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "alice": frozenset({"task_write", "audit_read"}),
            }),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg, host=HostCapabilities(), task_manager=tm, repo_root=None,
        )
        probe = reg._side_effect_probes["update_task_progress"]
        # No write has happened yet — the probe should report applied=False.
        result = probe(
            {"task_id": task_id, "progress_note": "pretend", "if_revision": 1},
            "alice",
        )
        assert result == {
            "applied": False,
            "evidence": f"revision_unchanged:task={task_id} revision=1",
        }

    def test_adopt_task_owner_probe_registered_and_detects_applied(self, tmp_path):
        from tools.task_management import TaskManager
        snapshot = tmp_path / "tasks.json"
        tm = TaskManager(storage_path=str(snapshot))
        task = tm.create_task(metadata={"revision": 1, "stage": "plan"})
        task_id = str(task.task_id)
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "admin": frozenset({"task_admin", "audit_read"}),
            }),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg, host=HostCapabilities(), task_manager=tm, repo_root=None,
        )
        probe = reg._side_effect_probes.get("adopt_task_owner")
        assert callable(probe)
        payload = {
            "task_id": task_id,
            "new_owner": "bob",
            "if_revision": 1,
        }
        reg.dispatch("admin", "adopt_task_owner", payload)
        result = probe(payload, "admin")
        assert isinstance(result, dict) and result["applied"] is True
        assert "owner_adopted" in result["evidence"]

    def test_read_only_tool_has_no_probe(self, tmp_path):
        """Read-only task-management tools do not need (and must not have)
        a side-effect probe registered — reading has no side effect."""
        from tools.task_management import TaskManager
        snapshot = tmp_path / "tasks.json"
        tm = TaskManager(storage_path=str(snapshot))
        tm.create_task(metadata={"revision": 1, "stage": "plan", "owner": "alice"})
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "alice": frozenset({"task_read"}),
            }),
            trust_actor_strings=True,
        )
        register_default_toolkits(
            reg, host=HostCapabilities(), task_manager=tm, repo_root=None,
        )
        assert "get_task_status" not in reg._side_effect_probes



class TestWriteSideEffectVerificationCorrections:
    """R3 reviewer corrections (round 4) — two small fixes inside the
    accepted side-effect probe task.

    Correction 1: concurrent reconcile_pending must not drain the same
    pending entry twice.

    Correction 2: when the probe raises AND the worker also raised, the
    audit entry must surface the probe's error class via probe_evidence
    (never the probe's exception message) so operators can tell
    \"no probe run\" apart from \"probe raised\".
    """

    def _build(self, probe, *, effects=("internal_write",)):
        reg = ToolRegistry(
            permission_grant=StaticGrant(
                permissions={"o": frozenset({"task_write", "audit_read"})}
            ),
            trust_actor_strings=True,
            default_timeout_s=0.1,
            dispatch_workers=4,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))
        descriptor = ToolDescriptor(
            id="writer",
            toolkit="t",
            kind=ToolKind.FUNCTION,
            description="d",
            input_schema={"type": "object"},
            owner="o",
            effects=effects,
            required_permissions=("task_write",),
        )
        import time as _time
        reg.register_function_tool(
            descriptor,
            lambda inputs: (_time.sleep(0.5) or {"ok": True}),
            side_effect_probe=probe,
        )
        return reg

    # ---- Correction 1 -------------------------------------------------

    def test_concurrent_reconcile_pending_drains_each_entry_once(self):
        """Two threads call reconcile_pending at the same instant on the
        same ready-but-detached entry. The entry must be drained exactly
        once; the probe must be called exactly once; the second thread
        sees an empty updated list."""
        import threading
        import time

        probe_calls = []
        probe_lock = threading.Lock()

        def probe(payload, principal):
            with probe_lock:
                probe_calls.append(1)
            # Simulate a slightly slow probe so the two reconcile_pending
            # threads overlap.
            time.sleep(0.05)
            return {"applied": True, "evidence": "landed"}

        reg = self._build(probe)
        with pytest.raises(ToolRegistryError, match="tool_timeout"):
            reg.dispatch("o", "writer", {})
        time.sleep(0.9)  # worker completes

        results = {}
        barrier = threading.Barrier(2)

        def _reconcile(key):
            barrier.wait()
            results[key] = reg.reconcile_pending("o")

        ta = threading.Thread(target=_reconcile, args=("a",))
        tb = threading.Thread(target=_reconcile, args=("b",))
        ta.start()
        tb.start()
        ta.join()
        tb.join()

        # Exactly one of the two callers drains the entry.
        drained_counts = sorted([len(results["a"]), len(results["b"])])
        assert drained_counts == [0, 1], (
            f"expected one drain and one empty, got {drained_counts}"
        )
        # Probe was called exactly once.
        assert len(probe_calls) == 1
        # Audit entry is settled on the one that drained.
        log = reg.audit_log("o")
        assert log[-1].side_effect_state == "settled"
        # Pending set is empty.
        assert reg.pending_timeouts("o") == []
        reg.close()

    # ---- Correction 2 -------------------------------------------------

    def test_probe_raise_with_worker_raise_surfaces_probe_class(self):
        """When both the worker and the probe raise, worker's exception
        class owns ``error_class`` but ``probe_evidence`` MUST carry
        the probe's exception class (never its message) so operators
        can tell the probe actually ran and failed."""
        import time
        reg = ToolRegistry(
            permission_grant=StaticGrant(
                permissions={"o": frozenset({"task_write", "audit_read"})}
            ),
            trust_actor_strings=True,
            default_timeout_s=0.1,
            dispatch_workers=4,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))

        def _impl(inputs):
            time.sleep(0.5)
            raise RuntimeError("worker boom (SECRET=abc)")

        def _probe(payload, principal):
            raise ValueError("probe boom (SECRET=xyz)")

        reg.register_function_tool(
            ToolDescriptor(
                id="w", toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={"type": "object"},
                owner="o",
                effects=("internal_write",),
                required_permissions=("task_write",),
            ),
            _impl,
            side_effect_probe=_probe,
        )
        with pytest.raises(ToolRegistryError, match="tool_timeout"):
            reg.dispatch("o", "w", {})
        time.sleep(0.9)
        updated = reg.reconcile_pending("o")
        assert len(updated) == 1
        entry = updated[0]
        # Worker owns error_class — not the probe.
        assert entry.error_class == "RuntimeError"
        # Probe-raise is still surfaced via probe_evidence, class name only.
        assert entry.probe_evidence == "probe_raised:ValueError"
        # No secret message leaks anywhere on the entry.
        for value in entry.__dict__.values():
            if isinstance(value, str):
                assert "SECRET" not in value
                assert "abc" not in value
                assert "xyz" not in value
        # Unverified because probe didn't produce applied=True/False.
        assert entry.side_effect_state == "settled_error_unverified"
        reg.close()

    def test_probe_raise_with_worker_success_surfaces_probe_class(self):
        """Companion: worker returned OK, probe raised. error_class is
        the probe's; probe_evidence is 'probe_raised:<ProbeExc>'."""
        import time
        reg = ToolRegistry(
            permission_grant=StaticGrant(
                permissions={"o": frozenset({"task_write", "audit_read"})}
            ),
            trust_actor_strings=True,
            default_timeout_s=0.1,
            dispatch_workers=4,
        )
        reg.register_toolkit(ToolkitDescriptor(id="t", description="d"))

        def _impl(inputs):
            time.sleep(0.5)
            return {"ok": True}

        def _probe(payload, principal):
            raise LookupError("probe-can-not-find (SECRET=qqq)")

        reg.register_function_tool(
            ToolDescriptor(
                id="w2", toolkit="t", kind=ToolKind.FUNCTION,
                description="d",
                input_schema={"type": "object"},
                owner="o",
                effects=("internal_write",),
                required_permissions=("task_write",),
            ),
            _impl,
            side_effect_probe=_probe,
        )
        with pytest.raises(ToolRegistryError, match="tool_timeout"):
            reg.dispatch("o", "w2", {})
        time.sleep(0.9)
        updated = reg.reconcile_pending("o")
        assert len(updated) == 1
        entry = updated[0]
        assert entry.error_class == "LookupError"
        assert entry.probe_evidence == "probe_raised:LookupError"
        for value in entry.__dict__.values():
            if isinstance(value, str):
                assert "SECRET" not in value and "qqq" not in value
        assert entry.side_effect_state == "settled_unverified"
        reg.close()
