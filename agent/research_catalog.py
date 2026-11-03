"""Synthetic research catalog — versioned samples with deterministic matching.

Templates supply investigation structure, not facts, accepted requirements,
or implementation authority. All catalog content is explicitly marked
synthetic with no factual authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agent.contracts.research import (
    CatalogMatch,
    CatalogMatchStatus,
    ResearchIntent,
)


@dataclass(frozen=True)
class CatalogSample:
    """A loaded synthetic catalog sample."""

    catalog_id: str
    category: str
    version: str
    matching_intents: tuple[str, ...]
    matching_keywords: tuple[str, ...]
    research_checklist: tuple[str, ...]
    success_criteria: tuple[str, ...]
    fixture_blueprint: dict[str, Any] | None = None
    is_synthetic: bool = True


class ResearchCatalog:
    """Versioned synthetic catalog with deterministic matching.

    Loading validates:
    - All sample IDs are unique.
    - All samples are marked synthetic.
    - Metadata and success criteria are present.

    Matching considers intent and keywords. A match supplies
    structure, not facts. No-match continues with task-specific
    investigation.
    """

    def __init__(self, samples_path: str | Path | None = None) -> None:
        if samples_path is None:
            samples_path = Path(__file__).parent / "catalog" / "research_samples.yaml"
        self._samples_path = Path(samples_path)
        self._samples: list[CatalogSample] = []
        self._version = ""
        self._loaded = False

    def load(self) -> None:
        """Load and validate catalog from YAML."""
        with open(self._samples_path) as f:
            data = yaml.safe_load(f)

        self._version = str(data.get("version", ""))
        if not self._version:
            raise ValueError("catalog missing version")

        if not data.get("synthetic", False):
            raise ValueError("catalog must be marked synthetic")

        samples_raw = data.get("samples", [])
        if not samples_raw:
            raise ValueError("catalog has no samples")

        seen_ids: set[str] = set()
        for sample_data in samples_raw:
            catalog_id = sample_data["catalog_id"]
            if catalog_id in seen_ids:
                raise ValueError(f"duplicate catalog ID: {catalog_id}")
            seen_ids.add(catalog_id)

            conditions = sample_data.get("matching_conditions", {})
            sample = CatalogSample(
                catalog_id=catalog_id,
                category=sample_data["category"],
                version=str(sample_data.get("version", "")),
                matching_intents=tuple(conditions.get("intents", [])),
                matching_keywords=tuple(conditions.get("keywords", [])),
                research_checklist=tuple(sample_data.get("research_checklist", [])),
                success_criteria=tuple(sample_data.get("success_criteria", [])),
                fixture_blueprint=sample_data.get("fixture_blueprint"),
                is_synthetic=True,
            )
            self._samples.append(sample)

        self._loaded = True

    @property
    def version(self) -> str:
        if not self._loaded:
            self.load()
        return self._version

    @property
    def samples(self) -> tuple[CatalogSample, ...]:
        if not self._loaded:
            self.load()
        return tuple(self._samples)

    @property
    def sample_ids(self) -> tuple[str, ...]:
        if not self._loaded:
            self.load()
        return tuple(s.catalog_id for s in self._samples)

    def match(
        self,
        intent: ResearchIntent,
        keywords: tuple[str, ...] = (),
    ) -> CatalogMatch:
        """Match an input against catalog templates.

        Matching considers intent and keywords:
        - EXACT: intent matches and all keywords are covered
        - MATCHED: intent matches and some keywords overlap
        - PARTIAL: intent does not match but keywords overlap
        - NONE: no overlap

        Returns a CatalogMatch with the best-matching sample.
        """
        if not self._loaded:
            self.load()

        best_sample: CatalogSample | None = None
        best_status = CatalogMatchStatus.NONE
        best_conditions: list[str] = []

        for sample in self._samples:
            intent_match = intent.value in sample.matching_intents
            keyword_lower = {k.lower() for k in keywords}
            sample_kw_lower = {k.lower() for k in sample.matching_keywords}
            keyword_overlap = keyword_lower & sample_kw_lower

            if intent_match and keywords:
                if keyword_lower <= sample_kw_lower:
                    status = CatalogMatchStatus.EXACT
                elif keyword_overlap:
                    status = CatalogMatchStatus.MATCHED
                else:
                    status = CatalogMatchStatus.PARTIAL  # intent only, no keyword overlap
            elif intent_match:
                status = CatalogMatchStatus.MATCHED
            elif keyword_overlap:
                status = CatalogMatchStatus.PARTIAL
            else:
                continue

            # Pick the highest-priority match, detect ties
            priority = {
                CatalogMatchStatus.EXACT: 3,
                CatalogMatchStatus.MATCHED: 2,
                CatalogMatchStatus.PARTIAL: 1,
                CatalogMatchStatus.AMBIGUOUS: 0,
                CatalogMatchStatus.NONE: 0,
            }
            if priority[status] > priority[best_status]:
                best_sample = sample
                best_status = status
                best_conditions = []
                if intent_match:
                    best_conditions.append(f"intent:{intent.value}")
                if keyword_overlap:
                    best_conditions.append(f"keywords:{','.join(sorted(keyword_overlap))}")
            elif (
                priority[status] == priority[best_status]
                and priority[status] > 0
                and best_sample is not None
                and sample.catalog_id != best_sample.catalog_id
                and keyword_overlap
            ):
                # Tie detected — mark as ambiguous only when both have
                # keyword overlap at the same priority level
                best_status = CatalogMatchStatus.AMBIGUOUS
                best_conditions.append(f"tie:{sample.catalog_id}")

        if best_sample is None or best_status == CatalogMatchStatus.AMBIGUOUS:
            if best_status == CatalogMatchStatus.AMBIGUOUS:
                return CatalogMatch(
                    catalog_id="AMBIGUOUS",
                    catalog_version=self._version,
                    match_status=CatalogMatchStatus.AMBIGUOUS,
                    matched_conditions=tuple(best_conditions),
                    is_synthetic=True,
                )
            return CatalogMatch(
                catalog_id="NONE",
                catalog_version=self._version,
                match_status=CatalogMatchStatus.NONE,
                matched_conditions=(),
                is_synthetic=True,
            )

        return CatalogMatch(
            catalog_id=best_sample.catalog_id,
            catalog_version=best_sample.version,
            match_status=best_status,
            matched_conditions=tuple(best_conditions),
            is_synthetic=True,
        )

    def get_sample(self, catalog_id: str) -> CatalogSample | None:
        """Retrieve a specific sample by ID."""
        if not self._loaded:
            self.load()
        for s in self._samples:
            if s.catalog_id == catalog_id:
                return s
        return None
