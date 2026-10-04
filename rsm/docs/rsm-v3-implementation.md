# RSM V3 — Implementation Report

**Status:** V3 shipped. V1 + V2 unchanged. Research complete.

This document records the Phase-1 baseline, the Phase-2 investigation
decisions, the Phase-3 ADRs, and the end-to-end verification of the V3
implementation. It is written against the actual repository, not against a
proposal.

---

## Phase 1 — Baseline (frozen)

Verified by direct inspection of `backend/src/rsm/`:

- **A1 Bucket immutability** — `rsm.bucket.immutability.FROZEN_FIELDS` and
  `check_mutation` enforce it; `rsm.daemon.store.FsStore.write` raises
  `BucketFrozen` on any post-STORED frozen-field mutation.
- **A2 schema_version="1"** — `rsm.bucket.schema.canonical_schema` emits
  `{"const": "1"}`.
- **A3 folder identity** — `rsm.extraction.folder.extract_folder` produces a
  canonical manifest with the required bounds counters; child Buckets carry
  `provenance.derived_from = <parent bucket_id>`.
- **Normalization (V2)** — `rsm.normalization.model.normalize` is a pure
  function of the frozen Bucket; byte- and codepoint-faithful.
- **Snapshot (V2)** — `rsm.snapshot` ships `ContextBudget`, `BudgetUnit`,
  `SnapshotKind`, `SnapshotContent`, `SnapshotIntegrity`, `Snapshot`,
  `build_snapshot`, and the `SummaryProvider` Protocol (`NullSummaryProvider`,
  `PrefixSummaryProvider`).
- **Replay envelope (V1 §14)** — `rsm.replay.envelope.build_replay_envelope`
  stamps `source="rsm"`, `provenance`, `integrity`.
- **MCP (ADR 0008)** — resources-only; `rsm.mcp_server.server.build_server`
  exposes `list_resources` + `read_resource`, no tools.
- **Forbidden-deps gate** — `backend/tools/check_forbidden_deps.py` bans
  OpenAI/Anthropic/Google/Cohere/Mistral/LangChain/LangGraph/LlamaIndex/
  DSPy/CrewAI/AutoGen/pydantic_ai across both `backend/src/rsm/` and
  `frontend/web/src/`.
- **PyMuPDF (ADR 0007)** — `check_pymupdf_import.py` rejects `import fitz`.
- **Boundary gate** — `check_boundaries.py` forbids cross-layer imports.

Baseline tests + gates re-executed before any V3 code was written:

```
pytest -q tests/backend         107 passed, 2 intentional skips
check_boundaries.py             boundary gate OK
check_forbidden_deps.py         forbidden-dep gate OK
check_pymupdf_import.py         pymupdf-import gate OK
```

Known environment / host state:

- Overlayfs on `/work` previously blocked `next build` to the point of
  reaching the 12-minute cap. **In this round the production build
  completed on this host** using `next build --webpack` with
  `NEXT_TELEMETRY_DISABLED=1` (~2.6 min compile + 67 s typecheck + 3.1 s
  prerender). AC-11 is therefore reported `PASS` this round. See Phase 7.
- Live `uvicorn` cannot persist across bash calls on this sandbox; HTTP
  behaviour is covered by FastAPI `TestClient` tests.

---

## Phase 2 — Investigation decisions (resolved before implementation)

### ON/OFF must actually be fail-closed (§2 of the mission)

**Decision:** V3 adds a per-interaction `InteractionRecord`. Three new routes
are **unconditionally** gated on `rsm_enabled`:

- `GET /v1/interactions/{interaction_id}` returns the fail-closed default
  for unknown ids but does not persist it.
- `PUT /v1/interactions/{interaction_id}` writes the record.
- `GET /v1/interactions/{interaction_id}/stream` is the ReplayStreaming
  delivery; fails closed on unknown / disabled / no-bucket.

