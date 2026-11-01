"""Scanner pattern discovery and guarded filesystem edits.

Discovery and change preparation are read-only. `scan_edit_write` is a separate,
explicitly authorized effect boundary and must never be called by Audit Discovery.
Existing Task Management / Build Admission remain the authorization owners.
"""

from __future__ import annotations

import difflib
import hashlib
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class ScanError(ValueError):
    """Rejected scanner input, unsafe path, ambiguous edit, or stale write."""


def _root(repo_root: str | Path) -> Path:
    root = Path(repo_root).resolve(strict=True)
    if not root.is_dir():
        raise ScanError("repository root is not a directory")
    return root


def _path(root: Path, relative: str) -> Path:
    if not relative or Path(relative).is_absolute() or "\\" in relative:
        raise ScanError(f"unsafe relative path: {relative!r}")
    parts = Path(relative).parts
    if not parts or any(part in (".", "..") for part in parts):
        raise ScanError(f"unsafe relative path: {relative!r}")
    path = root.joinpath(*parts)
    if not path.resolve().is_relative_to(root):
        raise ScanError(f"path escapes root: {relative!r}")
    for ancestor in (path, *path.parents):
        if ancestor == root:
            break
        if ancestor.is_symlink():
            raise ScanError(f"symlink is not an editable source: {relative!r}")
    if not path.is_file():
        raise ScanError(f"source is not a regular file: {relative!r}")
    return path


def _tracked(root: Path, *, include_untracked: bool = False) -> list[str]:
    command = ["git", "-C", str(root), "ls-files", "-z", "--cached"]
    if include_untracked:
        command.extend(["--others", "--exclude-standard"])
    result = subprocess.run(command, capture_output=True, check=False, timeout=30)
    if result.returncode:
        raise ScanError("git ls-files failed: " + result.stderr.decode("utf-8", "replace"))
    return sorted(set(v.decode("utf-8") for v in result.stdout.split(b"\0") if v))


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def scan_filesystems(repo_root: str | Path, *, include_untracked: bool = False) -> dict[str, Any]:
    """Inventory Git-visible files without reading through symlinks or writing."""
    root = _root(repo_root)
    files = []
    for relative in _tracked(root, include_untracked=include_untracked):
        try:
            path = _path(root, relative)
        except ScanError as exc:
            files.append({"path": relative, "status": "unavailable", "reason": str(exc)})
            continue
        raw = path.read_bytes()
        files.append({"path": relative, "status": "file", "sha256": _digest(raw), "size": len(raw)})
    return {"files": files, "count": len(files)}


def _rules(rules: list[dict[str, Any]]) -> list[tuple[str, re.Pattern[str], str]]:
    if not isinstance(rules, list) or not rules:
        raise ScanError("nonempty replacement rules are required")
    compiled = []
    for rule in rules:
        name = rule.get("name")
        expression = rule.get("pattern")
        replacement = rule.get("replacement")
        if not all(isinstance(x, str) and x for x in (name, expression)) or not isinstance(
            replacement, str
        ):
            raise ScanError("each rule needs nonempty name/pattern and string replacement")
        try:
            pattern = re.compile(expression if rule.get("regex") else re.escape(expression))
        except re.error as exc:
            raise ScanError(f"invalid pattern {name}: {exc}") from exc
        if pattern.match(""):
            raise ScanError(f"zero-width pattern is forbidden: {name}")
        compiled.append((name, pattern, replacement))
    return compiled


def _selected(root: Path, paths: list[str] | None, include_untracked: bool) -> list[str]:
    discovered = set(_tracked(root, include_untracked=include_untracked))
    if paths is None:
        return sorted(discovered)
    if not isinstance(paths, list) or not paths:
        raise ScanError("paths must be a nonempty list when supplied")
    selected = set(paths)
    if not selected.issubset(discovered):
        raise ScanError("requested path is not tracked or permitted")
    return sorted(selected)


def _matches(text: str, rules: list[tuple[str, re.Pattern[str], str]]) -> list[dict[str, Any]]:
    hits = []
    for name, pattern, replacement in rules:
        for match in pattern.finditer(text):
            start, end = match.span()
            value = match.expand(replacement)
            hits.append({
                "name": name, "start": start, "end": end, "matched": match.group(),
                "replacement": value,
                "line": text.count("\n", 0, start) + 1,
                "column": start - (text.rfind("\n", 0, start) + 1) + 1,
            })
    hits.sort(key=lambda h: (h["start"], h["end"], h["name"]))
    for previous, current in zip(hits, hits[1:]):
        if current["start"] < previous["end"]:
            raise ScanError(f"overlapping replacements: {previous['name']} / {current['name']}")
    return hits


