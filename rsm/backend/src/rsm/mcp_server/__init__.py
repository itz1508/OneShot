"""MCP server (resources only). Uses the `mcp` Python SDK.

ADR 0008 — resources only, no tools, no persistence.
"""
from .server import build_server
__all__ = ["build_server"]
