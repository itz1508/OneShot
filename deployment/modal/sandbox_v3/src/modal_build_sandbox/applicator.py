"""Preflight-only trusted text patch interpreter; never execute candidate instructions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .policy import normalize_path
from .snapshot import secure_read, secure_remove, secure_write

HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


@dataclass(frozen=True)
class FilePatch:
    path: str
    old_null: bool
    new_null: bool
    hunks: tuple[tuple[int, int, int, int, tuple[str, ...]], ...]


def parse_patch(payload: bytes) -> tuple[FilePatch, ...]:
    try:
        lines = payload.decode("utf-8").splitlines(keepends=True)
    except UnicodeDecodeError as exc:
        raise ValueError("binary patch not supported by patch-first mode") from exc
    result: list[FilePatch] = []
    i = 0
    while i < len(lines):
        match = re.fullmatch(r"diff --git a/(\S+) b/(\S+)\n", lines[i])
        if not match or match.group(1) != match.group(2):
            raise ValueError("patch must contain canonical same-path git diff headers")
        path = normalize_path(match.group(1))
        i += 1
        while i < len(lines) and not lines[i].startswith("--- "):
            if not (
                lines[i].startswith("index ")
                or lines[i].startswith("new file mode 100")
                or lines[i].startswith("deleted file mode 100")
            ):
                raise ValueError("unsupported patch metadata (rename/binary/mode)")
            if lines[i].startswith(("new file mode", "deleted file mode")) and not lines[i].strip().endswith(
                ("644", "755")
            ):
                raise ValueError("unsupported file permissions")
            i += 1
        if i + 1 >= len(lines) or not lines[i].startswith("--- ") or not lines[i + 1].startswith("+++ "):
            raise ValueError("missing patch file markers")
        old = lines[i][4:].strip()
        new = lines[i + 1][4:].strip()
        if (
            old not in ("/dev/null", f"a/{path}")
            or new not in ("/dev/null", f"b/{path}")
            or (old == new == "/dev/null")
        ):
            raise ValueError("patch path mismatch")
        i += 2
        hunks: list[tuple[int, int, int, int, tuple[str, ...]]] = []
        while i < len(lines) and not lines[i].startswith("diff --git "):
            m = HUNK.match(lines[i])
            if m is None:
                raise ValueError("malformed hunk")
            start_old, count_old = int(m.group(1)), int(m.group(2) or 1)
            start_new, count_new = int(m.group(3)), int(m.group(4) or 1)
            i += 1
            contents: list[str] = []
            while i < len(lines) and not lines[i].startswith(("@@ ", "diff --git ")):
                if not lines[i] or lines[i][0] not in (" ", "+", "-"):
                    raise ValueError("unsupported hunk line")
                contents.append(lines[i])
                i += 1
            if (
                sum(s[0] in (" ", "-") for s in contents) != count_old
                or sum(s[0] in (" ", "+") for s in contents) != count_new
            ):
                raise ValueError("hunk length mismatch")
            hunks.append((start_old, count_old, start_new, count_new, tuple(contents)))
        if not hunks:
            raise ValueError("patch must contain hunks")
        result.append(FilePatch(path, old == "/dev/null", new == "/dev/null", tuple(hunks)))
    if not result or len({p.path.casefold() for p in result}) != len(result):
        raise ValueError("empty or duplicate patch targets")
    return tuple(result)


def prepare_changes(
    root: Path, patch: bytes, allowed: tuple[str, ...], expected_preimages: dict[str, str | None]
) -> dict[str, bytes | None]:
    result: dict[str, bytes | None] = {}
    for file_patch in parse_patch(patch):
        path = file_patch.path
        if path not in allowed or path not in expected_preimages:
            raise ValueError("unauthorized patch path")
        try:
            original = secure_read(root, path)
        except FileNotFoundError:
            original = None
        expected = expected_preimages[path]
        if (original is None) != (expected is None) or (
            original is not None and hashlib.sha256(original).hexdigest() != expected
        ):
            raise ValueError("source preimage mismatch")
        if file_patch.old_null != (original is None) or file_patch.new_null and file_patch.old_null:
            raise ValueError("patch operation/preimage mismatch")
        text_lines = original.decode("utf-8").splitlines(keepends=True) if original is not None else []
        output: list[str] = []
        cursor = 0
        for old_start, old_count, _new_start, _new_count, hunk in file_patch.hunks:
            start = old_start - 1 if old_count else old_start
            if start < cursor or start > len(text_lines):
                raise ValueError("overlapping or invalid hunk position")
            output.extend(text_lines[cursor:start])
            pos = start
            for line in hunk:
                if line[0] in (" ", "-"):
                    if pos >= len(text_lines) or text_lines[pos] != line[1:]:
                        raise ValueError("hunk content does not match preimage")
                    pos += 1
                if line[0] in (" ", "+"):
                    output.append(line[1:])
            cursor = pos
        output.extend(text_lines[cursor:])
        new_data = "".join(output).encode("utf-8")
        result[path] = None if file_patch.new_null else new_data
    return result


def apply_changes(root: Path, changes: dict[str, bytes | None]) -> None:
    # All changes must be validated before this function is called.
    for path, new in changes.items():
        if new is None:
            secure_remove(root, path)
        else:
            secure_write(root, path, new)
