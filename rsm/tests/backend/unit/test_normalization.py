"""Normalization is deterministic and does not rewrite source."""

from rsm.extraction.text import extract_text
from rsm.normalization.model import normalize


def test_normalize_preserves_full_content_bytes():
    b = extract_text("hello world — \u2713")
    n = normalize(b)
    assert n.content_text == b.full_content
    assert n.size_chars == len(b.full_content)
    assert n.size_bytes == len(b.full_content.encode("utf-8"))


def test_normalize_is_deterministic():
    b = extract_text("same input")
    n1 = normalize(b)
    n2 = normalize(b)
    assert n1.model_dump() == n2.model_dump()


def test_normalize_does_not_mutate_bucket():
    b = extract_text("don't touch me")
    original_dump = b.model_dump(mode="json")
    _ = normalize(b)
    assert b.model_dump(mode="json") == original_dump


def test_token_estimate_is_deterministic_and_cheap():
    b = extract_text("x" * 400)
    n = normalize(b)
    # ceil(400/4) = 100
    assert n.token_estimate == 100


def test_metadata_passes_through():
    b = extract_text("hi")
    # Pydantic bucket has empty metadata by default
    assert normalize(b).metadata == {}
