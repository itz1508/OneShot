"""Project bounded comparison evidence from the existing Scanner owner.

The host provides the authorized comparison callable and its admitted inputs.
This module does not implement comparison, decide semantic gaps, or infer that
source completeness satisfies a workflow acceptance criterion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


class SourceComparator(Protocol):
    def __call__(
        self,
        sources: list[tuple[dict, bytes]],
        *,
        target_id: str | None = None,
        objective: str = "",
    ) -> dict: ...


@dataclass(frozen=True)
class Difference:
    evidence_id: str
    source_id: str
    path: str
    sha256: str | None
    status: str
    directional_finding: str
    counterpart_ids: tuple[str, ...]
    limitation: str | None
    read_status: str


@dataclass(frozen=True)
class ComparisonEvidence:
    target_id: str | None
    differences: tuple[Difference, ...]
    comparison_complete: bool
    content_complete: bool
    limitations: tuple[str, ...]
    method: str
    semantic_gap_verified: bool = False


class SourceComparison:
    """Keep partial/unknown results distinct from authoritative gap checks."""

    def __init__(self, comparator: SourceComparator) -> None:
        self._comparator = comparator

    def compare(
        self,
        sources: list[tuple[dict, bytes]],
        *,
        target_id: str | None = None,
        objective: str = "",
    ) -> ComparisonEvidence:
        if not sources:
            raise ValueError("Comparison requires at least one admitted source")
        source_ids = [source.get("id") for source, _ in sources if isinstance(source, dict)]
        if (
            len(source_ids) != len(sources)
            or not all(isinstance(sid, str) and sid for sid in source_ids)
            or len(source_ids) != len(set(source_ids))
        ):
            raise ValueError("Comparison source identities are invalid or duplicated")
        if target_id is not None and target_id not in source_ids:
            raise ValueError("Target is not within admitted scope")
        report = self._comparator(sources, target_id=target_id, objective=objective)
        if not isinstance(report, dict):
            raise TypeError("Scanner comparison returned no report")
        rows = report.get("records")
        states = report.get("sources")
        if not isinstance(rows, list) or not isinstance(states, list):
            raise TypeError("Scanner comparison lacks source/record evidence")
        if (
            type(report.get("comparison_complete")) is not bool
            or type(report.get("content_complete")) is not bool
        ):
            raise TypeError("Scanner comparison lacks coverage flags")
        if report.get("target_id") != target_id:
            raise ValueError("Scanner comparison returned a different target")
        if len(states) != len(source_ids) or {
            v.get("source_id") for v in states if isinstance(v, dict)
        } != set(source_ids):
            raise ValueError("Scanner result source scope differs from requested inputs")
        limitations: list[str] = []
        for state in states:
            if not isinstance(state, dict) or not isinstance(state.get("source_id"), str):
                raise TypeError("Invalid Scanner source coverage")
            ls = state.get("limitations")
            if not isinstance(ls, list) or not all(isinstance(s, str) for s in ls):
                raise TypeError("Invalid Scanner source limitations")
            limitations.extend(f"{state['source_id']}: {s}" for s in ls)
            if state.get("inventory_complete") is not True:
                limitations.append(f"{state['source_id']}: inventory incomplete")
        projected: list[Difference] = []
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("Invalid comparison record")
            keys = (
                "evidence_id",
                "source_id",
                "path",
                "status",
                "read_status",
                "directional_finding",
            )
            if not all(isinstance(row.get(k), str) and row[k] for k in keys):
                raise TypeError("Comparison record has missing identity/status")
            if row["source_id"] not in source_ids:
                raise ValueError("Scanner comparison returned a record outside the source scope")
            sha = row.get("sha256")
            if sha is not None and (
                not isinstance(sha, str) or re.fullmatch(r"[0-9a-f]{64}", sha) is None
            ):
                raise ValueError("Comparison record has invalid digest")
            peers = row.get("counterpart_ids")
            if not isinstance(peers, list) or not all(isinstance(i, str) for i in peers):
                raise TypeError("Comparison lacks counterpart references")
            limit = row.get("limitation")
            if limit is not None and not isinstance(limit, str):
                raise TypeError("Invalid record limitation")
            if limit:
                limitations.append(f"{row['source_id']}:{row['path']}: {limit}")
            projected.append(
                Difference(
                    row["evidence_id"],
                    row["source_id"],
                    row["path"],
                    sha,
                    row["status"],
                    row["directional_finding"],
                    tuple(peers),
                    limit,
                    row["read_status"],
                )
            )
        comparison_complete = bool(report["comparison_complete"]) and not limitations
        content_complete = (
            bool(report["content_complete"])
            and comparison_complete
            and all(d.read_status == "COMPLETE" for d in projected)
        )
        method = report.get("method")
        if not isinstance(method, str) or not method:
            raise TypeError("Scanner comparison did not specify method")
        return ComparisonEvidence(
            target_id,
            tuple(projected),
            comparison_complete,
            content_complete,
            tuple(limitations),
            method,
        )
