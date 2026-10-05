from rsm.extraction.text import extract_text
def test_stdin():
    b = extract_text("via stdin", kind="stdin")
    assert b.provenance.origin == "stdin"
