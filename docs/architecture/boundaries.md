# Import boundaries (codified)

`tools/verification/check_boundaries.py` enforces these rules in CI. A
violation fails the gate; there are no exceptions.

| Package | Must NOT import |
|---|---|
| `rsm.bucket` | `cli`, `api`, `mcp_server`, `daemon`, `transports`, `extraction` |
| `rsm.lifecycle` | anything outside `rsm.bucket` + stdlib |
| `rsm.transports` | `daemon`, `cli`, `api`, `mcp_server`, `interaction` |
| `rsm.classification` | `cli`, `api`, `daemon`, `mcp_server`, `transports`, `extraction` |
| `rsm.execution` | `cli`, `api`, `daemon`, `mcp_server`, `transports`, `extraction` |
| `rsm.replay` | `cli`, `api`, `daemon`, `mcp_server`, `interaction` |
| `rsm.normalization` | `cli`, `api`, `daemon`, `mcp_server`, `transports`, `interaction` |
| `rsm.snapshot` | `cli`, `api`, `daemon`, `mcp_server`, `transports`, `interaction` |
| `rsm.interaction` | `cli`, `api`, `daemon`, `mcp_server`, `transports`, `extraction` |
| `rsm.vision` | every other `rsm.*` package (stdlib + pydantic only) |
| `rsm.reader` | `cli`, `api`, `daemon`, `mcp_server`, `transports`, `extraction` |

Direction of dependencies: domain core (`bucket`, `lifecycle`) ← capability
modules (`classification`, `execution`, `replay`, `snapshot`, `normalization`)
← delivery (`transports`, `api`, `daemon`, `cli`, `mcp_server`). Nothing in
the core may depend upward.

See `tools/verification/check_boundaries.py` for the authoritative FORBIDDEN
map — this document mirrors it in prose.