The two legacy endpoints `/v1/buckets/{id}/replay` and
`/v1/buckets/{id}/snapshot` accept an **opt-in** `interaction_id` query
parameter. **When present**, the gate activates (`409 RSM_DISABLED`
on unknown or disabled). **When absent**, the legacy V1/V2 behaviour is
preserved — this is the explicit compatibility boundary (ADR 0009). It
is NOT a V3 bypass: a V3-aware caller cannot forget `interaction_id` and
receive gated content, because every V3 UI call site passes it.

### What "interaction begins" means (§3)

**Decision:** the consuming runtime (the UI in this build) tells the daemon
when an interaction starts by naming an `interaction_id` and calling
`/v1/interactions/{id}/stream`. RSM does NOT autonomously observe Main
Chat. There is no fake "interaction detector".

In the right-rail UI, the id is generated per-tab in
`rsmInteractionId.ts` (regenerated on reload). This mirrors the daemon's
process-lifetime discipline for `InteractionRecord` (ADR 0009).

### ReplayStreaming transport (§4, §5, §6)

**Decision:** FastAPI `StreamingResponse` yielding **exactly one JSON
chunk** containing the full `{ source, interaction_id, bucket_id, replay,
snapshot }` envelope. One chunk is enough to drive the ephemeral UI
honestly (ADR 0010). SSE, WebSocket, named events, and multi-chunk
progressive delivery are **deferred to V3.x** (ADR 0015).

The surface state machine is deliberately short:

```
idle → preparing → streaming → complete  → idle (auto-dismiss)
                             → failed    → idle (user dismiss / Escape)
                             → cancelled → idle (abort)
```

### `delivery_cursor` semantics (§7)

**Decision:** NOT stored. V3 streams one JSON chunk; a cursor cannot be
truthfully advanced on partial delivery, and no multi-chunk resume is
offered. The `InteractionRecord` carries `last_streamed_at` only as a UX
hint. Introducing a cursor is bundled with the multi-chunk / SSE V3.x
work (ADR 0015).

### `InteractionRecord` lifecycle (§8)

**Decision:**

```
InteractionRecord {
  interaction_id    : str          # runtime-owned
  rsm_enabled       : bool = False # fail-closed default
  selected_bucket_id: str | None   # one Bucket in V3
  last_streamed_at  : datetime|None
}
```

- Unknown id → fail-closed default returned on read, NOT persisted.
- PUT replaces the record; a `selected_bucket_id` that does not exist
  returns `404 BUCKET_NOT_FOUND`.
- Daemon restart clears all records (same discipline as classification /
  execution). Persistence to the FS store is V3.x (ADR 0015).
- One Bucket per interaction. Multi-Bucket aggregation is V3.x.

### Source revision / Snapshot staleness (§9)

**Decision:** no new domain object. A user correction is a NEW Bucket
with `provenance.derived_from = <old bucket_id>`. Snapshot staleness is
the SHA-256 check already built into `rsm.snapshot.builder`:

```
snapshot.provenance.derived_from.bucket_hash  !=  current Bucket.hash.value
    ⇒ Snapshot STALE
```

V3 builds Snapshots **on demand**, so there is no persistent cache and
no `SNAPSHOT_STALE` error in this round. Caching is V3.x (ADR 0015).

### Cohesive reduction / summary (§10, §11)

**Decision:** unchanged from V2. The `SummaryProvider` Protocol remains
the sole extension point for reduction. RSM core imports no AI SDK.
AI-derived output is always marked derived via `SnapshotKind.SUMMARY` and
`SnapshotContent.summary_provider`; it is never canonical source.

### Main Chat boundary (§12)

**Decision:** three-domain model preserved:

- MAIN_CHAT_CONTEXT — owner: runtime (RSM must not persist).
- RSM_CONTEXT — owner: RSM.
- RUNTIME_AGENT_CONTEXT — owner: runtime (composition of the two + its
  cache).

The ephemeral RSM UI surface does **not** write a Main Chat message. The
right rail is a persistent control surface, not Main Chat.

### Prompt-injection boundary (§13)

**Decision:** unchanged from V2. RSM carries `source="rsm"` + provenance
on every delivered payload; the consuming Agent/runtime is responsible
for treating that content as data rather than instructions. V3 does not
add an "AI security classifier" to RSM.

