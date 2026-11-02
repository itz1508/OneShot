"""Toolkit / Tool registry — discovery and the authorized dispatch boundary.

Design pins (reviewer directive, verbatim):

  * list_toolkits / list_tools are DISCOVERY. They never execute a tool,
    never grant permissions, never authorize Build actions.
  * Function Tools, Host-native tools, and MCP Tools stay distinctly
    typed via `ToolKind`.
  * `list_tools()` returns only tools actually available AND permitted
    for the authenticated caller.
  * MCP tools come in through a separate registration path (an MCP
    connector); they are NOT hard-coded into default registrations.
  * `dispatch()` is the authorized tool-dispatch boundary: it refuses
    unknown tools, unknown toolkits, inputs that fail `input_schema`,
    and callers whose grant does not satisfy `required_permissions`.
    Discovery and dispatch share the same filter so a tool a caller
    cannot see is also one the caller cannot invoke.

Ownership boundaries:
  * The registry reuses `CapabilityRegistry` for version/effect metadata.
  * Dispatch for FUNCTION tools runs the registered callable in-process.
  * HOST_NATIVE tools do not have an in-process callable — `dispatch()`
    on a HOST_NATIVE tool raises `ToolRegistryError('host_native_dispatch')`.
    The host owns their execution; the registry's job is discovery
    only. (The reviewer explicitly scoped list_toolkits / list_tools to
    discovery.)
  * MCP tools are dispatched through the MCP connector that registered
    them; the registry forwards the call to the connector's `invoke()`
    method.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.tools_registry.types import (
    EmptyGrant,
    PermissionGrant,
    ToolDescriptor,
    ToolKind,
    ToolkitDescriptor,
    ToolRegistryError,
)

# A callable with the shape `fn(inputs: dict) -> Any` for FUNCTION tools, or
# an object with an `invoke(tool_id, inputs) -> Any` method for MCP tools.
FunctionImpl = Callable[[dict[str, Any]], Any]


class ToolRegistry:
    """Append-only, principal-gated registry of toolkits and tools."""

    def __init__(
        self,
        *,
        permission_grant: PermissionGrant | None = None,
    ) -> None:
        self._toolkits: dict[str, ToolkitDescriptor] = {}
        self._tools: dict[str, ToolDescriptor] = {}
        self._impls: dict[str, FunctionImpl] = {}
        self._mcp_invokers: dict[str, Any] = {}
        self._grant: PermissionGrant = permission_grant or EmptyGrant()

    # ------------------------------------------------------------------
    # Registration — toolkits and tools
    # ------------------------------------------------------------------

    def register_toolkit(self, descriptor: ToolkitDescriptor) -> None:
        if descriptor.id in self._toolkits:
            raise ToolRegistryError(
                f"duplicate_toolkit: {descriptor.id!r} is already registered."
            )
        self._toolkits[descriptor.id] = descriptor

    def register_function_tool(
        self,
        descriptor: ToolDescriptor,
        implementation: FunctionImpl,
    ) -> None:
        self._assert_registerable(descriptor, expected_kind=ToolKind.FUNCTION)
        self._tools[descriptor.id] = descriptor
        self._impls[descriptor.id] = implementation
        self._bump_toolkit_count(descriptor)

    def register_host_native_tool(self, descriptor: ToolDescriptor) -> None:
        self._assert_registerable(descriptor, expected_kind=ToolKind.HOST_NATIVE)
        self._tools[descriptor.id] = descriptor
        self._bump_toolkit_count(descriptor)

    def register_mcp_tool(
        self,
        descriptor: ToolDescriptor,
        connector: Any,
    ) -> None:
        self._assert_registerable(descriptor, expected_kind=ToolKind.MCP)
        if not hasattr(connector, "invoke"):
            raise ToolRegistryError(
                f"invalid_mcp_connector: connector for {descriptor.id!r} is missing "
                "an `invoke(tool_id, inputs)` method."
            )
        self._tools[descriptor.id] = descriptor
        self._mcp_invokers[descriptor.id] = connector
        self._bump_toolkit_count(descriptor)

    def _assert_registerable(
        self, descriptor: ToolDescriptor, *, expected_kind: ToolKind
    ) -> None:
        if descriptor.toolkit not in self._toolkits:
            raise ToolRegistryError(
                f"unknown_toolkit: tool {descriptor.id!r} references toolkit "
                f"{descriptor.toolkit!r} which has not been registered."
            )
        if descriptor.kind != expected_kind:
            raise ToolRegistryError(
                f"wrong_kind: {descriptor.id!r} is {descriptor.kind.value!r}, "
                f"expected {expected_kind.value!r} for this registration path."
            )
        if descriptor.id in self._tools:
            raise ToolRegistryError(
                f"duplicate_tool: {descriptor.id!r} is already registered."
            )

    def _bump_toolkit_count(self, descriptor: ToolDescriptor) -> None:
        current = self._toolkits[descriptor.toolkit]
        kinds = tuple(sorted({*current.kinds, descriptor.kind}, key=lambda k: k.value))
        self._toolkits[descriptor.toolkit] = ToolkitDescriptor(
            id=current.id,
            description=current.description,
            version=current.version,
            owner=current.owner,
            registered_tool_count=current.registered_tool_count + 1,
            kinds=kinds,
        )

    # ------------------------------------------------------------------
    # Discovery — list_toolkits / list_tools
    # ------------------------------------------------------------------

    def list_toolkits(self, principal_name: str) -> list[ToolkitDescriptor]:
        """Return toolkits visible to the authorized caller.

        A toolkit is visible when the caller holds grants for at least one
        tool registered under it. An empty toolkit is also visible — the
        host may want to see that an empty toolkit is wired up — but it is
        only reported if it was registered (unknown toolkits are rejected
        by `list_tools`).
        """
        granted = self._grant.granted(principal_name)
        visible: list[ToolkitDescriptor] = []
        for tk_id, tk in self._toolkits.items():
            if any(
                self._caller_sees_tool(t, granted)
                for t in self._tools.values()
                if t.toolkit == tk_id
            ) or tk.registered_tool_count == 0:
                visible.append(tk)
        # Deterministic order — by id — so repeated calls return the same list.
        return sorted(visible, key=lambda d: d.id)

    def list_tools(
        self,
        principal_name: str,
        *,
        toolkit_id: str | None = None,
    ) -> list[ToolDescriptor]:
        """Return registered, callable tools permitted for the caller.

        Reviewer: 'list_tools returns only tools actually available and
        permitted for the authenticated caller and current workflow context.'

        An unknown `toolkit_id` is a hard refusal — it is NOT silently
        treated as an empty result.
        """
        if toolkit_id is not None and toolkit_id not in self._toolkits:
            raise ToolRegistryError(f"unknown_toolkit: {toolkit_id!r}")
        granted = self._grant.granted(principal_name)
        tools = []
        for tool in self._tools.values():
            if toolkit_id is not None and tool.toolkit != toolkit_id:
                continue
            if not self._caller_sees_tool(tool, granted):
                continue
            tools.append(tool)
        return sorted(tools, key=lambda d: d.id)

    def _caller_sees_tool(
        self, tool: ToolDescriptor, granted: set[str]
    ) -> bool:
        if not tool.available:
            return False
        return all(perm in granted for perm in tool.required_permissions)

    # ------------------------------------------------------------------
    # Dispatch — the authorized tool-dispatch boundary
    # ------------------------------------------------------------------

    def dispatch(
        self,
        principal_name: str,
        tool_id: str,
        inputs: dict[str, Any] | None = None,
    ) -> Any:
        """Execute a registered Function or MCP tool.

        Fails closed with `ToolRegistryError` for:
          * tool_id the caller cannot see (visibility == dispatchability).
          * `available=False` tools.
          * inputs that fail the tool's input_schema.
          * HOST_NATIVE tools (the host owns their execution; the registry
            discovers them only).
          * missing MCP connector (should not happen if registration path
            was used, but guarded nonetheless).

        The dispatcher validates inputs against `input_schema` using
        `jsonschema` when available; otherwise it falls back to a
        required-key subset check (mirroring BehaviorEvaluator's
        degrade-gracefully pattern).
        """
        tool = self._tools.get(tool_id)
        granted = self._grant.granted(principal_name)
        if tool is None or not self._caller_sees_tool(tool, granted):
            raise ToolRegistryError(
                f"unknown_tool: {tool_id!r} is not registered or not permitted "
                f"for principal {principal_name!r}."
            )
        payload = inputs or {}
        self._validate_inputs(tool, payload)
        if tool.kind == ToolKind.FUNCTION:
            impl = self._impls[tool.id]
            return impl(payload)
        if tool.kind == ToolKind.MCP:
            connector = self._mcp_invokers.get(tool.id)
            if connector is None:
                raise ToolRegistryError(
                    f"missing_mcp_connector: {tool.id!r}"
                )
            return connector.invoke(tool.id, payload)
        # HOST_NATIVE and anything else: discovery only.
        raise ToolRegistryError(
            f"host_native_dispatch: {tool.id!r} is host-native; dispatch is "
            "owned by the host, not the registry."
        )

    def _validate_inputs(
        self, tool: ToolDescriptor, inputs: dict[str, Any]
    ) -> None:
        schema = tool.input_schema or {}
        try:
            import jsonschema  # type: ignore
        except Exception:
            jsonschema = None  # type: ignore
        if jsonschema is not None:
            try:
                jsonschema.validate(inputs, schema)
                return
            except jsonschema.ValidationError as exc:
                raise ToolRegistryError(
                    f"invalid_input: {tool.id!r} inputs failed schema: {exc.message}"
                ) from exc
        required = schema.get("required") or []
        missing = [k for k in required if k not in inputs]
        if missing:
            raise ToolRegistryError(
                f"invalid_input: {tool.id!r} missing required keys: {missing!r}"
            )

    # ------------------------------------------------------------------
    # Convenience accessors (used by defaults & tests)
    # ------------------------------------------------------------------

    def toolkit(self, toolkit_id: str) -> ToolkitDescriptor | None:
        return self._toolkits.get(toolkit_id)

    def tool(self, tool_id: str) -> ToolDescriptor | None:
        return self._tools.get(tool_id)

    def all_toolkits(self) -> list[ToolkitDescriptor]:
        return sorted(self._toolkits.values(), key=lambda d: d.id)

    def all_tools(self) -> list[ToolDescriptor]:
        return sorted(self._tools.values(), key=lambda d: d.id)


__all__ = ["ToolRegistry"]
