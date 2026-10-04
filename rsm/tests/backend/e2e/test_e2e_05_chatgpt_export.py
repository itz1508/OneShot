from rsm.extraction.chatgpt_export import extract_chatgpt_export
def test_chatgpt_export_round_trip():
    raw = {"title": "demo", "model": "gpt-x", "conversation": [{"role": "user", "content": "hi"}]}
    b = extract_chatgpt_export(raw)
    assert b.provenance.origin == "chatgpt_export"
    assert b.metadata.get("message_count") == 1
    assert '"content":"hi"' in b.full_content
