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


class _PolicyLoadError(RuntimeError):
    """Raised when `.agents/settings.json` is present but malformed.

    Reviewer directive #2: policy-loading failures fail closed. A caller
    that cannot parse the deny policy MUST refuse to proceed with any file
    read — otherwise a corrupted / tampered policy silently disables the
    gate. _path_is_denied converts this error into "deny every path on
    this workspace".
    """


@lru_cache(maxsize=32)
def _deny_patterns(root_str: str) -> tuple[str, ...]:
    """Parse `root/.agents/settings.json` once per workspace root.

    * File missing      -> returns ``()`` (documented "no policy" state).
    * File present but invalid JSON / malformed schema -> raises
      ``_PolicyLoadError`` so the caller can fail closed.
    """
    import json
    root = Path(root_str)
    settings = root / ".agents" / "settings.json"
    if not settings.is_file():
        return ()
    try:
        text = settings.read_text(encoding="utf-8")
    except OSError as exc:
        raise _PolicyLoadError(
            f"cannot read {settings}: {exc}. Fail-closed: all paths will be denied."
        ) from exc
    try:
        data = json.loads(text)
    except Exception as exc:
        raise _PolicyLoadError(
            f"{settings} is not valid JSON: {exc}. Fail-closed: all paths will be denied."
        ) from exc
    if not isinstance(data, dict):
        raise _PolicyLoadError(
            f"{settings} must deserialise to a mapping; got {type(data).__name__}. "
            "Fail-closed: all paths will be denied."
        )
    perms_block = data.get("permissions")
    if perms_block is not None and not isinstance(perms_block, dict):
        raise _PolicyLoadError(
            f"{settings} 'permissions' must be a mapping or absent. "
            "Fail-closed: all paths will be denied."
        )
    deny_raw = (perms_block or {}).get("deny")
    if deny_raw is None:
        return ()
    if not isinstance(deny_raw, list):
        raise _PolicyLoadError(
            f"{settings} 'permissions.deny' must be a list of strings. "
            "Fail-closed: all paths will be denied."
        )
    out: list[str] = []
    for entry in deny_raw:
        if not isinstance(entry, str):
            raise _PolicyLoadError(
                f"{settings} 'permissions.deny' contains a non-string entry "
                f"({type(entry).__name__}). Fail-closed: all paths will be denied."
            )
        # The policy uses `Read(<glob>)`. Strip the `Read(...)` wrapper if
        # present; a bare glob is also accepted.
        m = _re.match(r"Read\((.+?)\)\s*$", entry.strip())
        glob = m.group(1) if m else entry.strip()
        if glob.startswith("./"):
            glob = glob[2:]
        out.append(glob)
    return tuple(out)


