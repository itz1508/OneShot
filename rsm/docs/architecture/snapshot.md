# Snapshot — bounded derived representation (V2)

**Scope:** Snapshot is a bounded, derived projection of a Bucket's normalized
source for delivery to a consuming Agent. It is NOT a task-management system
and NOT an agent orchestration platform.

```
External Source
    ↓ ingestion
Bucket (A1 frozen)
    ↓ normalization  (rsm.normalization — deterministic view, no rewrite)
NormalizedSource
    ↓ build_snapshot (rsm.snapshot — budget-aware)
Snapshot (preserved OR summary)
    ↓ replay / HTTP
Agent
```

## Strict separation (spec §2)

| Concept | Owner | Rule |
|---|---|---|
| Source | `rsm.extraction` | Original material. Immutable (A1). |
| Normalization | `rsm.normalization` | Deterministic structural view. **No summarisation, no reinterpretation, no LLM.** |
| Snapshot | `rsm.snapshot` | Bounded; records included/reduced/omitted sources. Own identity and integrity. |
| Summary | `SummaryProvider` plug-in | External adapter. Marked derived. Never claims to be original. |
| Replay | `rsm.replay` + API | Delivers the Snapshot projection. Never mutates the Bucket. |

## Context Budget (spec §4)

```
ContextBudget {
  unit:          bytes | characters | tokens_estimate
  value:         int >= 1
  is_hard_limit: bool  (default true)
}
```

`tokens_estimate` is a deterministic heuristic: `ceil(chars / 4)`. It is
**never** reported as an exact model token count.

## Reduction (spec §5)

```
normalized source fits  ─▶ preserved
normalized source overflows + no provider ─▶ SummaryUnavailable (409)
normalized source overflows + provider    ─▶ summary (SnapshotKind=SUMMARY)
```

The builder rejects a provider that returns text exceeding the declared
budget — `SnapshotBuildError`. No silent truncation.

## Summary Provider interface (spec §6)

```python
class SummaryProvider(Protocol):
    name: str
    def summarize(self, *, text: str, budget_bytes: int, budget_chars: int) -> str: ...
```

Shipped with RSM core:

- `NullSummaryProvider` — explicit no-op; raises `SummaryUnavailable`.
- `PrefixSummaryProvider` — deterministic, LLM-free. Returns a bounded
  excerpt plus a `[TRUNCATED BY RSM PrefixSummaryProvider]` marker so the
  result is never mistaken for original source.

Real LLM summarisation lives OUTSIDE RSM core (spec §6). No OpenAI/Anthropic/
LangChain/agent SDK is imported anywhere in `rsm.*`.

## Integrity (spec §10)

- The Bucket's `hash.value` is UNAFFECTED by Snapshot derivation.
- Snapshot has its own `integrity.value` — SHA-256 over canonical bytes of
  the Snapshot projection (excluding the integrity field itself).

## Provenance (spec §9)

Every Snapshot records:

```json
"provenance": {
  "derived_from": {
    "kind": "rsm_bucket",
    "bucket_id": "bkt_…",
    "bucket_hash": "<sha256>"
  },
  "produced_at": "<ISO-8601Z>"
}
```

## HTTP (spec §13)

Single new endpoint:

```
GET /v1/buckets/{id}/snapshot
    ?budget_unit=characters|bytes|tokens_estimate   (default: characters)
    &budget_value=<int≥1>                           (default: 2000)
    &reduce=null|prefix                             (default: null)
```

Response: the Snapshot JSON.

Errors:
- `404 BUCKET_NOT_FOUND`
- `409 SUMMARY_UNAVAILABLE` — source overflows and `reduce=null`
- `422 INVALID_BUDGET`
- `422 SNAPSHOT_BUILD_FAILED` — provider returned over-budget text
