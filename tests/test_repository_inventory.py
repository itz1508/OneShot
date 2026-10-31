"""Real repository Scanner integration (the Scanner is not reimplemented)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.adapters.repository_inventory import SourceInspection

try:
    from capabilities.scanner.repository import inspect_repository
except ImportError:
    inspect_repository = None


@unittest.skipUnless(inspect_repository is not None, "Real V18 Scanner not installed")
class RepositoryInventoryTests(unittest.TestCase):
    def test_admitted_and_invalid_utf8_are_not_conflated(self) -> None:
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / "okay.py").write_text("value = 3\n", encoding="utf-8")
            (root / "bad.md").write_bytes(b"bad\xff")
            result = SourceInspection(inspect_repository).inspect(root)
            rows = {row.path: row for row in result.files}
            self.assertTrue(rows["okay.py"].text_admitted)
            self.assertEqual(len(rows["okay.py"].sha256 or ""), 64)
            self.assertFalse(rows["bad.md"].text_admitted)
            self.assertTrue(result.partial)
            self.assertFalse(result.ready_for_complete_comparison)
            self.assertTrue(any("bad.md" in s for s in result.limitations))

    def test_symlink_is_not_traversed(self) -> None:
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / "okay.py").write_text("safe = True\n", encoding="utf-8")
            try:
                (root / "alias.py").symlink_to(root / "okay.py")
            except (OSError, NotImplementedError):
                self.skipTest("Symlinks not supported")
            result = SourceInspection(inspect_repository).inspect(root)
            self.assertFalse(any(row.path == "alias.py" and row.text_admitted for row in result.files))

    def test_complete_small_scope(self) -> None:
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            (root / "code.py").write_text("x = 1\n", encoding="utf-8")
            observed = SourceInspection(inspect_repository).inspect(root)
            self.assertFalse(observed.partial)
            self.assertTrue(observed.ready_for_complete_comparison)

    def test_malformed_scanner_result_fails_closed(self) -> None:
        class Broken:
            files = ()
            root = "root"
            partial = False
            limitations = []
            excluded_paths = []
        Broken.files = (type("File", (), dict(path="../escape", size=3, text_admitted=True, sha256_hex="a" * 64))(),)
        with self.assertRaises(ValueError):
            SourceInspection(lambda _root: Broken()).inspect(Path("."))


if __name__ == "__main__":
    unittest.main()
