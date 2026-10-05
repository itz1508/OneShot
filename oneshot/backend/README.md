# rsm — Replay State Memory daemon

Authoritative RSM service (HTTP · MCP · CLI). See
[`docs/architecture/rsm.md`](../../docs/architecture/rsm.md) and
[`docs/architecture/boundaries.md`](../../docs/architecture/boundaries.md).

```bash
uv run --package rsm pytest -q tests   # 323 passed, 1 skipped (run from repo root)
uv run rsm                             # CLI
uv run python -m rsm                   # daemon entrypoint
```
