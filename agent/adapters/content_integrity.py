"""Verify bytes through an injected, existing content-addressed store.

This adapter owns no files, persistence, task IDs, or authorization decisions.
A content digest is not a Research/Plan/Build artifact reference.
"""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Protocol

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class ContentStore(Protocol):
    def put(self, raw: bytes) -> str: ...
    def read(self, digest: str) -> bytes: ...


class VerifiedContent:
    def __init__(self, byte_store: ContentStore) -> None:
        self._store = byte_store

    def put(self, raw: bytes) -> str:
        if not isinstance(raw, bytes):
            raise TypeError("Content must be bytes")
        expected = sha256(raw).hexdigest()
        actual = self._store.put(raw)
        if actual != expected:
            raise ValueError("Content store returned the wrong digest")
        if self.read(actual) != raw:
            raise ValueError("Persisted bytes differ from input")
        return actual

    def read(self, digest: str) -> bytes:
        if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
            raise ValueError("Invalid SHA-256 digest")
        data = self._store.read(digest)
        if not isinstance(data, bytes) or sha256(data).hexdigest() != digest:
            raise ValueError("Content store returned corrupted bytes")
        return data
