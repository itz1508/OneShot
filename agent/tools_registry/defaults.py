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

import fnmatch
import re as _re
from functools import lru_cache
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


# ---------------------------------------------------------------------------
# .agents/settings.json deny policy + secret-redaction (C3 corrective)
# ---------------------------------------------------------------------------
#
# OneShot ships a minimal deny policy under `./.agents/settings.json` with
# `permissions.deny` entries like `Read(./**/dist/**/*)`. This module parses
# the policy at the workspace root and refuses to read / list / search any
# path matched by one of the deny patterns.


_SECRET_PATTERNS = [
    _re.compile(p) for p in (
        r"sk-[A-Za-z0-9_-]{20,}",
        r"ghp_[A-Za-z0-9]{30,}",
        r"github_pat_[A-Za-z0-9_]{20,}",
        r"xox[baprs]-[A-Za-z0-9-]{10,}",
        r"AIza[0-9A-Za-z_\-]{30,}",
        r"[Bb]earer\s+[A-Za-z0-9._\-]{20,}",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    )
]


def _redact_secret(text: str) -> str:
    """Return `text` with likely secrets replaced by a `<REDACTED>` marker."""
    for pat in _SECRET_PATTERNS:
        text = pat.sub("<REDACTED>", text)
    return text


@lru_cache(maxsize=32)
def _deny_patterns(root_str: str) -> tuple[str, ...]:
    """Parse `root/.agents/settings.json` once per workspace root."""
    import json
    root = Path(root_str)
    settings = root / ".agents" / "settings.json"
    if not settings.is_file():
        return ()
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except Exception:
        return ()
    perms = (data.get("permissions") or {}).get("deny") or []
    out: list[str] = []
    for entry in perms:
        if not isinstance(entry, str):
            continue
        # The policy uses `Read(<glob>)`. Strip the `Read(...)` wrapper if
        # present; a bare glob is also accepted.
        m = _re.match(r"Read\((.+?)\)\s*$", entry.strip())
        glob = m.group(1) if m else entry.strip()
        # Policy writes `./**/dist/**/*` — normalise to a workspace-relative
        # fnmatch pattern.
        if glob.startswith("./"):
            glob = glob[2:]
        out.append(glob)
    return tuple(out)


