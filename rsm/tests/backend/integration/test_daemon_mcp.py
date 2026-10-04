"""Build the MCP server descriptor; exercise read_resource via the daemon store."""

from rsm.daemon.service import DaemonService
from rsm.daemon.store import FsStore
from rsm.daemon.eventlog import EventLog
from rsm.mcp_server.server import build_server


def test_mcp_descriptor_round_trip(tmp_path):
    daemon = DaemonService(
        store=FsStore(tmp_path / "buckets"),
        eventlog=EventLog(tmp_path / "events.log"),
    )
    bucket = daemon.ingest_text("hello mcp")
    srv = build_server(daemon)
    resources = srv["list_resources"]()
    assert any(r.uri.endswith(bucket.bucket_id) for r in resources)
    doc = srv["read_resource"](f"rsm://bucket/{bucket.bucket_id}")
    assert doc["payload"]["bucket"]["full_content"] == "hello mcp"
