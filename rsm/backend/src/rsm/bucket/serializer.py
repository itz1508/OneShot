"""Deterministic canonical JSON for buckets.

Rules:
- UTF-8, no BOM
- Keys sorted lexicographically at every depth
- No whitespace (compact separators)
- datetime -> ISO-8601 with timezone, 'Z' for UTC
- Stable across runs — this is what SHA-256 is computed over.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .model import Bucket


def _default(o: Any) -> Any:
    if isinstance(o, datetime):
        if o.tzinfo is None:
            o = o.replace(tzinfo=timezone.utc)
        return o.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    raise TypeError(f"Not canonically serialisable: {type(o).__name__}")


def canonical_dumps(payload: Any) -> bytes:
    """Return deterministic canonical JSON bytes."""
    if isinstance(payload, Bucket):
        payload = payload.model_dump(mode="json")
    return json.dumps(
        payload,
        default=_default,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