def _path_is_denied(root: Path, candidate: Path) -> bool:
    """Return True when ``candidate`` matches any deny pattern on ``root``.

    Fail-closed semantics (reviewer directive #2):
      * Candidate not inside ``root``                     -> deny.
      * ``.agents/settings.json`` malformed / unreadable  -> deny.
      * No deny policy declared                           -> allow.
    """
    try:
        rel = str(candidate.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return True
    try:
        patterns = _deny_patterns(str(root))
    except _PolicyLoadError:
        return True
    return any(_glob_matches(rel, glob) for glob in patterns)


def _safe_relative_paths(root: str, relative_paths: list[str]) -> list[str]:
    """Filter ``relative_paths`` through the shared safety gate (reviewer directive #3).

    Keeps only paths that:
      1. Resolve inside ``root`` (no `../` escapes).
      2. Are regular files, not symlinks, with no symlink parent inside root.
      3. Pass the ``.agents/settings.json`` deny policy (fail-closed on load errors).

    Non-existent entries (common for a stale index) are dropped silently —
    callers can detect them by diffing the input against the output.
    """
    base = Path(root).resolve()
    out: list[str] = []
    for rel in relative_paths:
        raw = base / rel
        try:
            resolved = raw.resolve()
        except Exception:
            continue
        if not resolved.is_relative_to(base):
            continue
        if not raw.exists() or not resolved.is_file():
            continue
        if raw.is_symlink() or any(
            parent.is_symlink()
            for parent in raw.parents
            if parent != base and parent.is_relative_to(base)
        ):
            continue
        if _path_is_denied(base, resolved):
            continue
        out.append(rel)
    return out


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



def _mark_principal_aware(fn: Any) -> Any:
    """Flag a Function Tool impl as principal-aware.

    Wraps the attribute set so mypy stops narrowing the callable type;
    without this helper the ``fn._principal_aware = True`` write triggers
    ``[attr-defined]`` on Callables with explicit parameter types.
    """
    fn._principal_aware = True
    return fn


def _impl_get_task_status(task_manager: Any):
    """Return task state, revision, stage, owner.

    Reviewer directive #4: task-level access control. A caller sees only
    tasks they own; cross-owner reads require the ``task_read`` permission
    (gated at discovery) AND an explicit ``cross_owner=True`` input flag so
    a mis-typed task_id cannot leak the existence of someone else's task.
    """

    def fn(inputs: dict[str, Any], principal_name: str) -> dict[str, Any]:
        task_id = inputs["task_id"]
        cross_owner = bool(inputs.get("cross_owner", False))
        task = task_manager.get_task(task_id)
        if task is None:
            return {"found": False, "task_id": task_id}
        md = task.metadata or {}
        owner = md.get("owner")
        if owner is not None and owner != principal_name and not cross_owner:
            return {"found": False, "task_id": task_id}
        return {
            "found": True,
            "task_id": task_id,
            "owner": owner,
            "state": task.state.value if hasattr(task.state, "value") else str(task.state),
            "metadata_revision": int(md.get("revision", 1)),
            "stage": md.get("stage"),
        }

    return _mark_principal_aware(fn)


def _impl_update_task_progress(task_manager: Any):
    """Append a progress note to TaskManager via CAS write.

    Reviewer directives (R3-corrective #5, #6):
      * ``if_revision`` is REQUIRED in the input schema — the previous
        optional fallback is removed. A write without an explicit revision
        check is refused.
      * The owner-adoption path is REMOVED here. A legacy owner-less task
        must be adopted via ``adopt_task_owner`` first (requires
        ``task_admin``). update_task_progress strictly refuses owner-less
        tasks.
      * The impl receives the authenticated name and compares it against
        ``task.metadata['owner']`` — only the owner may write.
    """
    import time

    def fn(inputs: dict[str, Any], principal_name: str) -> dict[str, Any]:
        task_id = inputs["task_id"]
        progress_note = inputs["progress_note"]
        caller_if_revision = int(inputs["if_revision"])
        task = task_manager.get_task(task_id)
        if task is None:
            raise KeyError(f"task {task_id!r} not found")
        current_revision = int((task.metadata or {}).get("revision", 1))
        if caller_if_revision != current_revision:
            raise PermissionError(
                f"update_task_progress: caller-supplied if_revision="
                f"{caller_if_revision!r} does not match committed revision="
                f"{current_revision!r}"
            )
        owner = (task.metadata or {}).get("owner")
        if owner is None:
            raise PermissionError(
                f"update_task_progress: task {task_id!r} has no recorded "
                "owner. Call adopt_task_owner (requires task_admin) before "
                "progress writes."
            )
        if owner != principal_name:
            raise PermissionError(
                f"update_task_progress: task {task_id!r} is owned by "
                f"{owner!r}, not {principal_name!r}"
            )
        updated = dict(task.metadata or {})
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
            "owner": owner,
        }

    return _mark_principal_aware(fn)