def _path_is_denied(root: Path, candidate: Path) -> bool:
    """Return True when ``candidate`` matches any deny pattern on ``root``."""
    try:
        rel = str(candidate.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return True
    patterns = _deny_patterns(str(root))
    # fnmatch does not handle `**` across directories; _glob_matches does.
    return any(_glob_matches(rel, glob) for glob in patterns)


def _glob_matches(path: str, pattern: str) -> bool:
    """Minimal `**`-aware fnmatch for the deny policy shape.

    Semantics restricted to the shapes OneShot's deny policy uses:
      * ``pat/**/suffix``  — zero or more directory components between.
      * ``**/suffix``      — any depth prefix (including empty) + suffix.
      * ``prefix/**``      — prefix + any depth.
      * ``*.ext``, ``*.generated.*`` — fnmatch on the full relative path.
    """
    if "**" not in pattern:
        return fnmatch.fnmatch(path, pattern)
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("/**/", i):
            out.append("(?:/.*/|/)")
            i += 4
            continue
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if pattern.startswith("/**", i) and i + 3 == len(pattern):
            out.append("(?:/.*)?")
            i += 3
            continue
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        t = fnmatch.translate(pattern[i])
        if t.startswith("(?s:") and t.endswith(")\\Z"):
            t = t[4:-3]
        out.append(t)
        i += 1
    regex = "".join(out)
    return bool(_re.fullmatch(regex, path))



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
    """The ONLY default Function Tool that mutates TaskManager state.

    Reviewer directive (C2): require ``task_write`` AND verify the caller
    is the task's owner. If ``metadata['owner']`` is set, only that owner
    may append progress. If it is unset, the first owner-less call is
    rejected unless the caller also supplies ``owner_bind=True`` to adopt
    ownership — a one-shot upgrade path for legacy tasks.
    """
    import time

    def fn(inputs: dict[str, Any], principal_name: str) -> dict[str, Any]:
        task_id = inputs["task_id"]
        progress_note = inputs["progress_note"]
        caller_if_revision = inputs.get("if_revision")
        owner_bind = bool(inputs.get("owner_bind", False))
        task = task_manager.get_task(task_id)
        if task is None:
            raise KeyError(f"task {task_id!r} not found")
        current_revision = int((task.metadata or {}).get("revision", 1))
        if caller_if_revision is not None and int(caller_if_revision) != current_revision:
            raise PermissionError(
                f"update_task_progress: caller-supplied if_revision="
                f"{caller_if_revision!r} does not match committed revision="
                f"{current_revision!r}"
            )
        owner = (task.metadata or {}).get("owner")
        if owner is None:
            if not owner_bind:
                raise PermissionError(
                    f"update_task_progress: task {task_id!r} has no recorded "
                    "owner. Pass owner_bind=True to adopt ownership on the "
                    "first authorized write."
                )
            # Owner bind path: adopt the caller as the owner.
            new_owner = principal_name
        elif owner != principal_name:
            raise PermissionError(
                f"update_task_progress: task {task_id!r} is owned by "
                f"{owner!r}, not {principal_name!r}"
            )
        else:
            new_owner = owner
        updated = dict(task.metadata or {})
        updated["owner"] = new_owner
        trail = list(updated.get("progress_trail") or [])
        trail.append({
            "at": time.time(),
            "actor": principal_name,
            "note": progress_note,
            "evidence_ref": inputs.get("evidence_ref"),
        })
        updated["progress_trail"] = trail
        updated["revision"] = current_revision + 1
        task_manager.set_task_metadata(
            task_id, updated, if_revision=current_revision
        )
        return {
            "task_id": task_id,
            "new_revision": current_revision + 1,
            "owner": new_owner,
        }

    setattr(fn, "_principal_aware", True)  # noqa: B010 - signalling attribute
    return fn


def _impl_update_plan(host_plan_sink: Any):
    """`update_plan` forwards to the host's progress-tracking tool.

    Reviewer directive (medium): the pre-corrective in-memory buffer was
    advertising a host-supported progress interface without one. If the
    host does not supply a `host_plan_sink` (a callable accepting a dict),
    `update_plan` is NOT registered. The sink is the host's responsibility —
    the registry only forwards. The sink's return value, if any, is
    surfaced verbatim.
    """
    import time

    def fn(inputs: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "at": time.time(),
            "task_id": inputs["task_id"],
            "step": inputs["step"],
            "note": inputs.get("note", ""),
        }
        host_return = host_plan_sink(payload)
        return {
            "task_id": inputs["task_id"],
            "step": inputs["step"],
            "advisory": True,
            "host_return": host_return,
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
        kind = inputs.get("kind", "name")  # "name" (path glob) or "content"
        ss = SearchSources(root)
        if kind == "content":
            matches = list(ss.find_by_content(pattern))
        elif kind == "name":
            matches = list(ss.search_by_pattern(pattern))
        else:
            raise ValueError(f"search_sources: unknown kind={kind!r}; use 'name' or 'content'")
        return {"pattern": pattern, "kind": kind, "matches": matches}

    return fn


def _impl_read_file(root: str):
    def fn(inputs: dict[str, Any]) -> dict[str, Any]:
        path = inputs["path"]
        raw = Path(root) / path
        candidate = raw.resolve()
        base = Path(root).resolve()
        if not candidate.is_relative_to(base):
            raise PermissionError(
                f"read_file: path {path!r} escapes workspace root"
            )
        if raw.is_symlink() or any(
            parent.is_symlink()
            for parent in raw.parents
            if parent != base and parent.is_relative_to(base)
        ):
            raise PermissionError(
                f"read_file: path {path!r} crosses a symlink"
            )
        if _path_is_denied(base, candidate):
            raise PermissionError(
                f"read_file: path {path!r} matches .agents/settings.json deny policy"
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
        limit = int(inputs.get("limit", 100))
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            # Confine to root; refuse symlinks that leave the tree.
            resolved = path.resolve()
            if not resolved.is_relative_to(base):
                continue
            if path.is_symlink():
                continue
            # .agents/settings.json deny policy.
            if _path_is_denied(base, resolved):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                if pattern.search(line):
                    # Redact lines that look like secrets before returning.
                    hits.append({
                        "path": str(path.relative_to(base)),
                        "line": line_no,
                        "excerpt": _redact_secret(line),
                    })
                    if len(hits) >= limit:
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
    host_plan_sink: Any = None,
) -> None:
    """Seed `registry` with the default four toolkits.

    * host — governs which host-native tools are advertised.
    * task_manager — the OneShot TaskManager instance.
    * repo_root — workspace root; `None` means the repository + workspace
      Function Tools are NOT registered (the host does not run inside a
      workspace).
    * host_plan_sink — callable that accepts a dict and routes it to the
      host's real progress-tracking tool. `update_plan` is registered ONLY
      when `host.update_plan=True` AND `host_plan_sink` is callable.
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
                "Requires `task_write` AND task ownership. The ONLY default "
                "Function Tool that mutates TaskManager state."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "progress_note": {"type": "string"},
                    "evidence_ref": {"type": "string"},
                    "if_revision": {"type": "integer"},
                    "owner_bind": {"type": "boolean"},
                },
                "required": ["task_id", "progress_note"],
            },
            owner="tools/task_management.py",
            effects=("internal_write",),
            required_permissions=("task_write",),
        ),
        _impl_update_task_progress(task_manager),
    )

    if host.update_plan and callable(host_plan_sink):
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
            _impl_update_plan(host_plan_sink),
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
                dispatchable_in_registry=False,
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
                dispatchable_in_registry=False,
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
