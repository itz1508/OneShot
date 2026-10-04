# features/rsm-rail

V3 RSM right rail — a context control surface, not a workspace (ADR 0013).

Contains:

- `RsmRail.tsx` — the persistent right-side drawer (chevron collapse,
  APG switch for ON/OFF, Snapshot + Representation + Context readouts,
  manual `[Replay]`).
- `ReplayStreamingSurface.tsx` — the ephemeral loading surface that
  appears while a stream is in flight and disappears on
  completion/failure/cancel.
- `rsmInteractionId.ts` — opaque interaction id lifecycle for the UI
  (per-tab; regenerated on reload). RSM authorization is per-interaction,
  so this id is passed to every V3-aware call.

All data is read via `@/lib/rsm-client`. No mock data.
