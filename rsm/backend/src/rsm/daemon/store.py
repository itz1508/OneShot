"""Bucket store (fs backend; sqlite would plug in at the same ABC).

Honours A1 immutability on every write.
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable

from ..api.errors import BucketFrozen
from ..bucket.immutability import BucketImmutabilityViolation, check_mutation
from ..bucket.model import Bucket


class BucketStore(ABC):
    @abstractmethod
    def read(self, bucket_id: str) -> Bucket | None: ...
    @abstractmethod
    def write(self, bucket: Bucket) -> None: ...
    @abstractmethod
    def iter_ids(self) -> Iterable[str]: ...


class FsStore(BucketStore):
    """Filesystem-backed store: one JSON file per bucket."""

    def __init__(self, root: str | os.PathLike[str]):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, bucket_id: str) -> Path:
        safe = bucket_id.replace("/", "_")
        return self.root / f"{safe}.json"

    def read(self, bucket_id: str) -> Bucket | None:
        p = self._path(bucket_id)
        if not p.exists():
            return None
        return Bucket.model_validate_json(p.read_text("utf-8"))

    def write(self, bucket: Bucket) -> None:
        p = self._path(bucket.bucket_id)
        after = bucket.model_dump(mode="json")
        if p.exists():
            before = json.loads(p.read_text("utf-8"))
            try:
                check_mutation(before, after)
            except BucketImmutabilityViolation as e:
                raise BucketFrozen(str(e), details={"bucket_id": bucket.bucket_id})
        p.write_text(bucket.model_dump_json(), encoding="utf-8")

    def iter_ids(self) -> Iterable[str]:
        for f in sorted(self.root.glob("*.json")):
            yield f.stem
