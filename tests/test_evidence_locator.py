"""Source locator checks; semantic claim support is intentionally out of scope."""

from __future__ import annotations

import unittest

from agent.adapters.evidence_locator import verify_line


class LocatorTests(unittest.TestCase):
    def test_exact_line_and_excerpt(self) -> None:
        self.assertTrue(verify_line("a\nbeta\n", 2, excerpt="bet").matched)
        self.assertFalse(verify_line("a\nbeta\n", 1, excerpt="beta").matched)

    def test_invalid_positions_and_blank_excerpt(self) -> None:
        for number in (0, -1, True, 99):
            self.assertFalse(verify_line("one", number, excerpt="one").matched)
        self.assertFalse(verify_line("one", 1, excerpt="").matched)
        self.assertFalse(verify_line("one", 1, excerpt="two").matched)
        self.assertFalse(verify_line(None, 1, excerpt="one").matched)  # type: ignore[arg-type]

    def test_same_text_on_different_line_does_not_validate_wrong_locator(self) -> None:
        source = "approval denied\napproval granted\n"
        self.assertFalse(verify_line(source, 1, excerpt="approval granted").matched)
        self.assertTrue(verify_line(source, 2, excerpt="approval granted").matched)


if __name__ == "__main__":
    unittest.main()