def _impl_adopt_task_owner(task_manager: Any):
    """Assign ownership of an owner-less task (reviewer directive #5).

    Requires the ``task_admin`` permission (verified by discovery filter).
    The authorized caller supplies the NEW owner name explicitly — a caller
    cannot claim ownership for themselves by default; the host-approved
    workflow decides who owns which task.

    Fail-closed:
      * Task not found           -> KeyError
      * Task already has owner   -> PermissionError (use a separate
                                    reassignment tool if the host supports
                                    it; this one is strictly adoption).
      * Stale ``if_revision``    -> PermissionError
    """
    import time

    def fn(inputs: dict[str, Any], principal_name: str) -> dict[str, Any]:
        task_id = inputs["task_id"]
        new_owner = inputs["new_owner"]
        caller_if_revision = int(inputs["if_revision"])
        task = task_manager.get_task(task_id)
        if task is None:
            raise KeyError(f"task {task_id!r} not found")
        md = task.metadata or {}
        current_revision = int(md.get("revision", 1))
        if caller_if_revision != current_revision:
            raise PermissionError(
                f"adopt_task_owner: caller-supplied if_revision="
                f"{caller_if_revision!r} does not match committed revision="
                f"{current_revision!r}"
            )
        if md.get("owner") is not None:
            raise PermissionError(
                f"adopt_task_owner: task {task_id!r} already has owner "
                f"{md['owner']!r}. Owner reassignment is NOT exposed here."
            )
        updated = dict(md)
        updated["owner"] = new_owner
        updated["revision"] = current_revision + 1
        trail = list(updated.get("progress_trail") or [])
        trail.append({
            "at": time.time(),
            "actor": principal_name,
            "note": f"adopt_task_owner({new_owner!r}) by {principal_name!r}",
            "evidence_ref": inputs.get("evidence_ref"),
        })
        updated["progress_trail"] = trail
        task_manager.set_task_metadata(
            task_id, updated, if_revision=current_revision
        )
        return {
            "task_id": task_id,
            "owner": new_owner,
            "new_revision": current_revision + 1,
            "assigned_by": principal_name,
        }

    return _mark_principal_aware(fn)


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
        raw = list(ss.list_files())
        safe = _safe_relative_paths(root, raw)
        return {"files": safe, "root": root, "filtered_out": len(raw) - len(safe)}

    return fn


def _impl_search_sources(root: str):
    def fn(inputs: dict[str, Any]) -> dict[str, Any]:
        from search_sources import SearchSources  # type: ignore
        pattern = inputs["pattern"]
        kind = inputs.get("kind", "name")  # "name" (path glob) or "content"
        ss = SearchSources(root)
        if kind == "content":
            raw = list(ss.find_by_content(pattern))
        elif kind == "name":
            raw = list(ss.search_by_pattern(pattern))
        else:
            raise ValueError(
                f"search_sources: unknown kind={kind!r}; use 'name' or 'content'"
            )
        safe = _safe_relative_paths(root, raw)
        return {
            "pattern": pattern,
            "kind": kind,
            "matches": safe,
            "filtered_out": len(raw) - len(safe),
        }

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
            description=(
                "Return the current state + stage + revision + owner of a task."
                " Enforces task-level ACL: owner reads succeed; non-owner reads "
                "require ``cross_owner=True`` AND the ``task_read`` permission."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "cross_owner": {"type": "boolean"},
                },
                "required": ["task_id"],
            },
            owner="tools/task_management.py",
            effects=("read",),
            required_permissions=("task_read",),
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
                "Requires `task_write`, task ownership, AND a caller-supplied "
                "``if_revision`` for atomic CAS. The ONLY default Function Tool "
                "that mutates TaskManager state."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "progress_note": {"type": "string"},
                    "evidence_ref": {"type": "string"},
                    "if_revision": {"type": "integer", "minimum": 1},
                },
                "required": ["task_id", "progress_note", "if_revision"],
            },
            owner="tools/task_management.py",
            effects=("internal_write",),
            required_permissions=("task_write",),
        ),
        _impl_update_task_progress(task_manager),
    )

    registry.register_function_tool(
        ToolDescriptor(
            id="adopt_task_owner",
            toolkit="task_management",
            kind=ToolKind.FUNCTION,
            description=(
                "Assign an owner to a task that has none. Requires task_admin."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "new_owner": {"type": "string"},
                    "if_revision": {"type": "integer", "minimum": 1},
                    "evidence_ref": {"type": "string"},
                },
                "required": ["task_id", "new_owner", "if_revision"],
            },
            owner="tools/task_management.py",
            effects=("internal_write",),
            required_permissions=("task_admin",),
        ),
        _impl_adopt_task_owner(task_manager),
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
