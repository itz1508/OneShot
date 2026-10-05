"""MCP server exposing bucket contents as `rsm://bucket/<id>` resources.

The server reads from the authoritative daemon store; it never persists
state of its own.
"""

from __future__ import annotations

from typing import Any

from ..daemon.service import DaemonService
from ..transports.canonical import build_payload
from ..transports.mcp.view import mcp_resource_view


class _ResourceSpec:
    """Minimal resource descriptor the SDK (or a shim) can register."""
    def __init__(self, uri: str, name: str, mime_type: str):
        self.uri = uri
        self.name = name
        self.mime_type = mime_type


def build_server(daemon: DaemonService) -> dict[str, Any]:
    """Return a server descriptor consumable by the official `mcp` SDK.

    The dict is intentionally transport-agnostic — the SDK bootstrap script
    reads it in rsm.mcp_server.main. This indirection keeps the SDK dependency
    out of unit tests (which import this module only for its shape).
    """

    def list_resources() -> list[_ResourceSpec]:
        return [
            _ResourceSpec(
                uri=f"rsm://bucket/{bid}",
                name=f"RSM Bucket {bid}",
                mime_type="application/json",
            )
            for bid in daemon.store.iter_ids()
        ]

    def read_resource(uri: str) -> dict[str, Any]:
        prefix = "rsm://bucket/"
        if not uri.startswith(prefix):
            raise ValueError(f"Not an RSM bucket URI: {uri!r}")
        bucket_id = uri[len(prefix):]
        bucket = daemon.store.read(bucket_id)
        if bucket is None:
            raise LookupError(f"No bucket with id {bucket_id!r}")
        return mcp_resource_view(build_payload(bucket))

    return {
        "name": "rsm",
        "version": "0.0.0",
        "list_resources": list_resources,
        "read_resource": read_resource,
    }
