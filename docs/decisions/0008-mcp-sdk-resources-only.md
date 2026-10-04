# ADR 0008 — MCP Python SDK, Resources Only

**Status:** NEW. Binding.

RSM exposes buckets through the official MCP Python SDK as resources with URIs
`rsm://bucket/<bucket_id>`. No MCP tools, no MCP-side persistence. The server
reads from the same authoritative daemon as every other transport.