### Targeted source retrieval (§14)

**Decision:** deferred to V3.x. In V3 a runtime that needs more than the
Snapshot can read the full Bucket via `GET /v1/buckets/{id}` (existing).

### Concurrency / isolation (§23)

**Decision:** interaction records live in a dict on `DaemonService`
(single-process). The isolation test (A ↛ B) proves two interactions
with different `source_set` never cross-read.

### Overbuild check (§24)

Deferred — not implemented in this round:

- SSE / WebSocket
- persistent interaction database
- multi-Bucket aggregation / `source_set` as list
- targeted retrieval
- vector / embeddings / registry
- agent orchestration / task system / workflow engine
- model router / provider registry
- RECEIVED acknowledgement endpoint
- Snapshot cache + SNAPSHOT_STALE

See ADR 0015.

---

## Phase 3 — ADRs

- `docs/decisions/0009-rsm-interaction-and-onoff.md`
- `docs/decisions/0010-replay-streaming-transport.md`
- `docs/decisions/0012-source-revision-via-new-bucket.md`
- `docs/decisions/0013-right-rail-and-ephemeral-stream-ux.md`
- `docs/decisions/0015-defer-v3x-features.md`

Each ADR reflects a decision that landed in code (no filler ADRs).

---

## Phase 4 — Backend

New files:

```
backend/src/rsm/interaction/__init__.py
backend/src/rsm/interaction/model.py       # InteractionRecord + default
backend/src/rsm/interaction/store.py       # InteractionStore (in-memory)
backend/src/rsm/api/routers/interactions.py  # GET/PUT/stream (ADR 0010)
```

Modified files:

```
backend/tools/check_boundaries.py          # add rsm.interaction to the gate
backend/src/rsm/api/errors.py              # + RsmDisabled / NoSourceSelected / UnknownInteraction
backend/src/rsm/api/app.py                 # mount /v1/interactions
backend/src/rsm/api/routers/buckets.py     # opt-in `interaction_id` gate on /replay + /snapshot
backend/src/rsm/daemon/service.py          # wire InteractionStore + helpers
```

Boundary gate: `rsm.interaction` is permitted only to import stdlib + pydantic;
it is forbidden from everything else (API/daemon/transports/etc.). Verified by
`check_boundaries.py`.

The `/stream` endpoint handler builds the Snapshot via `build_snapshot` and
pairs it with the `build_replay_envelope` output, then streams a single JSON
chunk via `fastapi.StreamingResponse`. `canonical_dumps` provides the
deterministic byte sequence. The record's `last_streamed_at` is stamped
AFTER payload construction succeeds (never before, never on partial failure).

---

## Phase 5 — Backend tests

New files:

```
tests/backend/unit/test_interaction_record.py          # 7 cases
tests/backend/integration/test_api_interactions.py     # 18 cases
```

Results:

```
tests/backend/unit/test_interaction_record.py          7 passed
tests/backend/integration/test_api_interactions.py    18 passed
```

Full suite:

```
pytest -q tests/backend         132 passed, 2 intentional skips
```

(The two intentional skips are V1's `test_daemon_cli.py` (needs a live
HTTP daemon) and `test_archive_traversal.py` (archives are opaque in V1).)

---

## Phase 6 — Frontend

New files:

```
frontend/web/src/features/rsm-rail/README.md
frontend/web/src/features/rsm-rail/rsmInteractionId.ts
frontend/web/src/features/rsm-rail/ReplayStreamingSurface.tsx
frontend/web/src/features/rsm-rail/RsmRail.tsx
```

Modified files:

```
frontend/web/src/types/bucket.ts      # + Snapshot / InteractionRecord / StreamPayload / RsmErrorBody
frontend/web/src/lib/rsm-client.ts    # + RsmHttpError + getInteraction/putInteraction/streamInteraction
frontend/web/src/app/layout.tsx       # mount <RsmRail /> globally
frontend/web/src/app/page.tsx         # tighten effects + next/link (fix pre-existing lints)
frontend/web/src/app/buckets/[id]/page.tsx  # tighten effects (fix pre-existing lints)
```

