# Transport Parity

All four transports (HTTP, MCP, JSON export, stdout) consume the output of
`rsm.transports.canonical.build_payload`. E2E-11 asserts the same hash and
same `schema_version` appear in every transport's projection.
