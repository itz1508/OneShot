"""Research catalog tests — CAT01-CAT12.

Tests catalog loading, unique IDs, matching, no-match fallback,
and that synthetic content never supplies factual authority.
"""

import pytest

from agent.contracts.research import (
    CatalogMatchStatus,
    ResearchIntent,
)
from agent.research_catalog import ResearchCatalog


@pytest.fixture
def catalog():
    cat = ResearchCatalog()
    cat.load()
    return cat


class TestCatalogLoading:
    def test_catalog_loads_successfully(self, catalog):
        """CAT01: Catalog loads successfully."""
        assert catalog.version == "1.0.0"
        assert len(catalog.samples) > 0

    def test_sample_ids_unique(self, catalog):
        """CAT02: All sample IDs are unique."""
        ids = catalog.sample_ids
        assert len(ids) == len(set(ids))

    def test_ten_samples(self, catalog):
        """CAT03: Exactly 10 samples in catalog."""
        assert len(catalog.samples) == 10

    def test_all_samples_synthetic(self, catalog):
        """CAT04: All samples marked synthetic."""
        for s in catalog.samples:
            assert s.is_synthetic is True

    def test_metadata_and_criteria_present(self, catalog):
        """CAT05: Metadata and success criteria present for all samples."""
        for s in catalog.samples:
            assert s.catalog_id
            assert s.category
            assert s.version
            assert len(s.success_criteria) > 0
            assert len(s.research_checklist) > 0

    def test_mcp_sample_has_fixture_blueprint(self, catalog):
        """CAT06: MCP sample has fixture blueprint."""
        mcp = catalog.get_sample("SAMPLE-MCP-BUILD-001")
        assert mcp is not None
        assert mcp.fixture_blueprint is not None
        assert mcp.fixture_blueprint.get("preconditions_required") is True


class TestCatalogMatching:
    def test_feature_request_matches_feature_sample(self, catalog):
        """CAT07: Feature request matches feature sample."""
        m = catalog.match(
            ResearchIntent.INVESTIGATE_QUESTION,
            ("feature", "requirement", "functionality"),
        )
        assert m.match_status in (CatalogMatchStatus.EXACT, CatalogMatchStatus.MATCHED)
        assert m.catalog_id != "NONE"

    def test_fixture_request_matches_fixture_sample(self, catalog):
        """CAT08: Fixture request matches fixture sample."""
        m = catalog.match(
            ResearchIntent.CRAFT_FIXTURE,
            ("fixture", "test"),
        )
        assert m.match_status == CatalogMatchStatus.EXACT
        assert m.catalog_id == "SAMPLE-FIXTURE-001"

    def test_fixture_validity_matches(self, catalog):
        """CAT09: Fixture-validity request matches fixture-validity sample."""
        m = catalog.match(
            ResearchIntent.INVESTIGATE_FIXTURE_VALIDATION,
            ("fixture", "validity", "assessment"),
        )
        assert m.match_status == CatalogMatchStatus.EXACT
        assert m.catalog_id == "SAMPLE-FIXTURE-VALIDITY-001"

    def test_unmatched_continues_without_invented_match(self, catalog):
        """CAT10: Unmatched request continues without invented matches."""
        # Intent matches but keywords are completely unrelated -> partial
        m = catalog.match(
            ResearchIntent.INVESTIGATE_QUESTION,
            ("cooking", "recipe", "kitchen"),
        )
        # Should be partial (intent matches, keywords don't)
        assert m.match_status == CatalogMatchStatus.PARTIAL
        # Research continues with task-specific investigation
        assert m.is_synthetic is True

    def test_mcp_match(self, catalog):
        """CAT11: MCP request matches MCP sample."""
        m = catalog.match(
            ResearchIntent.INVESTIGATE_QUESTION,
            ("MCP", "server", "protocol"),
        )
        assert m.match_status == CatalogMatchStatus.EXACT
        assert m.catalog_id == "SAMPLE-MCP-BUILD-001"

    def test_exact_match_has_matched_conditions(self, catalog):
        """CAT12: Exact match records matched conditions."""
        m = catalog.match(
            ResearchIntent.CRAFT_FIXTURE,
            ("fixture", "test"),
        )
        assert m.match_status == CatalogMatchStatus.EXACT
        assert len(m.matched_conditions) > 0
        assert any("intent" in c for c in m.matched_conditions)


class TestCatalogAuthority:
    def test_no_sample_supplies_facts(self, catalog):
        """CAT13: No sample has is_synthetic=False."""
        for s in catalog.samples:
            assert s.is_synthetic is True, f"{s.catalog_id} should be synthetic"

    def test_match_result_is_synthetic(self, catalog):
        """CAT14: Match result is explicitly synthetic."""
        m = catalog.match(ResearchIntent.INVESTIGATE_QUESTION, ("code",))
        assert m.is_synthetic is True
