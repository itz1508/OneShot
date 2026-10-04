from rsm.extraction.text import extract_text
from rsm.transports.canonical import build_payload
from rsm.transports.http.view import http_view
from rsm.transports.mcp.view import mcp_resource_view
from rsm.transports.json_export import to_json_export


def test_parity():
    b = extract_text("parity test")
    p = build_payload(b)
    for view in (http_view(p),):
        assert view["schema_version"] == "1"
    assert mcp_resource_view(p)["payload"]["schema_version"] == "1"
    assert b"\"schema_version\":\"1\"" in to_json_export(p)
