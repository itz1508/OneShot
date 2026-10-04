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

## Canonical architecture (frozen)

```text
SOURCE
  │
  │ authoritative
  ▼
SCAN
  │
  │ fast discovery
  ▼
FILES
  │
  │ bounded/addressable source material
  ▼
READER + VISION
  │
  │ actual observation
  ├──────────────► READER TRACE
  │
  ▼
PROCESSOR
  │
  │ controlled preparation
  │ optional bounded reasoning
  ▼
PREPARED REPRESENTATION
  │
  ▼
REPLAY
  │
  │ delivery only
  ▼
AGENT
  │
  │ task reasoning
  ▼
RESULT
```

### Frozen responsibilities

```text
Scan discovers.
Reader observes.
Telemetry shows coverage.
Processor prepares.
Replay delivers.
Agent reasons.
```

### Frozen invariants

```text
Source is authoritative.

File is not a new Source.

Reader failure on one File does not automatically fail the entire read.

Processor may prepare and reduce, but does not become the Agent.

Processor never mutates Source.

Replay delivers; it does not transform.

Agent reasons; RSM does not become the Agent.

Reader trace reflects actual observation, not simulated progress.
```

Agent reasoning never occurs inside RSM. The RSM Processor may use
controlled reasoning where deterministic preparation reaches its limit —
provider-neutral, with provenance metadata preserved where the existing
architecture supports it. Agent output never automatically becomes a new
Source; storing a new source remains an explicit ingestion operation.

