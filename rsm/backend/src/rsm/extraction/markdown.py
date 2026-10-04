"""Markdown extractor — passes content through verbatim as full_content."""

from __future__ import annotations

from ..bucket.model import Bucket
from ._common import build_bucket


def extract_markdown(text: str, *, source_uri: str | None = None) -> Bucket:
    return build_bucket(origin="markdown", full_content=text, source_uri=source_uri)