def scan_match_variable(
    repo_root: str | Path,
    rules: list[dict[str, Any]],
    *,
    paths: list[str] | None = None,
    include_untracked: bool = False,
) -> dict[str, Any]:
    """Extract matched names, pattern locations, and proposed replacements."""
    root = _root(repo_root)
    compiled = _rules(rules)
    all_matches = []
    skipped = []
    for relative in _selected(root, paths, include_untracked):
        try:
            raw = _path(root, relative).read_bytes()
            text = raw.decode("utf-8")
        except (UnicodeError, ScanError) as exc:
            skipped.append({"path": relative, "reason": str(exc)})
            continue
        for match in _matches(text, compiled):
            all_matches.append({"path": relative, **match})
    return {"matches": all_matches, "count": len(all_matches), "skipped": skipped}


def scan_edit_change(
    repo_root: str | Path,
    rules: list[dict[str, Any]],
    *,
    paths: list[str] | None = None,
    include_untracked: bool = False,
) -> dict[str, Any]:
    """Preview replacements, recording before/after SHA-256; never writes."""
    root = _root(repo_root)
    compiled = _rules(rules)
    changes = []
    skipped = []
    for relative in _selected(root, paths, include_untracked):
        try:
            raw = _path(root, relative).read_bytes()
            text = raw.decode("utf-8")
        except (UnicodeError, ScanError) as exc:
            skipped.append({"path": relative, "reason": str(exc)})
            continue
        hits = _matches(text, compiled)
        if not hits:
            continue
        updated = text
        for hit in reversed(hits):
            updated = updated[: hit["start"]] + hit["replacement"] + updated[hit["end"] :]
        before_lines = text.splitlines(keepends=True)
        after_lines = updated.splitlines(keepends=True)
        diff = "".join(
            difflib.unified_diff(before_lines, after_lines, fromfile=relative, tofile=relative)
        )
        after = updated.encode("utf-8")
        changes.append({
            "path": relative, "before_sha256": _digest(raw), "after_sha256": _digest(after),
            "after_content": updated, "matches": hits, "diff": diff,
        })
    return {"changes": changes, "count": len(changes), "skipped": skipped}


def scan_edit_write(
    repo_root: str | Path,
    changes: list[dict[str, Any]],
    *,
    allowed_paths: list[str],
    authorized: bool = False,
) -> dict[str, Any]:
    """Explicit, bounded write boundary. Audit Discovery MUST NOT call this.

    Validates every tracked, allowlisted path and both digests before writing.
    Each write is atomic; a failure raises with the prior written paths in the
    message, so the caller can reconcile partial completion before retrying.
    """
    if not authorized:
        raise ScanError("scan_edit_write requires explicit Build authorization")
    root = _root(repo_root)
    if not isinstance(allowed_paths, list) or not allowed_paths:
        raise ScanError("explicit allowed_paths are required")
    allowed = set(allowed_paths)
    tracked = set(_tracked(root))
    if not isinstance(changes, list) or not changes:
        raise ScanError("nonempty changes are required")
    if len({x.get("path") for x in changes}) != len(changes):
        raise ScanError("duplicate write paths")
    prepared = []
    for change in changes:
        relative = change.get("path")
        if not isinstance(relative, str) or relative not in allowed or relative not in tracked:
            raise ScanError(f"write path not approved: {relative!r}")
        path = _path(root, relative)
        before = path.read_bytes()
        after_text = change.get("after_content")
        if not isinstance(after_text, str):
            raise ScanError("after_content must be UTF-8 text")
        after = after_text.encode("utf-8")
        if _digest(before) != change.get("before_sha256"):
            raise ScanError(f"stale source: {relative}")
        if _digest(after) != change.get("after_sha256"):
            raise ScanError(f"invalid proposed content digest: {relative}")
        prepared.append((relative, path, after, stat.S_IMODE(path.stat().st_mode)))
    completed = []
    for relative, path, after, mode in prepared:
        tmp_name = None
        try:
            expected = next(c["before_sha256"] for c in changes if c["path"] == relative)
            if _digest(_path(root, relative).read_bytes()) != expected:
                raise ScanError(f"stale source before effect: {relative}")
            with tempfile.NamedTemporaryFile(
                dir=path.parent, prefix=".scanner-", delete=False
            ) as f:
                tmp_name = f.name
                f.write(after)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp_name, mode)
            os.replace(tmp_name, path)
            completed.append({"path": relative, "sha256": _digest(after)})
        except (OSError, ScanError) as exc:
            raise ScanError(f"write stopped at {relative}; completed={completed!r}: {exc}") from exc
        finally:
            if tmp_name and os.path.exists(tmp_name):
                os.unlink(tmp_name)
    return {"written": completed, "count": len(completed)}


__all__ = [
    "ScanError", "scan_match_variable", "scan_edit_change", "scan_edit_write",
    "scan_filesystems",
]
