"""Toolkit / Tool discovery types.

Each `ToolDescriptor` carries:

  * stable `id` — never recycled across tool identities.
  * `toolkit` — the owning toolkit id (foreign key into `ToolkitDescriptor`).
  * `kind` — Function / Host-native / MCP. The three categories STAY DISTINCT
    (reviewer directive).
  * `description`, `version`, `owner`, `effects`, `available` — reused from
    `CapabilityDescriptor` semantics.
  * `input_schema` — JSON Schema for the tool's inputs. Discovery clients can
    validate inputs client-side before dispatch.
  * `required_permissions` — list of permission tokens the caller must hold
    (same closed vocabulary as `agent.prompt_authoring.types.ToolPermission`).

`HostCapabilities` tells the registry which host-native tools the host
actually advertises; `apply_patch`, `shell`, and `update_plan` are registered
only when the host says they are supported, per reviewer directive.

`PermissionGrant` is the injectable permission oracle. The default
`EmptyGrant` refuses everything — the host MUST supply a grant that maps
`principal -> set[ToolPermission.value]` for any tool to pass dispatch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class ToolKind(str, Enum):
    """Three distinct categories, verbatim from the reviewer directive.

    FUNCTION — Custom Function Tool, callable in-process by the controller.
    HOST_NATIVE — a tool provided by the agent host (e.g. apply_patch, shell).
                  Registered ONLY when the host advertises it.
    MCP — a tool exposed via the Model Context Protocol tools/list contract.
          Discovered through an MCP connector, not hard-coded.
    """

    FUNCTION = "function"
    HOST_NATIVE = "host_native"
    MCP = "mcp"


class ToolRegistryError(RuntimeError):
    """Any discovery / registration / dispatch error.

    The message carries a short classification key so callers can branch:
      * ``unknown_toolkit`` — `list_tools(toolkit_id=…)` referenced a toolkit
        the registry does not know.
      * ``unknown_tool`` — `dispatch(..., tool_id=…)` referenced an id that
        does not exist OR is filtered out for the caller.
      * ``not_permitted`` — the caller's grant does not satisfy all
        `required_permissions`.
      * ``not_available`` — tool is registered but `available=False` right now.
      * ``duplicate_tool`` / ``duplicate_toolkit`` — id already registered.
      * ``invalid_input`` — dispatch inputs failed `input_schema` validation.
    """


@dataclass(frozen=True)
class ToolkitDescriptor:
    """Discovery descriptor for one toolkit (collection of related tools)."""

    id: str
    description: str
    version: str = "1.0"
    # Metadata hint for discovery clients. Not an authorization claim.
    owner: str = "unknown"
    # The number of tools (ALL kinds) registered under this toolkit at
    # discovery time. The caller may hold permissions for only a subset,
    # so this field is intentionally NOT the number of tools the caller
    # can see — that is reported by the discovery call itself.
    registered_tool_count: int = 0
    # Which kinds the toolkit contains. A toolkit may hold a mix.
    kinds: tuple[ToolKind, ...] = ()


@dataclass(frozen=True)
class ToolDescriptor:
    """Discovery descriptor for one registered callable operation."""

    id: str
    toolkit: str
    kind: ToolKind
    description: str
    input_schema: dict[str, Any]
    owner: str
    version: str = "1.0"
    effects: tuple[str, ...] = ("read",)
    available: bool = True
    required_permissions: tuple[str, ...] = ()

    def is_available(self) -> bool:
        return self.available


@dataclass(frozen=True)
class HostCapabilities:
    """Which host-native tools the agent host advertises.

    Reviewer: 'Register apply_patch, shell, and update_plan only when
    supported by the actual host.' update_plan is a FUNCTION tool (not
    host-native) but the host decides whether a progress-tracking UI is
    present, so its availability also comes through here.
    """

    apply_patch: bool = False
    shell: bool = False
    update_plan: bool = False
    # Free-form name list — hosts may advertise additional native tools.
    extensions: tuple[str, ...] = ()


class PermissionGrant(Protocol):
    """How the host maps a Principal to a set of granted permission tokens.

    Vocabulary matches `agent.prompt_authoring.types.ToolPermission` but is
    kept as plain strings here to avoid a cross-import (toolkit discovery
    may be used by code that does not depend on prompt_authoring).

    The default `EmptyGrant` refuses everything, matching the reviewer
    rule that discovery does NOT grant permissions.
    """

    def granted(self, principal_name: str) -> set[str]:
        ...


@dataclass(frozen=True)
class EmptyGrant:
    """The default grant — refuses every permission."""

    def granted(self, principal_name: str) -> set[str]:
        return set()


@dataclass(frozen=True)
class StaticGrant:
    """In-memory grant mapping, useful for tests and small deployments."""

    permissions: dict[str, frozenset[str]] = field(default_factory=dict)

    def granted(self, principal_name: str) -> set[str]:
        return set(self.permissions.get(principal_name, frozenset()))


__all__ = [
    "EmptyGrant",
    "HostCapabilities",
    "PermissionGrant",
    "StaticGrant",
    "ToolDescriptor",
    "ToolKind",
    "ToolRegistryError",
    "ToolkitDescriptor",
]
