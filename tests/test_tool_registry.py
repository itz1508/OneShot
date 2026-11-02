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
        reg = ToolRegistry()
        with pytest.raises(ToolRegistryError, match="unknown_toolkit"):
            reg.register_function_tool(
                ToolDescriptor(
                    id="x", toolkit="nope", kind=ToolKind.FUNCTION,
                    description="d", input_schema={}, owner="t",
                ),
                lambda inputs: {},
            )

    def test_duplicate_toolkit_refused(self):
        reg = ToolRegistry()
        tk = ToolkitDescriptor(id="t", description="d")
        reg.register_toolkit(tk)
        with pytest.raises(ToolRegistryError, match="duplicate_toolkit"):
            reg.register_toolkit(tk)

    def test_duplicate_tool_refused(self):
        reg = ToolRegistry()
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
        reg = ToolRegistry()
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
        reg = ToolRegistry(permission_grant=grant)
        register_default_toolkits(
            reg,
            host=HostCapabilities(apply_patch=True, shell=True, update_plan=True),
            task_manager=_FakeTaskManager(),
            repo_root="/tmp",
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
        grant = StaticGrant(permissions={"caller": frozenset({"read_only"})})
        reg = self._registry(grant)
        ids = {t.id for t in reg.list_tools("caller")}
        # read_only-permitted tools:
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

    def test_list_tools_scoped_to_toolkit(self):
        grant = StaticGrant(permissions={"caller": frozenset({"read_only"})})
        reg = self._registry(grant)
        ids = {t.id for t in reg.list_tools("caller", toolkit_id="task_management")}
        assert ids == {"get_task_status", "update_task_progress", "update_plan"}

    def test_list_tools_rejects_unknown_toolkit(self):
        reg = self._registry(StaticGrant(permissions={"c": frozenset()}))
        with pytest.raises(ToolRegistryError, match="unknown_toolkit"):
            reg.list_tools("c", toolkit_id="imaginary")

    def test_empty_grant_sees_nothing(self):
        """Default EmptyGrant refuses every permission."""
        reg = ToolRegistry(permission_grant=EmptyGrant())
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
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "owner": frozenset({
                    "read_only", "code_search", "repository_read",
                    "filesystem_write", "network",
                }),
            })
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
        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "o": frozenset({"filesystem_write", "network"})
            })
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
        reg = ToolRegistry(permission_grant=grant)
        register_default_toolkits(
            reg,
            host=HostCapabilities(apply_patch=True, shell=True, update_plan=True),
            task_manager=self._tm,
            repo_root="/tmp",
        )
        return reg

    def setup_method(self):
        self._tm = _FakeTaskManager()
        self._tm.create_task("tid-1", {"revision": 1, "stage": "plan"})

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
        reg = self._registry(StaticGrant(permissions={"o": frozenset({"read_only"})}))
        out = reg.dispatch(
            "o", "update_task_progress",
            {"task_id": "tid-1", "progress_note": "half-way"},
        )
        assert out["new_revision"] == 2
        task = self._tm.get_task("tid-1")
        assert task.metadata["revision"] == 2
        trail = task.metadata.get("progress_trail", [])
        assert len(trail) == 1
        assert trail[0]["note"] == "half-way"

    def test_update_plan_is_advisory_only(self):
        """update_plan does NOT write to TaskManager — preserves ownership boundary."""
        reg = self._registry(StaticGrant(permissions={"o": frozenset({"read_only"})}))
        before = self._tm.get_task("tid-1").metadata["revision"]
        out = reg.dispatch(
            "o", "update_plan",
            {"task_id": "tid-1", "step": "sketch", "note": "advisory only"},
        )
        after = self._tm.get_task("tid-1").metadata["revision"]
        assert before == after  # TaskManager state unchanged
        assert out["advisory"] is True
        assert out["plan_entries"] == 1


# ---------------------------------------------------------------------------
# MCP tool category: registration, dispatch forwarding, missing connector
# ---------------------------------------------------------------------------


class TestMCPTools:
    def test_mcp_tool_registration_requires_connector(self):
        reg = ToolRegistry()
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

        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={"o": frozenset({"mcp"})})
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

        reg = ToolRegistry(
            permission_grant=StaticGrant(permissions={
                "with-mcp": frozenset({"mcp"}),
                "without-mcp": frozenset(),
            })
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
            permission_grant=StaticGrant(permissions={"o": frozenset({"read_only"})})
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
            permission_grant=StaticGrant(permissions={"o": frozenset({"read_only"})})
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
