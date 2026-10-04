"""Smoke test for PDF extraction via PyMuPDF (`pymupdf`)."""
import pytest
pymupdf = pytest.importorskip("pymupdf")


def _make_pdf_bytes(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def test_pdf_round_trip():
    from rsm.extraction.pdf import extract_pdf
    data = _make_pdf_bytes("hello pdf")
    b = extract_pdf(data)
    assert b.provenance.origin == "pdf"
    assert "hello pdf" in b.full_content
