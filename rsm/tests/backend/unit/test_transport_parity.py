"""E2E-11 — every transport consumes the SAME canonical payload."""

from datetime import datetime, timezone
from rsm.extraction.text import extract_text
from rsm.transports.canonical import build_payload
from rsm.transports.http.view import http_view
from rsm.transports.mcp.view import mcp_resource_view
from rsm.transports.json_export import to_json_export


def test_all_transports_agree_on_hash():
    b = extract_text("hello world")
    payload = build_payload(b)
    http = http_view(payload)
    mcp = mcp_resource_view(payload)
    je = to_json_export(payload)
    # Hash field appears identically in all three
    assert http["integrity"]["sha256"] == b.hash.value
    assert mcp["payload"]["integrity"]["sha256"] == b.hash.value
    assert b.hash.value.encode() in je
