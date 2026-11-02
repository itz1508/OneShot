"""Default toolkit + tool registrations.

Three toolkits are seeded by `register_default_toolkits(registry, …)`:

  * ``task_management`` — get_task_status (FUNCTION), update_plan (FUNCTION,
    only when host advertises it), update_task_progress (FUNCTION, backed
    by TaskManager).
  * ``repository`` — list_files (FUNCTION), search_sources (FUNCTION). Both
    reuse the existing `tools.search_sources.SearchSources` primitive.
  * ``workspace`` — read_file (FUNCTION), search_files (FUNCTION),
    apply_patch (HOST_NATIVE), shell (HOST_NATIVE). The latter two are
    registered ONLY when `HostCapabilities.{apply_patch, shell}` is True.

The ``mcp`` toolkit is created empty — MCP connectors register their
discovered tools against it at runtime. Hard-coding MCP tool identities
here would conflate protocol discovery with the OneShot catalog, which
the reviewer explicitly forbids.

Ownership-boundary notes (preserved):

  * ``update_plan`` is a lightweight progress-tracking Function Tool. It
    MUST NOT duplicate TaskManager state. The implementation here appends
    an advisory entry to a per-task plan buffer and never writes to the
    TaskManager snapshot. ``update_task_progress`` is the only Function
    Tool in this file that mutates TaskManager state.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from agent.tools_registry.types import (
    HostCapabilities,
    ToolDescriptor,
    ToolKind,
    ToolkitDescriptor,
)

# ---------------------------------------------------------------------------
# Toolkit descriptors (seeds — tool count is bumped by the registry)
# ---------------------------------------------------------------------------

TOOLKIT_TASK_MANAGEMENT = ToolkitDescriptor(
    id="task_management",
    description="Task state, TODO coordination, progress tracking.",
    owner="tools/task_management.py",
)
TOOLKIT_REPOSITORY = ToolkitDescriptor(
    id="repository",
    description="Repository inspection — list files, search sources.",
    owner="tools/search_sources.py",
)
TOOLKIT_WORKSPACE = ToolkitDescriptor(
    id="workspace",
    description="Local workspace: read files, search, apply patches, shell.",
    owner="agent/tools_registry/defaults.py",
)
TOOLKIT_MCP = ToolkitDescriptor(
    id="mcp",
    description="Tools discovered through registered MCP connectors.",
    owner="(mcp connectors)",
)


# ---------------------------------------------------------------------------
# Function Tool implementations
# ---------------------------------------------------------------------------


def _impl_get_task_status(task_manager: Any):
    def fn(inputs: dict[str, Any]) -> dict[str, Any]:
        task_id = inputs["task_id"]
        task = task_manager.get_task(task_id)
        if task is None:
            return {"found": False, "task_id": task_id}
        return {
            "found": True,
            "task_id": task_id,
            "state": task.state.value if hasattr(task.state, "value") else str(task.state),
            "metadata_revision": int((task.metadata or {}).get("revision", 1)),
            "stage": (task.metadata or {}).get("stage"),
        }

    return fn


def _impl_update_task_progress(task_manager: Any):
    """The ONLY default Function Tool that mutates TaskManager state."""
    import time

    def fn(inputs: dict[str, Any]) -> dict[str, Any]:
        task_id = inputs["task_id"]
        progress_note = inputs["progress_note"]
        task = task_manager.get_task(task_id)
        if task is None:
            raise KeyError(f"task {task_id!r} not found")
        current_revision = int((task.metadata or {}).get("revision", 1))
        updated = dict(task.metadata or {})
        trail = list(updated.get("progress_trail") or [])
        trail.append({
            "at": time.time(),
            "note": progress_note,
            "evidence_ref": inputs.get("evidence_ref"),
        })
        updated["progress_trail"] = trail
        updated["revision"] = current_revision + 1
        # CAS write — fail if a stale caller tries to overwrite.
        task_manager.set_task_metadata(
            task_id, updated, if_revision=current_revision
        )
        return {"task_id": task_id, "new_revision": current_revision + 1}

    return fn


# `update_plan` is advisory. It accumulates plan notes in a per-task in-memory
# buffer so we do not duplicate TaskManager state. The host may read this
# buffer out of band (e.g. to render a progress UI); it is NOT a durable
# record. Tests pin this contract explicitly.
_PLAN_BUFFER: dict[str, list[dict[str, Any]]] = {}


def _impl_update_plan():
    import time

    def fn(inputs: dict[str, Any]) -> dict[str, Any]:
        task_id = inputs["task_id"]
        step = inputs["step"]
        _PLAN_BUFFER.setdefault(task_id, []).append({
            "at": time.time(),
            "step": step,
            "note": inputs.get("note", ""),
        })
        return {
            "task_id": task_id,
            "plan_entries": len(_PLAN_BUFFER[task_id]),
            # Advisory marker — this is NOT a persisted receipt.
            "advisory": True,
        }

    return fn


def _impl_list_files(root: str):
    def fn(inputs: dict[str, Any]) -> dict[str, Any]:
        try:
            from search_sources import SearchSources  # type: ignore
        except Exception as exc:
            raise RuntimeError(f"SearchSources import failed: {exc}") from exc
        ss = SearchSources(root)
        return {"files": list(ss.list_files()), "root": root}

    return fn


def _impl_search_sources(root: str):
    def fn(inputs: dict[str, Any]) -> dict[str, Any]:
        from search_sources import SearchSources  # type: ignore
        pattern = inputs["pattern"]
        extensions = inputs.get("extensions")
        ss = SearchSources(root)
        results = list(ss.find(pattern, extensions=extensions)) if extensions else list(
            ss.find(pattern)
        )
        return {"pattern": pattern, "matches": results}

    return fn


def _impl_read_file(root: str):
    def fn(inputs: dict[str, Any]) -> dict[str, Any]:
        path = inputs["path"]
        candidate = (Path(root) / path).resolve()
        base = Path(root).resolve()
        if not str(candidate).startswith(str(base) + "/") and candidate != base:
            raise PermissionError(
                f"read_file: path {path!r} escapes workspace root"
            )
        if not candidate.is_file():
            return {"path": path, "found": False}
        return {"path": path, "found": True, "content": candidate.read_text(encoding="utf-8")}

    return fn


def _impl_search_files(root: str):
    def fn(inputs: dict[str, Any]) -> dict[str, Any]:
        import re
        pattern = re.compile(inputs["pattern"])
        base = Path(root).resolve()
        hits: list[dict[str, Any]] = []
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    hits.append({"path": str(path.relative_to(base)), "line": line_no})
                    if len(hits) >= inputs.get("limit", 100):
                        return {"matches": hits, "truncated": True}
        return {"matches": hits, "truncated": False}

    return fn


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def register_default_toolkits(
    registry,
    *,
    host: HostCapabilities,
    task_manager: Any,
    repo_root: str | None = None,
) -> None:
    """Seed `registry` with the default four toolkits.

    * host — governs which host-native tools are advertised.
    * task_manager — the OneShot TaskManager instance to back
      `update_task_progress` and `get_task_status`.
    * repo_root — workspace root; `None` means the repository tools are
      registered but with a no-op root that only works for `read_file`
      on absolute paths.
    """
    for tk in (
        TOOLKIT_TASK_MANAGEMENT,
        TOOLKIT_REPOSITORY,
        TOOLKIT_WORKSPACE,
        TOOLKIT_MCP,
    ):
        registry.register_toolkit(tk)

    # ------- task_management toolkit -------

    registry.register_function_tool(
        ToolDescriptor(
            id="get_task_status",
            toolkit="task_management",
            kind=ToolKind.FUNCTION,
            description="Return the current state + stage + revision of a task.",
            input_schema={
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
            owner="tools/task_management.py",
            effects=("read",),
            required_permissions=("read_only",),
        ),
        _impl_get_task_status(task_manager),
    )

    registry.register_function_tool(
        ToolDescriptor(
            id="update_task_progress",
            toolkit="task_management",
            kind=ToolKind.FUNCTION,
            description=(
                "Append a durable progress note to TaskManager via CAS write. "
                "The ONLY default Function Tool that mutates TaskManager state."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "progress_note": {"type": "string"},
                    "evidence_ref": {"type": "string"},
                },
                "required": ["task_id", "progress_note"],
            },
            owner="tools/task_management.py",
            effects=("internal_write",),
            required_permissions=("read_only",),
        ),
        _impl_update_task_progress(task_manager),
    )

    if host.update_plan:
        registry.register_function_tool(
            ToolDescriptor(
                id="update_plan",
                toolkit="task_management",
                kind=ToolKind.FUNCTION,
                description=(
                    "Advisory progress-tracking note. In-memory only; does NOT "
                    "write to TaskManager — see update_task_progress for durable "
                    "progress."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "task_id": {"type": "string"},
                        "step": {"type": "string"},
                        "note": {"type": "string"},
                    },
                    "required": ["task_id", "step"],
                },
                owner="agent/tools_registry/defaults.py",
                effects=("read",),
                required_permissions=("read_only",),
            ),
            _impl_update_plan(),
        )

    # ------- repository toolkit -------

    if repo_root:
        registry.register_function_tool(
            ToolDescriptor(
                id="list_files",
                toolkit="repository",
                kind=ToolKind.FUNCTION,
                description="List repository files via SearchSources.",
                input_schema={"type": "object", "properties": {}},
                owner="tools/search_sources.py",
                effects=("read",),
                required_permissions=("repository_read",),
            ),
            _impl_list_files(repo_root),
        )
        registry.register_function_tool(
            ToolDescriptor(
                id="search_sources",
                toolkit="repository",
                kind=ToolKind.FUNCTION,
                description="Search repository sources for a pattern.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "extensions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["pattern"],
                },
                owner="tools/search_sources.py",
                effects=("read",),
                required_permissions=("code_search",),
            ),
            _impl_search_sources(repo_root),
        )

    # ------- workspace toolkit -------

    if repo_root:
        registry.register_function_tool(
            ToolDescriptor(
                id="read_file",
                toolkit="workspace",
                kind=ToolKind.FUNCTION,
                description="Read a single file inside the workspace root.",
                input_schema={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
                owner="agent/tools_registry/defaults.py",
                effects=("read",),
                required_permissions=("read_only",),
            ),
            _impl_read_file(repo_root),
        )
        registry.register_function_tool(
            ToolDescriptor(
                id="search_files",
                toolkit="workspace",
                kind=ToolKind.FUNCTION,
                description="Regex-search workspace files line by line.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["pattern"],
                },
                owner="agent/tools_registry/defaults.py",
                effects=("read",),
                required_permissions=("read_only", "code_search"),
            ),
            _impl_search_files(repo_root),
        )
    if host.apply_patch:
        registry.register_host_native_tool(
            ToolDescriptor(
                id="apply_patch",
                toolkit="workspace",
                kind=ToolKind.HOST_NATIVE,
                description="Apply a unified diff via the host's native patch tool.",
                input_schema={
                    "type": "object",
                    "properties": {"diff": {"type": "string"}},
                    "required": ["diff"],
                },
                owner="(host)",
                effects=("internal_write",),
                required_permissions=("filesystem_write",),
            ),
        )
    if host.shell:
        registry.register_host_native_tool(
            ToolDescriptor(
                id="shell",
                toolkit="workspace",
                kind=ToolKind.HOST_NATIVE,
                description="Execute a shell command via the host's native terminal.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "cwd": {"type": "string"},
                    },
                    "required": ["command"],
                },
                owner="(host)",
                effects=("external_write",),
                required_permissions=("filesystem_write", "network"),
            ),
        )

    # The `mcp` toolkit is deliberately registered empty. MCP connectors
    # populate it dynamically via `registry.register_mcp_tool(...)`.


__all__ = [
    "TOOLKIT_MCP",
    "TOOLKIT_REPOSITORY",
    "TOOLKIT_TASK_MANAGEMENT",
    "TOOLKIT_WORKSPACE",
    "register_default_toolkits",
]
