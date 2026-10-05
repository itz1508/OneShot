from rsm.extraction.markdown import extract_markdown
def test_md_round_trip():
    b = extract_markdown("# hi\n\nbody")
    assert b.provenance.origin == "markdown"
    assert "# hi" in b.full_content
