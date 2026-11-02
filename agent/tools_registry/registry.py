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

from agent.prompt_authoring.store import Principal
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


def _require_jsonschema():
    """Return the jsonschema module or raise ToolRegistryError.

    M3-addon reviewer directive: full schema validation is MANDATORY for
    dispatch; the former silent fallback to a required-key subset check is
    rejected.
    """
    try:
        import jsonschema  # type: ignore
    except ImportError as exc:  # pragma: no cover - exercised in test
        raise ToolRegistryError(
            "schema_validation_unavailable: jsonschema is required for dispatch. "
            "Install `pip install jsonschema>=4.0`."
        ) from exc
    return jsonschema


class ToolRegistry:
    """Append-only, principal-gated registry of toolkits and tools."""

    def __init__(
        self,
        *,
        permission_grant: PermissionGrant | None = None,
        trust_actor_strings: bool = False,
    ) -> None:
        """Build a registry.

        * ``permission_grant`` — maps principal name to granted permission set.
        * ``trust_actor_strings`` — when True, discovery and dispatch accept
          a bare principal_name string instead of a verified Principal. This
          is the pre-corrective backward-compat path and is intended for
          tests and single-process trusted sessions. Production deployments
          MUST pass verified Principal objects (M1 contract) and keep this
          at the default False.
        """
        self._toolkits: dict[str, ToolkitDescriptor] = {}
        self._tools: dict[str, ToolDescriptor] = {}
        self._impls: dict[str, FunctionImpl] = {}
        self._mcp_invokers: dict[str, Any] = {}
        self._grant: PermissionGrant = permission_grant or EmptyGrant()
        self._trust_actor_strings = trust_actor_strings

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
    # Identity resolution (M1 Principal contract)
    # ------------------------------------------------------------------

    def _resolve_principal(self, caller: Principal | str) -> str:
        """Return the authenticated name, or raise ToolRegistryError.

        A verified Principal (from an IdentityProvider) is always accepted.
        An unverified Principal is accepted ONLY in trust_actor_strings mode.
        A bare string is accepted ONLY in trust_actor_strings mode.
        """
        if isinstance(caller, Principal):
            if caller.verified:
                return caller.name
            if self._trust_actor_strings:
                return caller.name
            raise ToolRegistryError(
                f"untrusted_identity: Principal {caller.name!r} is unverified. "
                "Obtain a verified Principal via an IdentityProvider or construct "
                "the registry with trust_actor_strings=True (tests only)."
            )
        if isinstance(caller, str):
            if self._trust_actor_strings:
                return caller
            raise ToolRegistryError(
                "untrusted_identity: discovery and dispatch require a verified "
                "Principal; bare principal_name strings are refused. Construct "
                "the registry with trust_actor_strings=True (tests only), or "
                "pass a verified Principal."
            )
        raise ToolRegistryError(
            f"untrusted_identity: expected Principal or str, got {type(caller).__name__}"
        )

    # ------------------------------------------------------------------
    # Discovery — list_toolkits / list_tools
    # ------------------------------------------------------------------

    def list_toolkits(self, caller: Principal | str) -> list[ToolkitDescriptor]:
        """Return toolkits visible to the authorized caller.

        A toolkit is visible when the caller holds grants for at least one
        tool registered under it. An empty toolkit is also visible — the
        host may want to see that an empty toolkit is wired up — but it is
        only reported if it was registered (unknown toolkits are rejected
        by `list_tools`).
        """
        principal_name = self._resolve_principal(caller)
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
        caller: Principal | str,
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
        principal_name = self._resolve_principal(caller)
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
        caller: Principal | str,
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
        principal_name = self._resolve_principal(caller)
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
            # M3-addon reviewer directive (C2): a Function Tool may need the
            # verified caller identity to enforce ownership. Impls that opt in
            # by setting `_principal_aware = True` receive (inputs, principal_name)
            # — legacy impls keep the single-argument contract.
            # Narrow via Any so mypy accepts the two-signature contract.
            impl_any: Any = impl
            if getattr(impl, "_principal_aware", False):
                return impl_any(payload, principal_name)
            return impl_any(payload)
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
        """Full JSON Schema validation (mandatory, no silent fallback).

        M3-addon reviewer directive: the pre-corrective silent fallback to a
        required-key subset check is refused. If jsonschema is missing the
        dispatcher raises `schema_validation_unavailable` so the deployment
        gap is loud.
        """
        schema = tool.input_schema or {}
        jsonschema = _require_jsonschema()
        try:
            jsonschema.validate(inputs, schema)
        except jsonschema.ValidationError as exc:
            raise ToolRegistryError(
                f"invalid_input: {tool.id!r} inputs failed schema: {exc.message}"
            ) from exc
        except jsonschema.SchemaError as exc:
            raise ToolRegistryError(
                f"invalid_schema: {tool.id!r} declared an invalid input_schema: "
                f"{exc.message}"
            ) from exc

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
