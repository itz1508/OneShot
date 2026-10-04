# ADR 0012 — User corrections produce a new Bucket; no in-place mutation

**Status:** V3. Binding.

## Decision

A user correction of ingested source material is **ingested as a new
Bucket** with `provenance.derived_from = <old_bucket_id>`. The previous
Bucket is never mutated (A1).

```
Bucket A  (STORED, frozen)
   │
   │ user corrects source
   ▼
Bucket B  (STORED, frozen)
   provenance.derived_from = A
```

Snapshot staleness is the SHA-256 identity check already present in
`rsm.snapshot.builder._snapshot_hash` and
`snapshot.provenance.derived_from.bucket_hash`:

```
snapshot.provenance.derived_from.bucket_hash  !=  current Bucket.hash.value
    ⇒ Snapshot STALE
```

V3 **does not cache Snapshots**, so staleness is a forward-looking
invariant: every Snapshot is rebuilt on demand by `build_snapshot`.
Introducing a cache (and a `409 SNAPSHOT_STALE` error) is deferred to
V3.x.

## Rationale

- A1 immutability is the backbone of integrity + provenance. Any
  "in-place edit" pathway violates it.
- Partial / selective rewrite of a Snapshot cannot be guaranteed by any
  deterministic reduction (and certainly not by an LLM). The honest
  guarantee is "new Bucket ⇒ Snapshot is a pure function of the new
  Bucket".
- No new `SourceRevision` domain object: the parent/child chain already
  exists via `provenance.derived_from`.

## Consequences

- `[Replay]` in the UI (ADR 0013) is the user-triggered re-delivery
  button that pushes the current Snapshot of the currently selected
  Bucket; it does not promise "only the changed sentence".
- Clients discover the chain by reading `provenance.derived_from`.
