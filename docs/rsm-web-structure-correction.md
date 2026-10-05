# RSM web builder — structure correction (2025-01)

**Status:** complete this round. Backend unchanged; frontend restructured.

## What drifted

The pre-correction frontend presented RSM as a standalone application with
primary navigation for `/buckets`, `/buckets/[id]`, `/ingest`, `/lifecycle`,
and `/replay`, and used `/` as an RSM dashboard with a hero paste editor. That
matches the `itz1508/test-replay` anti-pattern — RSM-as-application rather
than RSM-as-control-surface.

## What changed

### Removed (standalone-RSM navigation)

```
oneshot/frontend/web/src/app/buckets/           (deleted)
oneshot/frontend/web/src/app/buckets/[id]/      (deleted)
oneshot/frontend/web/src/app/ingest/            (deleted)
oneshot/frontend/web/src/app/lifecycle/         (deleted)
oneshot/frontend/web/src/app/replay/            (deleted)
oneshot/frontend/web/src/features/buckets/      (deleted)
oneshot/frontend/web/src/features/ingestion/    (deleted)
oneshot/frontend/web/src/features/lifecycle/    (deleted)
oneshot/frontend/web/src/features/replay/       (deleted)
```

### Replaced

```
oneshot/frontend/web/src/app/page.tsx           host workspace shell
                                         - "Workspace" area as the hero
                                         - no bucket/ingest/replay links
                                         - "Capture external context" is a
                                           secondary <details> disclosure
                                           and is the only ingestion
                                           affordance from the host
```

### Preserved

```
oneshot/frontend/web/src/app/layout.tsx         mounts <RsmRail /> as a secondary
                                         right rail on every page
oneshot/frontend/web/src/apps/features/rsm/     ON/OFF switch, source selector,
                                         Snapshot/Representation/Context
                                         readouts, manual Replay button,
                                         ephemeral ReplayStreaming surface
oneshot/frontend/web/src/lib/rsm-client.ts      typed fetch wrapper for the real
                                         daemon API
oneshot/frontend/web/src/types/bucket.ts        TS mirrors of the backend contract
```

### Added

```
docs/rsm-web-structure-correction.md    this file
```

The rail also listens for a `rsm:source-updated` window event so the host
workspace's optional "Capture external context" affordance immediately
refreshes the rail's state (no page reload, no client-side store).

## What `/` now communicates without explanation

```
┌──────────────────────────────────────────┬──────────────┐
│ Host application                         │              │
│ Workspace                                │   RSM        │
│                                          │              │
│ (primary user work area)                 │   ON   [ ]   │
│                                          │              │
│ ▸ Capture external context into RSM      │   Context    │
│   (secondary; disclosure)                │   NOT READY  │
│                                          │              │
│                                          │   Replay     │
│                                          │              │
│ daemon: ok (schema 1)                    │              │
└──────────────────────────────────────────┴──────────────┘
```

A reviewer who has never read the spec cannot see `Buckets`, `Ingest`, or
`Replay` as application pages. RSM is clearly a thing the host
application USES.

## Acceptance criteria (§24 of the correction brief)

### Architecture

- [x] RSM is not the primary application shell. — `/` is the host workspace;
      the rail is secondary.
- [x] Main application/workspace remains primary. — host workspace is the
      hero; the rail is a fixed-position aside.
- [x] RSM is a secondary control surface. — mounted via `layout.tsx`,
      scoped to `apps/features/rsm/`.
- [x] No Bucket/Ingest/Replay primary navigation. — those routes are
      deleted; there is no sidebar.
- [x] No second chat. — the workspace area is explicitly a demonstration
      placeholder; no messages, composer, or transcript.
- [x] No RSM dashboard. — no `/rsm` route; no multi-tile RSM home.
- [x] No RSM task/project/workflow UI. — none present.
- [x] No JetBrains-specific implementation. — none present.
- [x] No duplicate RSM backend domain in frontend. — grep finds no
      state manager, no `*Store`, no lifecycle/integrity/provenance/snapshot
      engines in TS.

### Workflow

- [x] User is not required to manually create a Bucket as the normal first
      step. — rail works with whatever Bucket the host attaches; capture
      is a secondary disclosure.
- [x] User is not required to paste content into an RSM workspace. — the
      capture affordance is in the host shell, as a disclosure, and
      explicitly described as a system-boundary entry point.
- [x] User is not required to manage attachments. — no file manager, no
      upload dashboard.
- [x] Replay is an action, not a destination. — triggered from the rail;
      drives the ephemeral stream surface; no `/replay` route.
- [x] Snapshot is backend-derived. — `rsm.snapshot.build_snapshot`
      produces it; the UI only reads it.
- [x] RSM ON/OFF is enforced by backend. — the three new interaction
      endpoints are unconditionally gated (ADR 0009).
- [x] UI consumes actual backend state. — all data goes through
      `@/lib/rsm-client`; no fake arrays.

### Authority

- [x] Backend remains authoritative. — nothing in the backend changed in
      this round.
- [x] Bucket immutability intact. — A1 preserved (unchanged).
- [x] Integrity backend-owned. — `rsm.integrity.sha256` (unchanged).
- [x] Provenance backend-owned. — `rsm.provenance` (unchanged).
- [x] Snapshot generation backend-owned. — `rsm.snapshot.builder`
      (unchanged).
- [x] Replay authorization backend-owned. — `rsm.interaction` +
      `/v1/interactions/.../stream` (unchanged).
- [x] Browser is not a second source of truth. — rail state is derived
      from each API response; no localStorage, no cross-tab sync, no
      store.

### Regression

```
pytest -q tests/backend                            132 passed, 2 skipped
backend/tools/check_boundaries.py                  OK
backend/tools/check_forbidden_deps.py              OK
backend/tools/check_pymupdf_import.py              OK
tsc --noEmit --skipLibCheck                        0 diagnostics
eslint 'src/**/*.{ts,tsx}'                         0 diagnostics
next build --webpack                               success (BUILD_ID written)
```

Browser E2E (Playwright) remains NOT RUN — the Playwright directory is a
placeholder (`tests/frontend/e2e/README.md`), and this sandbox cannot keep
`next start` + `uvicorn` alive across tool calls. Reported honestly as a
coverage gap, not as a PASS.

Routes compiled by `next build` after the correction:

```
Route (app)
┌ ○ /
└ ○ /_not-found
```

The absence of `/buckets`, `/buckets/[id]`, `/ingest`, `/lifecycle`, and
`/replay` from the build output is the primary structural evidence that the
standalone-RSM product model has been removed.
