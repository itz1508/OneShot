"""Actual V18 FileStore persists/readbacks bytes; no duplicate artifact owner."""
from __future__ import annotations

from hashlib import sha256
import tempfile
import unittest
from pathlib import Path

from agent.adapters.content_integrity import VerifiedContent

try:
    from systems.file_store import FileStore
except ImportError:
    FileStore = None


@unittest.skipUnless(FileStore is not None, "Real V18 FileStore not installed")
class ContentIntegrityTests(unittest.TestCase):
    def test_store_reopen_and_readback(self) -> None:
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname) / "objects"
            original = b"approval is NOT granted\n"
            digest = VerifiedContent(FileStore(root)).put(original)
            self.assertEqual(digest, sha256(original).hexdigest())
            self.assertEqual(VerifiedContent(FileStore(root)).read(digest), original)

    def test_reject_missing_or_corrupt_content(self) -> None:
        with tempfile.TemporaryDirectory() as dirname:
            store = VerifiedContent(FileStore(Path(dirname) / "objects"))
            with self.assertRaises(ValueError):
                store.read("not-a-digest")
            with self.assertRaises((FileNotFoundError, OSError)):
                store.read("f" * 64)

    def test_invalid_payload_rejected_before_persist(self) -> None:
        with tempfile.TemporaryDirectory() as dirname:
            store = VerifiedContent(FileStore(Path(dirname) / "objects"))
            with self.assertRaises(TypeError):
                store.put("string instead of bytes")  # type: ignore[arg-type]

    def test_corrupt_responses_rejected(self) -> None:
        class CorruptStore:
            def put(self, raw: bytes) -> str:
                return "0" * 64
            def read(self, digest: str) -> bytes:
                return b"corrupted"
        with self.assertRaises(ValueError):
            VerifiedContent(CorruptStore()).put(b"expected")
        with self.assertRaises(ValueError):
            VerifiedContent(CorruptStore()).read("0" * 64)


if __name__ == "__main__":
    unittest.main()
