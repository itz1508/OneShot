"""Plain text / pasted / stdin extractor."""

from __future__ import annotations

from typing import Literal

from ..bucket.model import Bucket
from ._common import build_bucket


def extract_text(
    text: str,
    *,
    source_uri: str | None = None,
    kind: Literal["text", "pasted", "stdin"] = "text",
) -> Bucket:
    return build_bucket(origin=kind, full_content=text, source_uri=source_uri)
