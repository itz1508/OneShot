from rsm.extraction.text import extract_text
def test_pasted():
    b = extract_text("pasted body", kind="pasted")
    assert b.provenance.origin == "pasted"
