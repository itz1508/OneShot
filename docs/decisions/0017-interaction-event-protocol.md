# ADR 0017 — Minimal interaction event protocol

**Status:** V3. Binding.

## Context

The §20 "Events and Streaming Audit" asked whether RSM already has a
coherent typed, ordered lifecycle/event protocol across the
Interaction → Source Assessment → Scan → Reader/Vision → Processor →
Prepared Representation → Replay flow.

The repository already carries typed events at every sub-boundary:

- `LifecycleEvent` — append-only bucket state transitions on the
  on-disk `EventLog` (`events.log`), covering RECEIVED → … → RELEASED.
- `ReaderEvent` — per-File observation events in `ReadResult.events`
  (`FILE_OBSERVED` / `FILE_PARTIAL` / `FILE_FAILED` /
  `READER_COMPLETE`), with monotonic 1-based `index` within one
  `read_bucket(...)` call.
- `InteractionRecord` — the §16 authorisation gate; stable identity.
- `PreparedRepresentation` + `Snapshot` + replay envelope — the typed
  domain result the client consumes.

What was missing was a **single ordered view of what happened to one
interaction** across all those sub-boundaries, with:

- a stable per-interaction identity,
- a strictly monotonic sequence,
- a terminal `cancelled` event (§21 cancellation stops further
  unreleased delivery),
- a terminal `failed` event (so a client can tell the structured error
  codes apart from a transient 4xx retry opportunity),
- a non-terminal `completed` event (so the §9/§10 "repeated streams are
  idempotent" contract keeps working),
- NO new transport layer (SSE / WebSocket remain deferred per ADR 0010
  + ADR 0015),
- NO new runtime, manager, bus, or session abstraction.

## Decision

Add `rsm.interaction.events` with one tiny pydantic DTO and a
seven-value enum:

```
InteractionEventKind:
    interaction.created
    interaction.started
    interaction.observed
    interaction.prepared_ready
    interaction.completed
    interaction.cancelled      # terminal, §21
    interaction.failed         # terminal, structured 4xx
```

Attach a per-interaction append-only log to `InteractionStore`
(process-lifetime, same discipline as the record itself). Issue a
strictly monotonic `sequence` per interaction. Emit events
synchronously from inside the existing API router — no background
worker, no fan-out bus. The HTTP contract of `/v1/interactions/{id}/stream`
is **unchanged** (same keys, same error codes); events are a sibling
log read via `GET /v1/interactions/{id}/events`.

### Transport vs event protocol vs domain result (§20 three-layer split)

```
TRANSPORT              chunked HTTP, one JSON chunk          (ADR 0010)
EVENT PROTOCOL         InteractionEvent log on InteractionStore (ADR 0017)
DOMAIN RESULT          PreparedRepresentation                 (ADR 0016)
```

The three layers never duplicate each other's state. The event log
references identities and counts; it never embeds full Source content.

### Terminals

- `cancelled` and `failed` are terminal — `append_event` refuses
  further emissions with `InteractionTerminated`.
- `completed` is **not** terminal. A re-stream appends another
  started/observed/prepared_ready/completed cycle. The existing
  `test_repeated_stream_is_idempotent_in_payload` HTTP contract remains
  honest; the audit log is honest about each stream.

### Cancellation (§21)

New endpoint `POST /v1/interactions/{id}/cancel` appends a terminal
`interaction.cancelled` event, idempotently. It:

- does NOT mutate Source (A1 preserved — frozen by
  `test_cancel_does_not_mutate_source`);
- does NOT flip `rsm_enabled` on the record;
- blocks subsequent `/stream` calls with the usual `409 RSM_DISABLED`
  envelope, now carrying `details.terminal_kind` so the client knows
  cancellation (as opposed to a pre-existing OFF state) is why.

### Ordering guarantees

- `interaction_id` is the stable identity, unchanged from ADR 0009.
- `sequence` is strictly monotonic per interaction, starting at 1.
  Cross-interaction order is NOT guaranteed — there is no global bus,
  by design.
- `at` is UTC wall-clock, carried for debugging only (sequence is the
  authority).

### Non-goals

- No SSE or WebSocket transport. The chunked-HTTP one-chunk delivery
  (ADR 0010) is unchanged; the event log is a read-only sibling,
  consumable with a plain `GET`.
- No OpenAI-compatible Response schema / ResponseItem — events point at
  RSM primitives (`interaction_id`, `bucket_id`, integrity digests).
- No EventManager / SessionManager / ResponseManager / cross-request
  bus.
- No disk persistence. Daemon restart clears the log, same discipline
  as the record itself.
- No LangChain / LangGraph / Strands / OpenAI SDK / MCP Agent runtime
  (enforced by `check_boundaries.py` + `check_forbidden_deps.py`).
- No frontend changes. The event endpoint is a backend observation
  surface; the Right-Rail (ADR 0013) continues to render the single
  ephemeral stream it already renders.

## Verification

- `pytest -q tests/backend` — 270 passed, 2 skipped.
- `python backend/tools/check_boundaries.py` — OK.
- `python backend/tools/check_forbidden_deps.py` — OK.
- `python backend/tools/check_pymupdf_import.py` — OK.

Specific coverage:

- Vocabulary + terminals: `tests/backend/unit/test_interaction_events.py`.
- Full lifecycle on success, idempotent re-stream, failed terminal,
  cancellation, isolation, Prepared-Representation payload left
  intact: `tests/backend/integration/test_api_interaction_events.py`.
