"""PDF extractor via PyMuPDF (imported as `pymupdf`; never `fitz`)."""

from __future__ import annotations

from typing import Any

from ..bucket.model import Bucket
from ._common import build_bucket


def extract_pdf(pdf_bytes: bytes, *, source_uri: str | None = None) -> Bucket:
    """Deterministic text extraction from a PDF.

    Import rule (ADR 0007): `import pymupdf`. The `fitz` PyPI distribution
    is explicitly forbidden by backend/tools/check_boundaries.py and spec §5.2.
    """
    import pymupdf  # noqa: F401  (deliberate: the import gate checks for the right module)

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        page_texts: list[str] = []
        for page in doc:
            page_texts.append(page.get_text("text"))
        full_content = "\n\n".join(page_texts)

        metadata: dict[str, Any] = {
            "page_count": doc.page_count,
            "pdf_metadata": {k: v for k, v in (doc.metadata or {}).items() if v},
        }
    finally:
        doc.close()

    return build_bucket(
        origin="pdf",
        full_content=full_content,
        source_uri=source_uri,
        metadata=metadata,
    )
