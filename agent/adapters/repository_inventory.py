"""Normalize observations from an existing authorized repository Scanner.

Does not read paths itself or make workflow gap-analysis decisions. The host
supplies the Scanner and remains responsible for safe file access and scope.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class RepositoryInspector(Protocol):
    def __call__(self, root: Path) -> object: ...


@dataclass(frozen=True)
class SourceFile:
    path: str
    byte_count: int
    sha256: str | None
    text_admitted: bool


@dataclass(frozen=True)
class SourceInventory:
    root: str
    files: tuple[SourceFile, ...]
    excluded_paths: tuple[str, ...]
    limitations: tuple[str, ...]
    partial: bool

    @property
    def ready_for_complete_comparison(self) -> bool:
        return not self.partial and all(file.text_admitted for file in self.files)


class SourceInspection:
    """Read-only projection of the *existing* repository Scanner report."""

    def __init__(self, inspector: RepositoryInspector) -> None:
        self._inspector = inspector

    def inspect(self, root: Path) -> SourceInventory:
        requested_root = Path(root)
        report = self._inspector(requested_root)
        files = getattr(report, "files", None)
        limitations = getattr(report, "limitations", None)
        excluded = getattr(report, "excluded_paths", None)
        partial = getattr(report, "partial", None)
        report_root = getattr(report, "root", None)
        if not isinstance(files, (tuple, list)):
            raise TypeError("Scanner report lacks files")
        if not isinstance(limitations, (tuple, list)) or not isinstance(excluded, (tuple, list)):
            raise TypeError("Scanner report lacks exclusions/limitations")
        if type(partial) is not bool or not isinstance(report_root, str) or not report_root:
            raise TypeError("Scanner report lacks root/coverage")
        if not all(isinstance(v, str) for v in (*limitations, *excluded)):
            raise TypeError("Scanner coverage contains invalid descriptions")
        rows: list[SourceFile] = []
        seen: set[str] = set()
        for item in files:
            path, count = getattr(item, "path", None), getattr(item, "size", None)
            admitted, digest = (
                getattr(item, "text_admitted", None),
                getattr(item, "sha256_hex", None),
            )
            if (
                not isinstance(path, str)
                or not path
                or path.startswith("/")
                or "\\" in path
                or "\x00" in path
                or any(segment in ("", ".", "..") for segment in path.split("/"))
            ):
                raise ValueError("Scanner returned invalid relative file path")
            if path in seen:
                raise ValueError("Scanner returned duplicate file path")
            seen.add(path)
            if (
                type(count) is not int
                or count < 0
                or type(admitted) is not bool
                or not isinstance(digest, str)
            ):
                raise TypeError("Scanner returned an invalid source entry")
            if admitted and not _DIGEST.fullmatch(digest):
                raise ValueError("Admitted source is missing a verified digest")
            if not admitted and digest:
                raise ValueError("Unadmitted source unexpectedly has a digest")
            rows.append(SourceFile(path, count, digest if admitted else None, admitted))
        # An unadmitted file or a reported limitation prevents a complete claim,
        # even if a future Scanner implementation mistakenly returns partial=False.
        incomplete = partial or bool(limitations) or any(not row.text_admitted for row in rows)
        return SourceInventory(
            report_root, tuple(rows), tuple(excluded), tuple(limitations), incomplete
        )
