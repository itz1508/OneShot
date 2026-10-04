"""Normalized source projection.

A *normalized* representation of a Bucket's content is the deterministic view
Snapshot derivation reads from. For V2 it is:

- `content_text` — exactly the Bucket's `full_content` (unchanged bytes).
- `metadata` — exactly the Bucket's `metadata` (unchanged).
- `size_bytes` — UTF-8 byte length of `content_text`.
- `size_chars` — length in Unicode code points.
- `token_estimate` — a crude, deterministic estimate (⌈chars / 4⌉) used ONLY
  when the caller asks for a token-count-shaped number. **Never** reported as
  an exact model token count.

Normalization MUST NOT:
  - invent content
  - summarise
  - reinterpret
  - execute source material
  - call out to any LLM / provider SDK
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..bucket.model import Bucket


class NormalizedSource(BaseModel):
    """Deterministic structural view of a Bucket's content."""
    model_config = ConfigDict(extra="forbid")

    bucket_id: str
    schema_version: str = "1"
    origin: str
    content_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    size_bytes: int
    size_chars: int
    token_estimate: int


def _token_estimate(chars: int) -> int:
    """Deterministic estimate: ceil(chars / 4). NOT an exact model token count."""
    if chars <= 0:
        return 0
    return (chars + 3) // 4


def normalize(bucket: Bucket) -> NormalizedSource:
    """Project a Bucket onto its normalized representation (pure function)."""
    text = bucket.full_content
    chars = len(text)
    bytes_ = len(text.encode("utf-8"))
    return NormalizedSource(
        bucket_id=bucket.bucket_id,
        schema_version=bucket.schema_version,
        origin=bucket.provenance.origin,
        content_text=text,
        metadata=dict(bucket.metadata),
        size_bytes=bytes_,
        size_chars=chars,
        token_estimate=_token_estimate(chars),
    )
