# RSM — Replay State Memory

**Replay State Memory (RSM)** is a source/context boundary for external
source material: capture → identity → provenance → integrity → bucket →
lifecycle → work classification → execution metadata → replay readiness →
release/replay → stable envelope → agent adapter → external agent.

RSM is **not** an LLM, an agent runtime, a model router, a provider manager,
a vector database, a prompt orchestrator, or a long-term memory system.

## Status (this build)

| Area | State |
|---|---|
| Backend domain (bucket / lifecycle / integrity / provenance / extraction) | **VERIFIED** |
| Classification · execution · replay readiness · replay envelope | **VERIFIED** |
| Normalization · Snapshot · ContextBudget · SummaryProvider interface (V2) | **VERIFIED** |
| HTTP API (`/v1/buckets/*`, `/v1/events/*`, `/v1/prov/*`, `/healthz`) | **VERIFIED** |
| MCP resource transport (`rsm://bucket/<id>`) | **VERIFIED** |
| Transport parity (HTTP · MCP · JSON export · stdout) | **VERIFIED** |
| CI gates (boundaries · forbidden deps · pymupdf) | **VERIFIED** |
| Tests | **308 passed** |
| Frontend code (Next.js App Router + typed client + real pages) | AUTHORED |
| Frontend install / build / Playwright | **PENDING STANDARD-FILESYSTEM VERIFICATION** |

AC-11 (local-first Next.js UI builds and renders) remains **BLOCKED** on this
host (overlayfs returns `EIO` on cross-dir `rename` → `create-next-app`
aborts; `pnpm install` and `npm install` stall during `node_modules`
materialisation). Not a code defect. Dev-host recovery procedure is in
`frontend/web/HAND_AUTHORED.md`.

## Repository layout

```
rsm/
├── backend/
│   ├── src/rsm/
│   │   ├── bucket/          canonical bucket model + schema + serializer + A1 immutability
│   │   ├── lifecycle/       7 states, 8 legal transitions, append-only events
│   │   ├── integrity/       SHA-256 over A1 identity fields (reproducible preimage)
│   │   ├── provenance/      W3C PROV-JSON projection
│   │   ├── extraction/      markdown · text · pasted · stdin · chatgpt_export · pdf · folder · opaque
│   │   ├── loading/         runtime dirs (attachment/ · store/) + attachment staging + zip enumerator
│   │   ├── transports/      canonical payload + HTTP / MCP view adapters + json_export + stdout
│   │   ├── classification/  work classification (independent of lifecycle)
│   │   ├── execution/       execution-state records (independent of lifecycle & content)
│   │   ├── replay/          derived replay readiness + envelope
│   │   ├── api/             FastAPI application + routers
│   │   ├── daemon/          authoritative service + fs store + event log
│   │   ├── mcp_server/      MCP SDK adapter (resources only)
│   │   ├── cli/             thin HTTP client CLI + local-mode subcommands (ingest-local/replay-local/transition-local/events-local)
│   │   └── config/          fail-closed TOML loader
│   └── tools/               CI gates (boundaries, forbidden deps, pymupdf)
├── frontend/web/            Next.js UI (hand-authored on this host; see HAND_AUTHORED.md)
├── docs/                    architecture / API / lifecycle / security / ADRs
└── tests/backend/           unit · integration · security · e2e
```

## Quickstart (on a standard filesystem)

```bash
# Backend
python3.11 -m venv .venv && . .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
pytest -q                       # expect 308 passed
python3 backend/tools/check_boundaries.py
python3 backend/tools/check_forbidden_deps.py
python3 backend/tools/check_pymupdf_import.py

# Daemon
uvicorn rsm.api.app:create_app --factory --host 127.0.0.1 --port 8787

# Local-mode CLI (no daemon required)
#   ingest a single file, folder, or zip into ./store/
rsm --store-root ./store --attachment-root ./attachment \
    --eventlog-path ./store/events.log ingest-local path/to/source.txt

#   replay a stored bucket deterministically to stdout
rsm --store-root ./store --eventlog-path ./store/events.log replay-local <bucket_id>

#   lifecycle transition + event-log tail
rsm --store-root ./store --eventlog-path ./store/events.log transition-local <bucket_id> STAGED
rsm --store-root ./store --eventlog-path ./store/events.log events-local <bucket_id>

# Frontend — see docs/decisions/0005-nextjs-app-router.md and frontend/web/HAND_AUTHORED.md
cd frontend/web && pnpm install && pnpm build
```

## Spec

Governing spec: `RSMFInalStructure.txt` (frozen). ADRs under `docs/decisions/`.
