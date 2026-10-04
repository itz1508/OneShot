from rsm.extraction.text import extract_text
def test_txt():
    b = extract_text("plain", kind="text")
    assert b.provenance.origin == "text"
