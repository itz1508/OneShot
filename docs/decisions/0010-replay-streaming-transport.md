# ADR 0010 — Replay vs ReplayStreaming; transport = chunked HTTP, one JSON chunk

**Status:** V3. Binding.

## Decision

- **Replay** = the stable envelope `rsm.replay.build_replay_envelope`
  produces (unchanged from V1 §14).
- **ReplayStreaming** = the *delivery mechanism* that transports the
  current Snapshot for an interaction. It is not a new domain object.

V3 implements ReplayStreaming as a **FastAPI `StreamingResponse` that
yields exactly one JSON chunk** containing the complete Snapshot
projection. The response's `Content-Type` is `application/json`.

Why one chunk:

- The Snapshot is a single bounded derived payload (§3–§5 of the
  governing spec). A streaming transport is only *necessary* if the
  deliverable is itself unbounded or produced incrementally. V3's
  Snapshot is neither.
- The user-facing ReplayStreaming experience is defined by the UI
  (ADR 0013) — an ephemeral loading surface that disappears on
  completion. The surface's role is to communicate "we're preparing
  external context", not to render partial content. A single-chunk HTTP
  response is enough to drive that UX honestly.
- Multi-chunk / SSE / WebSocket introduce ordering, acknowledgement, and
  reconnection semantics that V3 cannot honestly guarantee against the
  current one-way delivery model (no RECEIVED hook, no durable cursor).

Explicitly deferred to V3.x:

- Multi-chunk progressive streaming (adds `delivery_cursor` semantics).
- SSE named events.
- WebSocket bidirectional transport.
- RECEIVED acknowledgement endpoint.

## Rationale

A ReplayStream object or event protocol would be speculative abstraction
in V3. Keeping the transport minimal and honest ("chunked HTTP, one JSON
chunk") lets the end-to-end behaviour — ON/OFF, provenance, integrity,
ephemeral UI — be verified without inventing partial-delivery
guarantees RSM cannot keep.

## Consequences

- The browser client reads the stream via `fetch` + `response.json()`;
  no `EventSource` dependency.
- "Stream cancelled" means the HTTP connection closed before the chunk
  was delivered; the daemon records nothing and the UI shows a
  dismissible failed state.
- No `delivery_cursor` is stored on `InteractionRecord`; the record only
  records `last_streamed_at` as a UX hint, never as authorization.
