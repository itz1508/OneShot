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

import dataclasses
import itertools
import json
import threading
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as _FutureTimeout
from typing import Any

from agent.prompt_authoring.store import Principal
from agent.tools_registry.types import (
    DispatchAuditEntry,
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
        input_byte_limit: int = 256 * 1024,
        default_timeout_s: float = 30.0,
        audit_max_entries: int = 10_000,
        dispatch_workers: int = 4,
    ) -> None:
        """Build a registry.

        * ``permission_grant`` — maps principal name to granted permission set.
        * ``trust_actor_strings`` — when True, discovery and dispatch accept
          a bare principal_name string instead of a verified Principal. This
          is the pre-corrective backward-compat path and is intended for
          tests and single-process trusted sessions. Production deployments
          MUST pass verified Principal objects (M1 contract) and keep this
          at the default False.
        * ``input_byte_limit`` — refuse dispatch inputs whose canonical JSON
          serialisation exceeds this many bytes. Protects against DoS
          through oversized payloads; set to ``0`` to disable.
        * ``default_timeout_s`` — hard wall-clock cap for a single dispatch
          call. Function and MCP tools run on a persistent ThreadPoolExecutor
          and the caller returns at the deadline whether or not the worker
          has finished; see ``_invoke_with_timeout`` and ``reconcile_pending``
          for the side-effect reconciliation contract. Set to ``0`` to
          disable (not recommended).
        * ``audit_max_entries`` — ring-buffer bound on the in-process audit
          log. The oldest entries are evicted first; set to 0 to make the
          buffer unbounded (NOT recommended — OOM risk under high dispatch
          volume).
        * ``dispatch_workers`` — worker-thread pool size for the persistent
          dispatch executor. Must be >= 1. Independent of per-call
          ``timeout_s``: workers that outlive a ``tool_timeout`` continue
          running until they return of their own accord (Python has no safe
          thread cancellation); their eventual settlement is observed via
          ``reconcile_pending()``.
        """
        self._toolkits: dict[str, ToolkitDescriptor] = {}
        self._tools: dict[str, ToolDescriptor] = {}
        self._impls: dict[str, FunctionImpl] = {}
        self._mcp_invokers: dict[str, Any] = {}
        self._input_byte_limit = int(input_byte_limit)
        self._default_timeout_s = float(default_timeout_s)
        # Structured audit log — one DispatchAuditEntry per dispatch
        # attempt. Append-only in-process (durable persistence stays with
        # TaskManager — single-ownership rule); ring-buffered under a lock
        # for retention bounds and thread safety.
        cap = int(audit_max_entries)
        self._audit_cap: int | None = cap if cap > 0 else None
        self._audit: deque[DispatchAuditEntry] = deque(maxlen=self._audit_cap)
        self._audit_lock = threading.Lock()
        self._audit_counter: itertools.count[int] = itertools.count(1)
        # Pending "tool_timeout" dispatches — the caller has already received
        # tool_timeout but the worker Future is still live. Reconciliation
        # (see reconcile_pending) updates the audit entry once the Future
        # completes or fails. Map: entry_id -> _PendingTimeout dict.
        self._pending_timeouts: dict[int, dict[str, Any]] = {}
        # Persistent dispatch executor. One pool for the registry's
        # lifetime — a per-call ``with ThreadPoolExecutor(...) as pool:``
        # would ``shutdown(wait=True)`` on exit and silently defeat the
        # caller-side timeout.
        workers = max(1, int(dispatch_workers))
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="tool_dispatch"
        )
        self._closed = False
        # Per-registry provenance marker. Only IdentityProviders obtained via
        # self.identity_provider(credentials) bake this token into their
        # Principals; _resolve_principal rejects verified Principals whose
        # issuer_token does not match. Independently-minted IdentityProvider
        # instances fail — the reviewer directive #1 ("Establish trusted host
        # identity provenance; reject independently minted identities").
        self._host_token: object = object()
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
        """Register an MCP tool backed by `connector.invoke(tool_id, inputs)`.

        Reviewer directive #7:
          * Each MCP tool MUST declare non-empty ``effects`` — a connector
            exposing an opaque remote operation cannot be registered with
            effects=() because the registry would then advertise it as a
            pure read.
          * The connector MUST declare its own
            ``required_connector_permissions`` set. The registry UNIONs
            them into the descriptor's ``required_permissions`` so the
            discovery filter sees both the per-tool AND per-connector
            permissions.
        """
        self._assert_registerable(descriptor, expected_kind=ToolKind.MCP)
        if not hasattr(connector, "invoke"):
            raise ToolRegistryError(
                f"invalid_mcp_connector: connector for {descriptor.id!r} is missing "
                "an `invoke(tool_id, inputs)` method."
            )
        if not descriptor.effects or (
            len(descriptor.effects) == 1 and descriptor.effects[0] == ""
        ):
            raise ToolRegistryError(
                f"invalid_mcp_tool: {descriptor.id!r} must declare non-empty effects "
                "(reviewer directive: enforce individual MCP tool effects)."
            )
        connector_perms = tuple(
            getattr(connector, "required_connector_permissions", ()) or ()
        )
        if not isinstance(connector_perms, tuple):
            raise ToolRegistryError(
                f"invalid_mcp_connector: {descriptor.id!r} connector's "
                "required_connector_permissions must be an iterable of strings."
            )
        for perm in connector_perms:
            if not isinstance(perm, str):
                raise ToolRegistryError(
                    f"invalid_mcp_connector: {descriptor.id!r} connector has a "
                    f"non-string permission token ({type(perm).__name__})."
                )
        # Union connector permissions into the descriptor's required_permissions.
        from dataclasses import replace as _replace
        effective = tuple(sorted(set(descriptor.required_permissions) | set(connector_perms)))
        effective_desc = _replace(descriptor, required_permissions=effective)
        self._tools[descriptor.id] = effective_desc
        self._mcp_invokers[descriptor.id] = connector
        self._bump_toolkit_count(effective_desc)

    # Toolkit "mcp" is a sentinel — only MCP tools may be registered under it.
    # This keeps the three kinds (Function / Host-native / MCP) distinct
    # (reviewer directive #7).
    _MCP_RESERVED_TOOLKITS: frozenset[str] = frozenset({"mcp"})

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
        if (
            descriptor.toolkit in self._MCP_RESERVED_TOOLKITS
            and descriptor.kind != ToolKind.MCP
        ):
            raise ToolRegistryError(
                f"wrong_kind: tool {descriptor.id!r} targets toolkit "
                f"{descriptor.toolkit!r} which is reserved for MCP tools, "
                f"got {descriptor.kind.value!r}."
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
                if caller.issuer_token is self._host_token:
                    return caller.name
                if self._trust_actor_strings:
                    return caller.name
                raise ToolRegistryError(
                    f"untrusted_identity: Principal {caller.name!r} was issued by "
                    "a different host than this registry. Obtain the Principal "
                    "via ToolRegistry.identity_provider(credentials=...) so it "
                    "carries this registry's host provenance token."
                )
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

    def identity_provider(self, *, credentials: dict[str, str]):
        """Return an IdentityProvider sealed to THIS registry's host_token.

        Reviewer directive #1: trusted host identity provenance. A caller who
        builds their own IdentityProvider cannot forge our private host_token
        reference, so the registry rejects verified Principals that didn't
        come from this factory.
        """
        from agent.prompt_authoring.store import IdentityProvider

        return IdentityProvider(credentials=credentials, issuer_token=self._host_token)

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
        *,
        timeout_s: float | None = None,
    ) -> Any:
        """Execute a registered Function or MCP tool.

        Fails closed with ``ToolRegistryError`` for:
          * tool_id the caller cannot see (visibility == dispatchability).
          * ``available=False`` tools.
          * inputs whose canonical JSON exceeds the registry's
            ``input_byte_limit`` (``input_too_large``).
          * inputs that fail the tool's ``input_schema``.
          * HOST_NATIVE tools (the host owns their execution; the registry
            discovers them only).
          * a tool that exceeds the per-call ``timeout_s`` (``tool_timeout``).

        The dispatcher writes one ``DispatchAuditEntry`` per attempt to its
        in-process audit log (readable via ``audit_log(caller=...)``). Error
        entries name the exception class but never the exception message,
        which may carry sensitive data.

        A ``tool_timeout`` entry starts with ``side_effect_state="uncertain"``
        and ``worker_termination_confirmed=False``. The audit record is
        promoted to ``settled`` / ``settled_error`` by
        ``reconcile_pending()`` once the worker's Future completes.
        """
        if self._closed:
            raise ToolRegistryError("registry_closed: dispatch after close()")
        start = time.monotonic()
        payload = inputs or {}
        error_class: str | None = None
        status = "ok"
        principal_name = "<unresolved>"
        payload_bytes = 0
        side_effect_state = "ok"
        worker_termination_confirmed = True
        # Pre-allocate an entry id so a tool_timeout can reference it in
        # _pending_timeouts before the finally block appends.
        entry_id = next(self._audit_counter)
        try:
            principal_name = self._resolve_principal(caller)
            try:
                payload_bytes = len(
                    json.dumps(payload, sort_keys=True, separators=(",", ":"))
                    .encode("utf-8")
                )
            except Exception:  # noqa: BLE001 - payload may be non-JSON-ish
                payload_bytes = len(repr(payload).encode("utf-8", errors="replace"))
            if self._input_byte_limit and payload_bytes > self._input_byte_limit:
                status = "input_too_large"
                raise ToolRegistryError(
                    f"input_too_large: payload is {payload_bytes} bytes; "
                    f"limit is {self._input_byte_limit}."
                )
            tool = self._tools.get(tool_id)
            granted = self._grant.granted(principal_name)
            if tool is None or not self._caller_sees_tool(tool, granted):
                status = "unknown_tool"
                raise ToolRegistryError(
                    f"unknown_tool: {tool_id!r} is not registered or not permitted "
                    f"for principal {principal_name!r}."
                )
            self._validate_inputs(tool, payload)
            effective_timeout = (
                float(timeout_s) if timeout_s is not None else self._default_timeout_s
            )
            return self._invoke_with_timeout(
                tool, payload, principal_name, effective_timeout, entry_id
            )
        except ToolRegistryError as exc:
            if status == "ok":
                msg = str(exc)
                status = msg.split(":", 1)[0] if ":" in msg else "invalid_input"
            # tool_timeout -> uncertain side effects.
            if status == "tool_timeout":
                side_effect_state = "uncertain"
                worker_termination_confirmed = False
            raise
        except Exception as exc:  # noqa: BLE001 - re-raise after audit
            error_class = type(exc).__name__
            if status == "ok":
                status = "error"
            raise
        finally:
            entry = DispatchAuditEntry(
                at=time.time(),
                principal=principal_name,
                tool_id=tool_id,
                status=status,
                duration_ms=round((time.monotonic() - start) * 1000, 3),
                error_class=error_class,
                input_bytes=payload_bytes,
                worker_termination_confirmed=worker_termination_confirmed,
                side_effect_state=side_effect_state,
                entry_id=entry_id,
            )
            with self._audit_lock:
                self._audit.append(entry)

    def _invoke_with_timeout(
        self,
        tool: ToolDescriptor,
        payload: dict[str, Any],
        principal_name: str,
        timeout_s: float,
        entry_id: int,
    ) -> Any:
        """Run a FUNCTION or MCP tool with a wall-clock timeout.

        The dispatch executor is persistent for the registry's lifetime
        (see ``__init__``), so a ``tool_timeout`` returns control to the
        caller IMMEDIATELY — the executor's ``shutdown(wait=True)`` is
        avoided by not entering a per-call ``with ThreadPoolExecutor(...)``
        block. The worker Future is NOT force-cancelled: Python has no
        safe thread cancellation, and ``Future.cancel()`` only drops
        work that has not started yet.

        When the Future outlives the caller's deadline the entry is kept
        in ``self._pending_timeouts`` and the paired audit record is
        marked ``side_effect_state="uncertain"``. Callers performing a
        write MUST pass the uncertain record through
        ``ToolRegistry.reconcile_pending()`` before retrying — the tool
        may have already applied its effect in the detached worker.
        """
        def _run() -> Any:
            if tool.kind == ToolKind.FUNCTION:
                impl = self._impls[tool.id]
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
            raise ToolRegistryError(
                f"host_native_dispatch: {tool.id!r} is host-native; dispatch is "
                "owned by the host, not the registry."
            )

        if timeout_s <= 0:
            return _run()
        fut: Future[Any] = self._executor.submit(_run)
        try:
            return fut.result(timeout=timeout_s)
        except _FutureTimeout as exc:
            # Record the still-running Future for later reconciliation.
            # We attempt a soft cancel first — it only succeeds if the
            # worker never started — but mostly we accept that the
            # worker is detached.
            cancelled = fut.cancel()
            with self._audit_lock:
                self._pending_timeouts[entry_id] = {
                    "future": fut,
                    "tool_id": tool.id,
                    "principal": principal_name,
                    "deadline_s": float(timeout_s),
                    "submitted_at": time.time(),
                    "cancel_attempted": True,
                    "cancel_succeeded": cancelled,
                }
            raise ToolRegistryError(
                f"tool_timeout: {tool.id!r} did not return within "
                f"{timeout_s:g}s. Worker is detached; call "
                "ToolRegistry.reconcile_pending() before retrying any write."
            ) from exc

    def audit_log(
        self,
        caller: Principal | str | None = None,
        *,
        principal: str | None = None,
        tool_id: str | None = None,
        status: str | None = None,
    ) -> list[DispatchAuditEntry]:
        """Return a filtered view of the in-process dispatch audit log.

        Access control
        --------------
        Reading the audit log can disclose which principals called which
        tools and when, so the view is gated by the ``audit_read`` or
        ``task_admin`` permission. When ``permission_grant`` is set the
        caller is required and must present a verified Principal (or a
        bare string if ``trust_actor_strings=True``); the view is empty
        when neither permission is granted.

        Backward compatibility
        ----------------------
        A legacy ``audit_log()`` call with no caller is accepted only when
        no ``permission_grant`` is configured — i.e. the registry is in
        an un-gated test-harness mode. Any registry with grants wired up
        refuses unauthenticated reads with ``untrusted_identity``.
        """
        if isinstance(self._grant, EmptyGrant):
            # Un-gated registry — legacy behaviour; no caller required.
            pass
        else:
            if caller is None:
                raise ToolRegistryError(
                    "untrusted_identity: audit_log requires a caller "
                    "(Principal or str) when a permission_grant is set."
                )
            principal_name = self._resolve_principal(caller)
            granted = self._grant.granted(principal_name)
            if not ({"audit_read", "task_admin"} & granted):
                raise ToolRegistryError(
                    f"insufficient_permission: {principal_name!r} needs "
                    "`audit_read` or `task_admin` to read the audit log."
                )
        with self._audit_lock:
            out = list(self._audit)
        if principal is not None:
            out = [e for e in out if e.principal == principal]
        if tool_id is not None:
            out = [e for e in out if e.tool_id == tool_id]
        if status is not None:
            out = [e for e in out if e.status == status]
        return out

    def reconcile_pending(
        self,
        caller: Principal | str | None = None,
    ) -> list[DispatchAuditEntry]:
        """Observe completed-after-timeout workers; rewrite audit entries.

        Returns the list of audit entries updated by this call (empty when
        every detached worker is still running).

        For each Future recorded by ``_invoke_with_timeout``:
          * ``future.done() is False`` — leave the ``uncertain`` audit
            entry in place; the worker is still running.
          * ``future.done() is True`` and no exception — replace the
            audit entry with ``side_effect_state="settled"`` and
            ``worker_termination_confirmed=True``.
          * ``future.done() is True`` and ``future.exception()`` set —
            replace the audit entry with ``side_effect_state="settled_error"``,
            ``error_class`` recording the exception type (never the
            message), and ``worker_termination_confirmed=True``.

        Access control mirrors ``audit_log`` — ``audit_read`` or
        ``task_admin``. The audit entry may have been evicted from the
        retention ring buffer; in that case the Future's result is still
        drained from ``_pending_timeouts`` but the return list simply
        omits the vanished record.
        """
        if not isinstance(self._grant, EmptyGrant):
            if caller is None:
                raise ToolRegistryError(
                    "untrusted_identity: reconcile_pending requires a caller "
                    "when a permission_grant is set."
                )
            principal_name = self._resolve_principal(caller)
            granted = self._grant.granted(principal_name)
            if not ({"audit_read", "task_admin"} & granted):
                raise ToolRegistryError(
                    f"insufficient_permission: {principal_name!r} needs "
                    "`audit_read` or `task_admin` to reconcile pending timeouts."
                )
        updated: list[DispatchAuditEntry] = []
        with self._audit_lock:
            pending_now = list(self._pending_timeouts.items())
            for entry_id, meta in pending_now:
                fut: Future[Any] = meta["future"]
                if not fut.done():
                    continue
                exc = fut.exception()
                if exc is None:
                    new_state = "settled"
                    error_class = None
                else:
                    new_state = "settled_error"
                    error_class = type(exc).__name__
                # Locate the audit entry (may have been evicted). Audit is
                # a deque; linear scan is acceptable at retention sizes.
                replaced = None
                for idx, old in enumerate(self._audit):
                    if old.entry_id != entry_id:
                        continue
                    replaced = dataclasses.replace(
                        old,
                        side_effect_state=new_state,
                        worker_termination_confirmed=True,
                        error_class=error_class if error_class is not None
                        else old.error_class,
                    )
                    self._audit[idx] = replaced
                    break
                self._pending_timeouts.pop(entry_id, None)
                if replaced is not None:
                    updated.append(replaced)
        return updated

    def pending_timeouts(
        self, caller: Principal | str | None = None
    ) -> list[int]:
        """Return the entry ids of currently-detached timed-out workers.

        Audit-read gated like ``audit_log`` / ``reconcile_pending``.
        """
        if not isinstance(self._grant, EmptyGrant):
            if caller is None:
                raise ToolRegistryError(
                    "untrusted_identity: pending_timeouts requires a caller "
                    "when a permission_grant is set."
                )
            principal_name = self._resolve_principal(caller)
            granted = self._grant.granted(principal_name)
            if not ({"audit_read", "task_admin"} & granted):
                raise ToolRegistryError(
                    f"insufficient_permission: {principal_name!r} needs "
                    "`audit_read` or `task_admin` to read pending timeouts."
                )
        with self._audit_lock:
            return list(self._pending_timeouts.keys())

    def close(self) -> None:
        """Shut down the dispatch executor without waiting on live workers.

        Idempotent. After ``close()`` any further ``dispatch`` call fails
        with ``registry_closed``. Pending futures from timed-out dispatches
        are NOT awaited — they continue running until the Python
        interpreter exits (or the process is terminated). Call
        ``reconcile_pending()`` before ``close()`` if you want to settle
        the audit log first.
        """
        if self._closed:
            return
        self._closed = True
        self._executor.shutdown(wait=False)

    def __enter__(self) -> ToolRegistry:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:  # pragma: no cover - best-effort cleanup
        import contextlib
        with contextlib.suppress(Exception):
            self.close()

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
