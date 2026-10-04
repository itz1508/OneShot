"""Canonical payload + the four transport adapters.

Rule: every transport reads the output of transports.canonical.build_payload.
Transports do NOT persist state and do NOT import daemon/cli/api/mcp_server.
"""
from .canonical import build_payload, CanonicalPayload
from .json_export import to_json_export
from .stdout import to_stdout

__all__ = ["build_payload", "CanonicalPayload", "to_json_export", "to_stdout"]
