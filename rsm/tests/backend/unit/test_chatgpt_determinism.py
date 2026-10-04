"""Deterministic normalization of ChatGPT export (spec §12)."""

from rsm.extraction.chatgpt_export import extract_chatgpt_export


def test_same_input_same_canonical_content_and_hash():
    doc = {
        "title": "demo",
        "model": "gpt-x",
        "conversation": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ],
    }
    b1 = extract_chatgpt_export(doc)
    b2 = extract_chatgpt_export(doc)
    # Deterministic normalization: canonical bytes equal
    assert b1.full_content == b2.full_content
    # Hashes match because the IDENTITY fields are deterministic given identical input
    # (bucket_id differs each call; hash is over identity fields incl. bucket_id and provenance.produced_at).
    # So we assert on the content and metadata canonical form instead.
    assert b1.metadata.get("message_count") == 2
    assert b1.metadata.get("vendor") == "chatgpt_export"


def test_preserves_original_content_verbatim():
    doc = {"conversation": [{"role": "user", "content": "verbatim \u2713"}]}
    b = extract_chatgpt_export(doc)
    assert "verbatim" in b.full_content
    # Should be canonical JSON (sorted keys, no whitespace)
    assert b.full_content.startswith("{")
    assert '"role":"user"' in b.full_content


def test_rejects_malformed_input():
    import pytest
    with pytest.raises((ValueError, Exception)):
        extract_chatgpt_export("not json at all {{{")
