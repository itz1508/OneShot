"""Extraction adapters: markdown, text, chatgpt_export, pdf, folder, opaque."""
from .markdown import extract_markdown
from .text import extract_text
from .chatgpt_export import extract_chatgpt_export
from .pdf import extract_pdf
from .folder import extract_folder, FolderExtractionResult
from .opaque import extract_opaque

__all__ = [
    "extract_markdown",
    "extract_text",
    "extract_chatgpt_export",
    "extract_pdf",
    "extract_folder",
    "FolderExtractionResult",
    "extract_opaque",
]
