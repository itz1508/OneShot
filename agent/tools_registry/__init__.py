"""OneShot Tool Registry — discovery for Function, Host-native, and MCP tools.

Reviewer scope (R3 addon):
  * Toolkit = collection of related tools; Tool = one registered callable
    operation. Neither is a workflow stage.
  * `list_toolkits()` and `list_tools(toolkit_id=None)` are the discovery
    contracts. They return only tools actually available and permitted for
    the authenticated caller. Discovery NEVER executes tools, grants
    permissions, or authorizes Build actions.
  * Function Tools, Host-native tools, and MCP Tools stay distinctly typed
    via `ToolKind`.
  * Reuse the existing `CapabilityRegistry` for version/effect metadata and
    reuse `agent.prompt_authoring.store.Principal` for identity. This
    package is NOT a competing tool-management subsystem.
"""

from agent.tools_registry.registry import ToolRegistry
from agent.tools_registry.types import (
    DispatchAuditEntry,
    HostCapabilities,
    PermissionGrant,
    ToolDescriptor,
    ToolKind,
    ToolkitDescriptor,
    ToolRegistryError,
)

__all__ = [
    "DispatchAuditEntry",
    "HostCapabilities",
    "PermissionGrant",
    "ToolDescriptor",
    "ToolKind",
    "ToolRegistryError",
    "ToolRegistry",
    "ToolkitDescriptor",
]
