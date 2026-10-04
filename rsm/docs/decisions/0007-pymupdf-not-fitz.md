# ADR 0007 — PyMuPDF (not `fitz`)

**Status:** NEW. Binding.

Install `pymupdf`; import `pymupdf`. The `fitz` PyPI distribution is a
different, unmaintained package and must not be installed. Enforcement:
`backend/tools/check_pymupdf_import.py` rejects any `import fitz` and any
`fitz` entry in `pyproject.toml`.
