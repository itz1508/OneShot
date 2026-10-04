# ADR 0009 — RSM interaction scope and ON/OFF authorization

**Status:** V3. Binding.

## Decision

V3 introduces a per-interaction `InteractionRecord` kept in memory on
`DaemonService`, same discipline as classification and execution records
(V1 §9, §10). It is the authoritative delivery gate.

```
InteractionRecord (in-memory, keyed by interaction_id)
  interaction_id    : opaque string, runtime-owned
  rsm_enabled       : bool          (default false — fail closed)
  selected_bucket_id: str | None    (V3: at most one Bucket)
  last_streamed_at  : datetime | None
```

Every V3 interaction-aware delivery path enforces the gate:

- `GET /v1/interactions/{id}` — read record (creates default record
  implicitly as the response if unknown; **does not** persist on read).
- `PUT /v1/interactions/{id}` — set `rsm_enabled` and/or
  `selected_bucket_id`; persists.
- `GET /v1/interactions/{id}/stream` — ReplayStreaming of the current
  Snapshot for the interaction's selected Bucket. **Fails closed** when
  the record is unknown, when `rsm_enabled` is false, or when no Bucket
  is selected.

Legacy `/replay` and `/snapshot` endpoints accept an optional
`interaction_id` query parameter. When supplied they **enforce** the same
gate (`409 RSM_DISABLED` if disabled or unknown). When **absent** they
behave exactly as in V2 (no gate). This explicit compatibility boundary
is documented in `docs/rsm-v3-implementation.md`; new UI clients MUST
pass `interaction_id`.

## Rationale

- "Fail-closed" is the mission's non-negotiable: an unknown or disabled
  interaction MUST NOT release Bucket content. The three new paths are
  gated unconditionally.
- V1/V2 callers never used the interaction concept, so adding a hard
  requirement would break the existing test suite without benefit. The
  gate activates **when the caller opts in** by naming an
  `interaction_id`. There is no silent V3 bypass — a V3-aware caller
  cannot "forget" to send the id and get content.
- No persistence requirement: a daemon restart clears records (same as
  classification / execution), which is a safer default than a stored
  authorization leaking across restarts.

## Scope / non-goals

- **One Bucket per interaction in V3.** Multi-Bucket aggregation is
  deferred to V3.x. Keeping the field as `selected_bucket_id: str | None`
  rather than a list reflects that explicitly.
- No `delivery_cursor` field. V3 streams one JSON chunk — a cursor
  cannot be truthfully advanced on partial delivery (ADR 0010).