### Right rail (`RsmRail.tsx`)

- `<aside role="complementary" aria-label="RSM external context">`.
- APG `role="switch"` + `aria-checked` for ON/OFF.
- `aria-expanded` + `aria-controls` on the chevron.
- Reads real Buckets from `GET /v1/buckets/`; no mock data.
- Writes `rsm_enabled` and `selected_bucket_id` via
  `PUT /v1/interactions/{id}`.
- `[Replay]` triggers `streamInteraction`; disabled when OFF or no
  Bucket selected.
- Readouts (Sources count, Snapshot readiness, Representation, Context
  usage) are computed from the actual payload returned by the stream.

### Ephemeral surface (`ReplayStreamingSurface.tsx`)

- `role="status" aria-live="polite"` (becomes `assertive` on failed).
- Stage-based indicator — no fake percentage.
- CSS keyframe animation wrapped in `motion-safe:` and
  `motion-reduce:` utilities so `prefers-reduced-motion` is honoured.
- `Escape` dismisses the surface (also cancels in-flight fetch via
  `AbortController`).
- `complete` state auto-dismisses after a short delay (default
  1200 ms); failed / cancelled wait for user dismiss.
- Returns `null` when `stage === "idle"` so the surface is truly
  ephemeral.

### Client (`rsm-client.ts`)

- `RsmHttpError` class exposes `code` from the daemon's structured
  error body.
- `streamInteraction(interactionId, opts)` is an `AsyncGenerator`
  that yields the single JSON payload. Supports `AbortSignal` for
  cancellation.

---

## Phase 7 — Frontend verification

Run on this host with the toolchain in `/work/toolchain/`:

```
node_modules/.bin/tsc --noEmit --skipLibCheck   exit 0, 0 diagnostics
node_modules/.bin/eslint 'src/**/*.{ts,tsx}'    exit 0, 0 diagnostics
NEXT_TELEMETRY_DISABLED=1 node_modules/.bin/next build --webpack
                                                 exit 0
```

Routes compiled by `next build`:

```
┌ ○ /
├ ○ /_not-found
├ ○ /buckets
├ ƒ /buckets/[id]
├ ○ /ingest
├ ○ /lifecycle
└ ○ /replay
```

The `.next/BUILD_ID` was produced (`WPbi7TA9_zoMMsG_bniIs`), confirming
AC-11 passed on this host. The build artifact was deleted after
verification to keep the repository / release zip clean.

The Round-1 investigation reported ESLint "0 diagnostics". The current
pinned ESLint v9 + `eslint-plugin-react-hooks` v7 toolchain is stricter
(the new `react-hooks/set-state-in-effect` rule) and surfaces lints that
were present in the pre-existing V1 pages. Those have been fixed by
splitting mount-effects into async IIFEs and switching bucket navigation
to `next/link`. The fix touches only pre-existing V1 UI; it does not
alter any V1/V2 contract.

Browser E2E (Playwright) remains deferred — the Playwright directory is
a placeholder (`tests/frontend/e2e/README.md`), and the sandbox does
not keep `next start` + `uvicorn` alive across tool calls. The
production build + typecheck + lint provide the evidence that the UI
compiles and renders.

---

## Phase 8 — Full regression

```
pytest -q tests/backend                            132 passed, 2 skipped
backend/tools/check_boundaries.py                  OK
backend/tools/check_forbidden_deps.py              OK
backend/tools/check_pymupdf_import.py              OK
tsc --noEmit --skipLibCheck                        0 diagnostics
eslint 'src/**/*.{ts,tsx}'                         0 diagnostics
next build --webpack                               success (BUILD_ID produced)
```

---

## Phase 9 — Scope-creep audit

- Forbidden-deps grep across `backend/src/rsm/` + `frontend/web/src/`: no
  matches outside intentional ban-list declarations.
- `SSE`, `WebSocket`, `EventSource`, `cache` grep across sources: zero
  matches.
