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
        # R3 corrective (C2): update_task_progress now requires task_write.
        grant = StaticGrant(permissions={"caller": frozenset({"read_only", "task_write"})})
        reg = self._registry(grant)
        ids = {t.id for t in reg.list_tools("caller")}
        # read_only + task_write permitted tools:
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
        # New: without task_write, update_task_progress is dropped.
        grant_ro = StaticGrant(permissions={"caller": frozenset({"read_only"})})
        reg_ro = self._registry(grant_ro)
        ids_ro = {t.id for t in reg_ro.list_tools("caller")}
        assert "update_task_progress" not in ids_ro

    def test_list_tools_scoped_to_toolkit(self):
        grant = StaticGrant(permissions={"caller": frozenset({"read_only", "task_write"})})
        reg = self._registry(grant)
        ids = {t.id for t in reg.list_tools("caller", toolkit_id="task_management")}
        assert ids == {"get_task_status", "update_task_progress", "update_plan"}

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
                    "filesystem_write", "network", "task_write",
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
        reg = self._registry(StaticGrant(permissions={"o": frozenset({"read_only"})}))
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
        reg = self._registry(StaticGrant(permissions={"o": frozenset({"read_only"})}))
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
        from agent.prompt_authoring.store import IdentityProvider
        reg = self._reg()
        self._bootstrap(reg)
        idp = IdentityProvider(credentials={"o": "s"})
        p = idp.authenticate("o", "s")
        tools = reg.list_tools(p)
        assert [t.id for t in tools] == ["x"]
        assert reg.dispatch(p, "x") == {"out": "ok"}


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

    def test_owner_bind_adopts_caller(self):
        tm = _FakeTaskManager()
        # Legacy task with no owner.
        tm.create_task("legacy", {"revision": 1, "stage": "plan"})
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={"alice": frozenset({"task_write"})}),
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
        out = reg.dispatch("alice", "update_task_progress", {
            "task_id": "legacy",
            "progress_note": "first write",
            "if_revision": 1,
            "owner_bind": True,
        })
        assert out["owner"] == "alice"
        assert tm.get_task("legacy").metadata["owner"] == "alice"


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
