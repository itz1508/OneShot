# ADR 0001 — Single Daemon Authority

**Status:** Carried forward from the governing spec.

The daemon is the sole authoritative state owner. The UI is a view; MCP and
HTTP are transports; no other component may own canonical state.
