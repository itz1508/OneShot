# RSM app

The RSM daemon lives in [`apps/rsm/`](../../apps/rsm/). It is the
authoritative Replay State Memory service: capture → identity → provenance →
integrity → bucket → lifecycle → classification → execution → replay.

- Source: `apps/rsm/src/rsm/`
- Tests: `apps/rsm/tests/` (unit · integration · security · e2e)
- Entrypoints: `uv run rsm` (CLI) or `python -m rsm`
- Config example: [`rsm.conf.toml.example`](../../apps/rsm/rsm.conf.toml.example)

Architecture docs live alongside this file in `docs/architecture/`; ADRs are
in `docs/decisions/`.
