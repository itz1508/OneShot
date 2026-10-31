"""Fail-closed locator check against already authorized, identified source text.

Matching an excerpt is not evidence that a semantic claim is correct. Source
identity and permissions are responsibilities of the calling host.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LocatorResult:
    matched: bool
    reason: str
    line_text: str | None = None


def verify_line(source_text: str, line_number: int, *, excerpt: str) -> LocatorResult:
    if not isinstance(source_text, str):
        return LocatorResult(False, "source text unavailable")
    if type(line_number) is not int or line_number < 1:
        return LocatorResult(False, "line number must be a positive integer")
    if not isinstance(excerpt, str) or not excerpt:
        return LocatorResult(False, "nonempty excerpt required")
    lines = source_text.splitlines()
    if line_number > len(lines):
        return LocatorResult(False, "line outside source")
    observed = lines[line_number - 1]
    if excerpt not in observed:
        return LocatorResult(False, "excerpt does not occur on line", observed)
    return LocatorResult(True, "matched", observed)
