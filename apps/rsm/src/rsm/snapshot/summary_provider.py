"""Summary provider plug-in interface (spec §6, §7).

RSM core does NOT run an LLM. A SummaryProvider is an EXTERNAL adapter that
accepts normalized text and a budget and returns a bounded derived summary.

If no provider is wired in, Snapshot construction with an overflowing source
MUST fail explicitly (SummaryUnavailable) — the system never silently drops
or truncates source content.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class SummaryUnavailable(Exception):
    """Raised when a Snapshot requires reduction but no provider is wired."""


@runtime_checkable
class SummaryProvider(Protocol):
    """Produce a bounded derived summary of a block of normalized text.

    Implementations MUST:
      - return a string whose UTF-8 byte length ≤ `budget_bytes` AND whose
        character length ≤ `budget_chars`;
      - clearly identify themselves via a stable `.name`.
    """

    name: str

    def summarize(
        self,
        *,
        text: str,
        budget_bytes: int,
        budget_chars: int,
    ) -> str: ...


class NullSummaryProvider:
    """Explicit no-op provider — raises SummaryUnavailable when invoked."""

    name = "null"

    def summarize(self, *, text: str, budget_bytes: int, budget_chars: int) -> str:
        raise SummaryUnavailable(
            "No SummaryProvider is configured; Snapshot cannot be reduced. "
            "Register a provider or widen the budget."
        )


class PrefixSummaryProvider:
    """Deterministic, LLM-free provider for tests and conservative CLI use.

    It returns a prefix of the input text that fits within both budget bounds,
    followed (when there is room) by a short, explicit marker so the result
    is never mistaken for original source (spec §8). If the budget is so
    tight that even the marker will not fit, it is omitted; the caller still
    detects derivation via `SnapshotContent.kind == SUMMARY`.

    This provider:
      - preserves source order,
      - makes no claim of "summarisation" (it is a bounded excerpt),
      - operates purely on UTF-8 character/byte counts.
    """

    name = "prefix"
    _MARKER = "\n…[TRUNCATED BY RSM PrefixSummaryProvider]…"

    def summarize(self, *, text: str, budget_bytes: int, budget_chars: int) -> str:
        marker = self._MARKER
        marker_bytes = len(marker.encode("utf-8"))
        marker_chars = len(marker)

        include_marker = (
            marker_chars <= budget_chars and marker_bytes <= budget_bytes
        )

        if include_marker:
            char_budget = budget_chars - marker_chars
            byte_budget = budget_bytes - marker_bytes
        else:
            char_budget = budget_chars
            byte_budget = budget_bytes

        # Walk forward one codepoint at a time, respecting BOTH limits.
        out: list[str] = []
        used_bytes = 0
        used_chars = 0
        for ch in text:
            cb = len(ch.encode("utf-8"))
            if used_chars + 1 > char_budget or used_bytes + cb > byte_budget:
                break
            out.append(ch)
            used_chars += 1
            used_bytes += cb

        return "".join(out) + (marker if include_marker else "")
