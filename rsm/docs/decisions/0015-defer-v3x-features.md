# ADR 0015 — V3.x deferrals: Snapshot cache, targeted retrieval, SSE, multi-Bucket, RECEIVED ack

**Status:** V3. Binding.

## Deferred to V3.x

The following were considered and NOT shipped in V3:

- **Persistent Snapshot cache** and the matching `409 SNAPSHOT_STALE`
  error. V3 builds Snapshots on demand; staleness is a pure-function
  invariant without a cache (ADR 0012).
- **Targeted source retrieval** (`GET /v1/buckets/{id}/segment`). The
  Agent/runtime can read the full Bucket today via
  `GET /v1/buckets/{id}`. A deterministic segment selector is a
  future capability; V3 does not add it.
- **Server-Sent Events (SSE)** and WebSocket transports for
  ReplayStreaming. V3 ships chunked HTTP, one JSON chunk (ADR 0010).
- **Multi-Bucket aggregation.** `InteractionRecord.selected_bucket_id`
  is a single id in V3 (ADR 0009); aggregating a set of Buckets into
  one Snapshot is a V3.x capability.
- **RECEIVED acknowledgement.** V3 reports DELIVERED only (the HTTP
  response completed). A separate ack endpoint for the runtime is
  future work.
- **Persisting `InteractionRecord` across daemon restarts.** V3 keeps
  interaction records in memory, same discipline as classification and
  execution (V1 §9, §10).

## Rationale

Each deferred capability either adds state RSM cannot honestly
guarantee at this transport layer or expands the API surface beyond
what the end-to-end V3 scenario (§28) requires. Keeping V3 small is
explicit in the mission.
