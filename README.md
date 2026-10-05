# OneShot — monorepo (RSM v6.1)

**Replay State Memory (RSM)** is a source/context boundary for external
source material: capture → identity → provenance → integrity → bucket →
lifecycle → work classification → execution metadata → replay readiness →
release/replay → stable envelope → agent adapter → external agent.

RSM is **not** an LLM, an agent runtime, a model router, a provider manager,
a vector database, a prompt orchestrator, or a long-term memory system.

## Repository layout

```
D:\OneShot\
├── apps/
│   ├── rsm/                 RSM daemon (Python ≥3.11, uv workspace member)
│   │   ├── src/rsm/         domain + delivery packages (see docs/architecture/)
│   │   └── tests/           unit · integration · security · e2e
│   └── oneshot/             OneShot shell (empty placeholder in v6.1)
├── packages/rsm-client/     typed TS client (@oneshot/rsm-client)
├── apps/web/            Next.js UI (App Router)
├── docs/                    architecture / api / decisions / lifecycle / security
├── deploy/                  Dockerfiles · compose production override · deploy.sh (ADR 0018)
├── tools/                   dev · build · verification (4 CI gates)
├── tests/                   cross-app integration + shared fixtures
└── store/                   attachments · buckets · snapshots (runtime data)
```

## Quickstart

```bash
# Backend (uv workspace)
uv sync
uv run --package rsm pytest -q apps/rsm/tests        # expect 339 passed, 1 skipped
uv run python tools/verification/check_boundaries.py
uv run python tools/verification/check_forbidden_deps.py
uv run python tools/verification/check_pymupdf_import.py
uv run python tools/verification/check_no_agent_tools.py

# Daemon
uv run uvicorn rsm.api.app:create_app --factory --host 127.0.0.1 --port 8787

# Local-mode CLI (no daemon required)
uv run rsm --store-root ./store/buckets --attachment-root ./store/attachments \
    --eventlog-path ./store/events.log ingest-local path/to/source.txt
uv run rsm --store-root ./store/buckets --eventlog-path ./store/events.log replay-local <bucket_id>

# Frontend
cd apps/web && pnpm install && pnpm build
```

## Deploy (single host, Docker Compose)

```bash
docker compose up --build -d           # daemon 127.0.0.1:8787, UI 127.0.0.1:3000
curl -fsS http://127.0.0.1:8787/healthz
```

Nothing is published beyond loopback (ADR 0001). Releases are pushed to GHCR
and deployed through the gated workflow (smoke test + automatic rollback):
`.github/workflows/deploy.yml`. Full guide: `docs/deployment.md`.

## Spec

Governing spec: `RSMFInalStructure.txt` (frozen). ADRs under `docs/decisions/`.


## Status (this build)

| Area | State |
|---|---|
| Backend domain (bucket / lifecycle / integrity / provenance / extraction) | **VERIFIED** |
| Classification · execution · replay readiness · replay envelope | **VERIFIED** |
| Normalization · Snapshot · ContextBudget · SummaryProvider interface (V2) | **VERIFIED** |
| HTTP API (`/v1/buckets/*`, `/v1/events/*`, `/v1/prov/*`, `/healthz`) | **VERIFIED** |
| MCP resource transport (`rsm://bucket/<id>`) | **VERIFIED** |
| Transport parity (HTTP · MCP · JSON export · stdout) | **VERIFIED** |
| CI gates (boundaries · forbidden deps · pymupdf · no-agent-tools) | **VERIFIED** |
| Tests | **339 passed, 1 skipped** |
| Frontend code (Next.js App Router + typed client + real pages) | AUTHORED |
| Frontend build (`next build`, Next 16 · Turbopack) | **VERIFIED** (exit 0; `tsc`/`eslint` 0 findings; Playwright suite collects 9 tests) |
| Playwright chat-intake specs A–I | **VERIFIED** (9/9 green against the composed containers) |
| Deploy path (compose · GHCR · gated deploy + rollback) | **VERIFIED locally** (images build + stack serves + fail-closed CORS; ADR 0018, `docs/deployment.md`) · GHCR/deploy job awaiting first runner run |

AC-11 (local-first Next.js UI builds and renders) is **verified on the
current dev host** (standard filesystem): the production `next build` exits 0,
typecheck/lint are clean, and the Playwright suite is green end-to-end against
the composed stack (`docker compose up -d`, see `docs/deployment.md`). The
earlier overlayfs `EIO` blocker applied to the legacy sandbox host only; its
recovery notes remain in `apps/web/HAND_AUTHORED.md`.

