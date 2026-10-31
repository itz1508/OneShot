"""Real V18 Scanner comparison, with independent expected relationships."""

from __future__ import annotations

import unittest
from hashlib import sha256

from agent.adapters.source_comparison import SourceComparison

try:
    from capabilities.scanner.comparison import inspect_bundle
except ImportError:
    inspect_bundle = None


def admitted(identifier: str, filename: str, raw: bytes) -> tuple[dict, bytes]:
    # This metadata shape is imposed by the existing source implementation.
    return (
        {"id": identifier, "name": filename, "version": 1, "sha256": sha256(raw).hexdigest()},
        raw,
    )


@unittest.skipUnless(inspect_bundle is not None, "Real V18 comparison owner unavailable")
class SourceComparisonTests(unittest.TestCase):
    def test_changed_same_name(self) -> None:
        comparison = SourceComparison(inspect_bundle).compare(
            [
                admitted("old", "item.txt", b"before\n"),
                admitted("new", "item.txt", b"after\n"),
            ],
            target_id="new",
        )
        self.assertTrue(comparison.comparison_complete)
        self.assertTrue(comparison.content_complete)
        self.assertEqual({row.status for row in comparison.differences}, {"CHANGED"})
        self.assertTrue(
            all(row.directional_finding == "COUNTERPART_PRESENT" for row in comparison.differences)
        )
        self.assertFalse(comparison.semantic_gap_verified)

    def test_same_content_other_path_is_not_assumed_semantically_same(self) -> None:
        raw = b"same bytes\n"
        comparison = SourceComparison(inspect_bundle).compare(
            [
                admitted("old", "a.txt", raw),
                admitted("new", "b.txt", raw),
            ],
            target_id="new",
        )
        self.assertEqual({row.directional_finding for row in comparison.differences}, {"MOVED"})
        self.assertFalse(comparison.semantic_gap_verified)

    def test_only_one_source_cannot_prove_relative_missing(self) -> None:
        comparison = SourceComparison(inspect_bundle).compare(
            [admitted("solo", "a.txt", b"alone\n")]
        )
        self.assertEqual(
            {row.directional_finding for row in comparison.differences}, {"NOT_COMPARED"}
        )

    def test_partial_source_cannot_be_claimed_complete(self) -> None:
        result = SourceComparison(inspect_bundle).compare(
            [
                admitted("good", "a.txt", b"readable\n"),
                admitted("bad", "a.txt", b"bad\xffdata"),
            ],
            target_id="bad",
        )
        self.assertFalse(result.content_complete)
        self.assertFalse(result.semantic_gap_verified)

    def test_invalid_admission_is_rejected_by_owner(self) -> None:
        source = admitted("bad", "a.txt", b"expected\n")
        bad_metadata = {**source[0], "sha256": "0" * 64}
        with self.assertRaises(ValueError):
            SourceComparison(inspect_bundle).compare([(bad_metadata, source[1])])

    def test_empty_scope_is_not_declared_complete(self) -> None:
        with self.assertRaises(ValueError):
            SourceComparison(inspect_bundle).compare([])

    def test_wrong_result_scope_is_rejected(self) -> None:
        source = admitted("expected", "a.txt", b"hello")

        def wrong_scope(_sources, *, target_id=None, objective=""):
            return {
                "sources": [
                    {"source_id": "different", "inventory_complete": True, "limitations": []}
                ],
                "records": [],
                "comparison_complete": True,
                "content_complete": True,
                "target_id": target_id,
                "method": "false claim",
            }

        with self.assertRaises(ValueError):
            SourceComparison(wrong_scope).compare([source])

    def test_unknown_owner_report_fails_closed(self) -> None:
        with self.assertRaises(TypeError):
            SourceComparison(lambda *_args, **_kw: {"records": [], "sources": []}).compare(
                [admitted("scope", "x.txt", b"x")]
            )


if __name__ == "__main__":
    unittest.main()