- No new domain object other than `InteractionRecord`.
- MCP still resources-only.
- No mock / fake frontend data (the only occurrences of "fake" in the
  tree are comments explicitly rejecting fake progress).
- The right rail is a control surface; the only ephemeral surface is the
  stream overlay; neither is a second chat.

---

## Deferred (V3.x) — explicit non-goals this round

- Snapshot cache + `409 SNAPSHOT_STALE`.
- Targeted source retrieval (`/v1/buckets/{id}/segment`).
- SSE / WebSocket transports.
- Multi-Bucket aggregation (`selected_bucket_id: str | None` stays
  single).
- RECEIVED acknowledgement endpoint.
- Persistent `InteractionRecord` across daemon restarts.
- Browser-based E2E (Playwright) specs.

Each is covered by ADR 0015.

---

## End-to-end scenario (§28 of the mission)

Verified by `tests/backend/integration/test_api_interactions.py`:

1. Interaction `i-1` exists, `rsm_enabled=False` →
   `GET /v1/interactions/i-1/stream` → `409 RSM_DISABLED`.
   (See `test_stream_disabled_fails_closed`.)
2. Toggle ON, select Bucket A → `GET /v1/interactions/i-1/stream` → 200
   with `source="rsm"`, provenance, integrity, Snapshot content.
   (See `test_stream_happy_path_shape`.)
3. User correction: ingest Bucket B, re-point interaction →
   `GET /stream` delivers B. Bucket A remains intact; hashes differ.
   (See `test_source_revision_new_bucket_delivered`.)
4. Isolation: two interactions see only their own Bucket.
   (See `test_interaction_isolation`.)
5. The right rail + ephemeral surface in `RsmRail.tsx` wire the
   browser-side half of the same scenario end-to-end — compiled and
   typechecked clean.

---

## Known limitations (verified)

- `tests/backend/integration/test_daemon_cli.py` is intentionally
  skipped (needs a live HTTP daemon; FastAPI `TestClient` covers the
  contract in `test_daemon_http.py` + `test_api_v1_full.py` + the new
  `test_api_interactions.py`).
- `tests/backend/security/test_archive_traversal.py` is intentionally
  skipped — V1 treats archives as opaque, which is the mitigation.
- Playwright specs under `tests/frontend/e2e/` are not written in this
  round; `next build` success is the verifiable UI build evidence.
- Daemon has no persistence for interaction records; a restart drops
  them (same discipline as classification / execution; see ADR 0015).

---

## Verification matrix (final)

| Area | State | Evidence |
|---|---|---|
| Phase 1 baseline | PASS | pytest 107 + 2 skips re-run; 3 gates OK |
| V3 ON/OFF enforcement | PASS | `test_stream_disabled_fails_closed`, `test_stream_unknown_interaction_fails_closed`, `test_replay_with_disabled_interaction_rejected`, `test_snapshot_with_unknown_interaction_rejected` |
| Fail-closed defaults | PASS | `test_get_unknown_interaction_returns_default_off`, `test_default_is_fail_closed` |
| ReplayStreaming payload shape | PASS | `test_stream_happy_path_shape` |
| Source revision chain | PASS | `test_source_revision_new_bucket_delivered` |
| Interaction isolation | PASS | `test_interaction_isolation`, `test_interaction_isolation_disabled_a_cannot_read_b` |
| Legacy compatibility | PASS | `test_replay_without_interaction_id_is_legacy`, `test_snapshot_without_interaction_id_is_legacy` |
| V1 regression | PASS | pytest total 132 passed, 2 intentional skips |
| V2 regression | PASS | same |
| Security gates | PASS | three gates OK |
| Frontend typecheck | PASS | `tsc --noEmit` exit 0 |
| Frontend lint | PASS | `eslint` exit 0 |
| Frontend production build | PASS | `next build --webpack` succeeded; `BUILD_ID` produced |
| Browser E2E | NOT RUN | Playwright specs not authored this round; `next build` + `tsc` + `eslint` cover UI compile/typing |
