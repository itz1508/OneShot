# RSM V3 — External Source, ReplayStreaming, and the ON = Participation Correction (Investigation, Round 2)

**Scope:** research and architecture only. No V3 production code is written in
this round. V1 + V2 remain frozen and unchanged.

**Status of this file:** this document **replaces** the Round 1 V3
investigation that previously occupied this path. Round 1 proposed
`ON = permission` and `[Replay] = explicit action`; that model is **superseded**
below (§5, §11). The parts of Round 1 that remain correct — existing
architecture inventory, security findings against the current code, prohibition
of AI/LLM/agent SDKs in `rsm.*`, the Bucket-vs-attachment direction — are
retained as findings of this round after re-verification against the actual
repository.

**Baseline (anchored before and after this document was authored):**

- `pytest -q tests/backend` → **107 passed, 2 intentional skips**
- `backend/tools/check_boundaries.py` · `check_forbidden_deps.py` ·
  `check_pymupdf_import.py` → all **OK**
- No production source files were modified during this investigation.

**Legend** used throughout:

- **FACT** — observed in this repository or in a cited primary source.
- **RESEARCH FINDING** — inferred from reading primary documentation.
- **RECOMMENDATION** — a proposed design decision for V3.
- **OPEN QUESTION** — explicitly unresolved; must not be assumed.

---

## 0. What changed from Round 1

| Round 1 claim (SUPERSEDED) | Round 2 correction (THIS DOCUMENT) |
|---|---|
| `ON = replay authorization only` | `ON = participation: RSM automatically supplies eligible prepared external context into the current interaction via ReplayStreaming when the interaction begins.` |
| `[Replay]` is the *only* way RSM content reaches the Agent (explicit action, once per release). | `[Replay]` is the *re-replay / refresh / retry* lever — used after a source edit, after an explicit user request, or when the previously delivered Snapshot is stale. Initial delivery happens automatically under ON. |
| Interaction state carries three fields including `selected_snapshot_id`. | Interaction state carries ON/OFF, selected `source_set` (one or more Buckets), and the current `delivery_cursor` identifying what has already been streamed. `selected_snapshot_id` is **not** a required field — Snapshots are derived on demand from the Bucket set + budget. |
| Snapshot is a one-shot payload. | Snapshot is still the bounded delivery unit; **ReplayStreaming** is the delivery mechanism that progressively transfers that unit (and any revision deltas) to the consuming runtime without claiming the Agent has processed it. |
| Right rail is a permission + action control. | Right rail is a *context control surface* that reflects: Sources, Reduction (preserved / reduced / stale), Context budget usage, ON/OFF, and the manual `[Replay]` lever. Still not a workspace. |

The §22 question set, the state model (§23), the security model (§24), and the
scope separation (§27) all follow from this correction.

---

## 1. Baseline inspection — V1 + V2 FROZEN

Observed by direct inspection of `backend/src/rsm/`. These findings are
unchanged from Round 1; re-verified for Round 2.

| Package | Role (FACT) |
|---|---|
| `rsm.bucket` | Pydantic canonical bucket, `canonical_schema()`, deterministic `canonical_dumps`, A1 immutability (`FROZEN_FIELDS`, `check_mutation`). |
| `rsm.lifecycle` | 7-state `StrEnum`, 8 legal directed edges, append-only events. |
| `rsm.integrity` | SHA-256 over the A1 identity fields via `canonical_preimage`. |
| `rsm.provenance` | W3C PROV-JSON projection (`https://www.w3.org/TR/prov-json/`). |
| `rsm.extraction` | markdown · text · pasted · stdin · chatgpt_export · pdf · folder · opaque. |
| `rsm.normalization` (V2) | `NormalizedSource` + `normalize(bucket)`: deterministic view, no reinterpretation. |
| `rsm.snapshot` (V2) | `ContextBudget`, `BudgetUnit`, `SnapshotContent`, `SnapshotKind`, `SnapshotIntegrity`, `Snapshot`, `build_snapshot`, `SummaryProvider` Protocol with `NullSummaryProvider` and `PrefixSummaryProvider`. |
| `rsm.classification` | `WorkClassification` (`STORE | REVIEW | REVIEW_TODO | READY_EXECUTION`) — independent of lifecycle. |
| `rsm.execution` | Execution state keyed by `bucket_id` — independent of lifecycle. |
| `rsm.replay` | `derive_replayability(state, classification)` + `build_replay_envelope`. |
| `rsm.transports` | `canonical.build_payload` + HTTP/MCP view adapters + `json_export` + `stdout`. |
| `rsm.api` | FastAPI app + routers (`buckets`, `events`, `prov`); `errors.py` structured codes. |
| `rsm.daemon` | Service, FS store, append-only event log; in-memory classification/execution. |
| `rsm.mcp_server` | MCP SDK adapter; resources only (ADR 0008). |
| `rsm.cli` | Thin HTTP client. |
| `rsm.config` | Fail-closed TOML loader (stdlib `tomllib` + Pydantic `extra="forbid"`). |

CI gates (`backend/tools/`): `check_boundaries.py` forbids cross-layer imports;
`check_forbidden_deps.py` forbids every AI/LLM/agent SDK (openai, anthropic,
google.generativeai, cohere, mistralai, langchain, langgraph, llama_index,
dspy, crewai, autogen, pydantic_ai, …); `check_pymupdf_import.py` enforces
`import pymupdf` (ADR 0007).

**V3 does not alter any of the above.** It adds new, side-by-side primitives
and new routes; no existing field, enum, or import graph is changed.

---

## 2. Reframe — what RSM actually is

**RSM is an external-context preparation and delivery layer.** It is not a
memory store (RSM core does not persist Agent output, does not persist Main
Chat messages, and does not promote Agent output into canonical source), not
an agent runtime, and not a workflow engine. Its job is:

```
EXTERNAL SOURCE
      ↓ ingestion                     (rsm.extraction — byte-faithful)
BUCKET                                 (A1-frozen identity; §1 preserved)
      ↓ normalization                 (rsm.normalization — deterministic view)
NORMALIZEDSOURCE
      ↓ build_snapshot(budget, …)     (rsm.snapshot — bounded; preserved OR summary)
SNAPSHOT
      ↓ ReplayStreaming               (NEW IN V3 — delivery, not transformation)
CONSUMING RUNTIME
      ↓ context composition           (runtime's job — RSM never composes AgentContext)
AGENT
```

Three invariants (RESEARCH FINDING, carried from the spec and verified
against the code):

- **Source ≠ Summary.** The authoritative Bucket is immutable under A1
  (`rsm.bucket.immutability.FROZEN_FIELDS`); any derived representation is
  marked and provenance-linked. V3 strengthens this with explicit source
  revisioning (§8–§9) and stronger stale-detection semantics (§12).
- **Summary ≠ Agent understanding.** RSM reports *delivery*; it never asserts
  the Agent read, interpreted, or acted on the content (§13).
- **RSM ≠ Agent.** The runtime composes `AgentContext`; RSM provides a tagged
  `RSM_CONTEXT` block (`"source": "rsm"`, provenance, integrity) that the
  runtime integrates (§13, §20 of Round 1 preserved; see §24 security).

---

## 3. The v1/v2/v3 example is illustrative only

The user's prompt mentioned a `[ ] v1 / [ ] v2 / [ ] v3` list as a trigger
example. **It is not a required RSM structure.** RSM must accept, with the
same primitives, any of:

- a pasted sentence
- a webpage (HTML, Markdown, article)
- a PDF
- a `.txt` / `.md` file
- a research collection (folder, zip left opaque per V1)
- an architecture document
- a ChatGPT export
- an attachment from the host runtime

and reduce them when necessary without introducing new concepts like
`task`, `stage`, `project`, `workflow`, `planning`, `execution`, or
`version-tracked requirement list`. The existing `Bucket` + `NormalizedSource`
+ `Snapshot` triad is sufficient and MUST remain the whole domain (§18).

---

## 4. The core problem, directly stated

> A user hands the Main Agent a large external source (webpage, document,
> research collection). The Agent typically does not read it exhaustively; it
> latches onto the immediate user instruction and the salient keywords.

**What a dedicated external-context layer can offer:**

- Preserve the authoritative source so nothing is lost or silently truncated.
- Normalize once, deterministically.
- Produce a **cohesive bounded representation** fitting a declared budget.
- Deliver that representation into the interaction automatically when RSM is
  ON, with provenance and integrity attached.
- Allow re-replay when the source is edited, and (in a future V3.x) targeted
  retrieval of segments the Agent discovers it still needs.

**What it must not promise:**

- That the Agent "understood" the source.
- That the summary is equivalent to the source.
- That summarisation preserves every claim or constraint in a way an Agent
  cannot miss.
- That one source change rewrites only one sentence of the summary — a single
  edit may legitimately change the whole cohesive representation (§8).

---

## 5. ON/OFF semantics — CORRECTED

> **RSM ON** — RSM is an active participant in the current interaction's
> external-context feed. When the interaction begins, RSM automatically
> streams eligible prepared context (the current Snapshot of the selected
> source set) into the consuming runtime via **ReplayStreaming**.
>
> **RSM OFF** — RSM MUST NOT release any Bucket, Snapshot, or Replay payload
> into the current interaction, regardless of readiness. Nothing is streamed
> on interaction start.

**Where the flag lives (RECOMMENDATION):**

The authoritative value is **per-interaction**, keyed by an opaque
`interaction_id` supplied by the runtime (same discipline as `classification`
and `execution` records in V1/V2: in-memory on `DaemonService`; the UI mirrors
it; API carries it; daemon enforces it).

```
InteractionRecord (V3 proposed, in-memory):
  interaction_id   : string                 # runtime-owned
  rsm_enabled      : bool                   # default FALSE (fail closed)
  source_set       : list[bucket_id]        # which Buckets participate
  delivery_cursor  : opaque                 # last streamed Snapshot integrity
  last_streamed_at : datetime | null
```

**Why `source_set` is a list, not a single bucket:**

A user may pin a research collection (folder → one parent Bucket + many child
Buckets via A3). V3 **still delivers only one Snapshot per interaction**
(multi-Bucket aggregation remains deferred — §27). The list captures
intent-of-inclusion; the Snapshot builder reduces across the authoritative
subset the user chose. In V3 the list may have length 1 (default); length > 1
is a V3.x capability (§27).

**Mandatory fail-closed behaviours (RECOMMENDATION):**

- Unknown `interaction_id` ⇒ default record ⇒ ReplayStreaming blocked.
- `rsm_enabled: false` ⇒ `409 RSM_DISABLED` on `/replay`, `/snapshot`, and the
  new `/stream` endpoint (§19).
- Flipping to ON mid-conversation ⇒ next interaction turn triggers a one-shot
  stream from `delivery_cursor = null` (effectively "start now").
- Flipping to OFF during an active stream ⇒ server-side cancel of the stream;
  already-delivered chunks remain with the runtime (RSM cannot un-send).

**What is *not* changing:** V1 §15 remains binding — user Main-Chat messages
are never auto-ingested into Buckets, and Agent output is never promoted into
canonical source. ON authorises *outbound* participation only.

---

## 6. Source vs derived representation — formal definitions

| Concept | Owner | Mutable? | Identity |
|---|---|---|---|
| **Source** | `rsm.extraction` → `Bucket` | A1-frozen after STORED | `bucket_id` + `hash.value` |
| **NormalizedSource** | `rsm.normalization` | pure function of the frozen Bucket | reconstructed on demand |
| **Snapshot** | `rsm.snapshot.build_snapshot` | derived; non-authoritative | `snapshot_id` + its own `integrity.value` |
| **Replay payload** | `rsm.replay.build_replay_envelope` | derived, read-only wrapper | `source="rsm"` + Bucket provenance |
| **ReplayStream** | V3 proposed | ordered sequence of Snapshot deltas | integrity per delta + cumulative cursor |

**Rule (RECOMMENDATION):** the authoritative Bucket is always recoverable in
full from RSM (`GET /v1/buckets/{id}` and `GET /v1/buckets/{id}/export` already
guarantee this — FACT). Snapshots and ReplayStreams are bounded delivery
projections and must never be mistaken for the source. The
`PrefixSummaryProvider` already enforces this with an explicit
`[TRUNCATED BY RSM PrefixSummaryProvider]` marker; this discipline extends to
every future provider plug-in.

---

## 7. Cohesive reduction vs keyword extraction

A large webpage/document carries headings, prose, tables, code, definitions,
constraints, relationships, conclusions, caveats, examples, and references.
"Reduce" cannot mean "extract keywords"; that would drop the structure the
Agent is trying to reason over.

**What RSM should mean by "reduce the source" (RECOMMENDATION):**

A **bounded cohesive representation** that, within its declared
`ContextBudget`, preserves — in the order and relative weight of the original —
whichever of the following are present:

- major claims and conclusions,
- definitions and the terms they define,
- stated constraints,
- cross-references and relationships that the surrounding prose makes
  explicit,
- the source's own structural scaffolding (section headings, enumeration),
- caveats, uncertainty markers, and dates where present,
- enough examples to disambiguate the definitions,
- integrity + provenance pointers so the Agent can request more if needed.

**What RSM must not do:**

- Rewrite claims into stronger forms (e.g. "may" → "will").
- Invent coverage of a topic the source does not discuss.
- Drop caveats to save budget.
- Reorder for salience in ways that destroy the original argument structure.

**Interface, not template (RECOMMENDATION):**

RSM core already defines a `SummaryProvider` Protocol — any process (local AI,
host AI, deterministic bounded excerpt, external adapter) that implements
`summarize(text, budget_bytes, budget_chars) -> str` and returns within budget
is acceptable. The provider identifies itself via `.name`, which is recorded
on the Snapshot content (`SnapshotContent.summary_provider`), so the audit
trail is already in place. RSM does **not** enforce a fixed template; it
enforces the budget, the derivation marker, and the provenance.

**Deterministic fallback (FACT):** `PrefixSummaryProvider` is shipped with
RSM core, imports no AI SDK, and produces a bounded excerpt plus a marker. It
is honest about what it is — a prefix, not a cohesive summary — and callers
that need true cohesion must plug an external provider.

---

## 8. Source revision and user corrections — the small-edit problem

Scenario: user ingests a 50 KB document. RSM builds Snapshot A. The user
corrects one sentence.

**What RSM MUST NOT promise:** "only the changed sentence is re-summarised".
A single sentence can change the meaning of the whole document, and any claim
to selective rewrite is a correctness hazard.

**What RSM SHOULD do (RECOMMENDATION):**

Minimise *unnecessary* recomputation while preserving coherence and
correctness of the derived representation:

1. The authoritative Bucket is **A1-frozen after STORED**. A user correction
   is therefore an *ingestion* of a new Bucket, not a mutation of the old
   one. The new Bucket's `provenance.derived_from` points back to the
   previous Bucket's `bucket_id` (same mechanism V1 already uses for A3
   folder children).
2. The new Bucket's `hash.value` is different; `derive_replayability` and
   `build_snapshot` operate on the new Bucket.
3. The old Snapshot (if cached) is **stale by definition** —
   `snapshot.provenance.derived_from.bucket_hash` no longer matches the
   current Bucket.hash (FACT: `rsm.snapshot.builder._snapshot_hash` already
   embeds this link).
4. Rebuilding is a pure function of the new Bucket + budget + provider.
   Nothing claims the derivation was partial.

**Why this is enough (RESEARCH FINDING):**

Content-addressed derivation (new Bucket → new hash → stale indicator → clean
rebuild) is the W3C PROV discipline and the same discipline RSM already
applies to lifecycle vs identity. It avoids the correctness landmine of
"edit-level diffing" of summaries, which no deterministic provider can
guarantee against a general LLM reduction. Any future partial-recompute
optimisation lives *inside* a provider implementation, not in the RSM core
contract.

**No new `SourceRevision` domain object is required for V3** (§18, §20).
The existing `provenance.derived_from` + per-Bucket `hash` already models
the parent/child chain; the `delivery_cursor` on the interaction record
distinguishes delivered from undelivered revisions.

---

## 9. Can derived representations be recomputed without rewriting the source?

**YES, and the current code already does this (FACT):**

- `rsm.integrity.sha256.canonical_preimage` excludes `state`, `lifecycle.*`,
  `integrity_status`, `optional_summary` from the identity hash
  (`test_integrity_stable_across_lifecycle.py`). A lifecycle transition does
  not alter the Bucket hash.
- `rsm.snapshot.build_snapshot` is a pure function of the frozen Bucket;
  rebuilding never writes to the Bucket.
- `rsm.replay.build_replay_envelope` is read-only.

So every Snapshot and every Replay can be re-derived from the current Bucket
without ever rewriting the authoritative source. V3 preserves this invariant.

---

## 10. Targeted source retrieval — when needed, and when

A Snapshot may legitimately omit material (`omitted_sources` on the Snapshot,
FACT). The Agent may discover during reasoning that it needs more. The
pattern:

```
Snapshot delivered
      ↓
Agent determines missing information
      ↓
Agent/runtime requests a targeted source segment
      ↓
RSM returns authoritative source segment (bounded)
```

**When this should ship (RECOMMENDATION):**

- **NOT V3.** V3 proves the ON=participation + ReplayStreaming model.
- **V3.x** — add `GET /v1/buckets/{id}/segment?offset=&length=` or a
  JSON-path-style targeted selector, with a per-request integrity envelope
  and provenance pointer. This is still read-only.
- **V4 / future architecture** — richer selectors (semantic region, section
  heading, byte range in the original pre-normalised blob) with recorded
  provenance of which segment satisfied which Agent request.

**Why defer:** targeted retrieval introduces a request/response pattern
between Agent and RSM that is strictly larger than ReplayStreaming's
one-way "we delivered X" guarantee. Validating the one-way model first keeps
the V3 security story simple (§24).

---

## 11. Does manual `[Replay]` remain necessary? YES — redefined

Round 1 modelled Replay as *the* delivery action. Round 2 redefines it as a
user-triggered **re-replay / refresh / retry** lever:

- "I just edited the source — redeliver." (`delivery_cursor` is stale.)
- "I want to re-send the current Snapshot into the Agent's context now, even
  though RSM already streamed it at interaction start."
- "Last stream failed; retry."
- "I added a Bucket to the source set — resend."

**Mechanism (RECOMMENDATION):**

Clicking `[Replay]` resets `delivery_cursor = null` for the current
interaction and triggers a fresh ReplayStream from the current Snapshot. It
does NOT bypass ON/OFF (OFF ⇒ still refused with `409 RSM_DISABLED`). It does
NOT mutate the Bucket.

**What `[Replay]` is NOT:**

- Not an admission gate (ON/OFF is the gate).
- Not a Bucket mutator (A1 preserved).
- Not a mechanism to retroactively alter a prior Agent turn.

---

## 12. Snapshot staleness

**Rule (RECOMMENDATION):**

```
snapshot.provenance.derived_from.bucket_hash  !=  current Bucket.hash
    ⇒ Snapshot STALE
```

(FACT: the builder already records `bucket_hash` inside the Snapshot's
`provenance.derived_from`.)

V2/V3 currently build Snapshots on demand, so staleness is a *forward* rule
for any future cache. If V3.x caches Snapshots, the cache lookup must
compare these hashes before returning; a mismatch forces a rebuild.

**UI behaviour (RECOMMENDATION):** the right rail shows "Stale — refresh" and
offers `[Replay]`; the `/stream` endpoint, if a cache ever answers it with
stale data, must either rebuild or return `409 SNAPSHOT_STALE`. V3 does not
cache, so the enforcement is a forward safeguard.

**Rebuild vs block vs warn:** policy question deferred to V3.x; the daemon
*could* implement any of the three without changing the Bucket model.

---

## 13. What RSM knows about delivery — four states, not one

The following four facts are different, and RSM must not conflate them:

| State | What it means | Who owns it |
|---|---|---|
| **DELIVERED** | RSM transmitted the Snapshot (bytes left the daemon). | RSM — recorded by `delivery_cursor` + `last_streamed_at`. |
| **RECEIVED** | The runtime's HTTP/MCP layer parsed and acknowledged the stream. | Runtime (optional ack hook; §19). |
| **PROCESSED** | The runtime included the payload in a specific Agent turn's context composition. | Runtime. Not visible to RSM. |
| **UNDERSTOOD** | The Agent reasoned over the content. | Agent. Never knowable by RSM; never claimed by RSM. |

**V3 commits only to DELIVERED.** It MAY accept a RECEIVED ack from the
runtime (helpful for retry semantics on `[Replay]`); PROCESSED and
UNDERSTOOD remain outside RSM's surface.

---

## 14. Runtime responsibilities

The consuming runtime owns:

- Composing `AgentContext = MainChatContext + RSM_CONTEXT + RuntimeCache`
  (and tagging each block so the Agent can tell them apart).
- Deciding when to inject the stream into the model call.
- Enforcing its own context-window budget (RSM only knows the Snapshot
  budget it was asked for; the runtime subtracts system/user/tool overhead
  before asking).
- Caching Agent output.
- Deciding whether to send a RECEIVED ack back.

RSM owns:

- Preserving source (A1).
- Deterministic normalization.
- Bounded Snapshot derivation (`SummaryProvider`-pluggable, LLM-free core).
- ReplayStreaming delivery (NEW) + Replay envelope (existing).
- Provenance + integrity on every payload.
- ON/OFF enforcement + interaction-scoped cursor.
- Explicit refusal when disabled (`409 RSM_DISABLED`).

---

## 15. Enabling RSM after an interaction has already started

**Behaviour (RECOMMENDATION):** the next turn initiates a ReplayStream from
`delivery_cursor = null`. The Agent sees that turn's context augmented with
the current Snapshot; prior turns are not retroactively augmented (nothing
can rewrite history — this is a runtime invariant RSM MUST NOT breach).

**UI (RECOMMENDATION):** toggling the ON switch mid-conversation flashes a
"RSM will join on your next message" notice; the switch becomes immediately
authoritative server-side, so the following `/stream` request succeeds.

---

## 16. Disabling RSM during an active run

**Behaviour (RECOMMENDATION):**

- The daemon flags `rsm_enabled: false` immediately.
- Any in-flight `/stream` response is cancelled (connection closed).
- Already-delivered chunks remain with the runtime; RSM cannot un-send and
  must not pretend to (§13).
- Subsequent `/replay`, `/snapshot`, `/stream` calls return
  `409 RSM_DISABLED`.
- The runtime decides whether to continue the Agent turn with what it has;
  that is a runtime policy question.

---

## 17. Agent needs information omitted from the Snapshot

**Short-term (V3):** the Agent (or the runtime on its behalf) requests the
full Bucket via the existing `GET /v1/buckets/{id}` — but *within* the
Agent's own context budget, this is often infeasible. The runtime decides.

**Medium-term (V3.x / V4):** targeted source retrieval (§10).

**Non-goal (V3):** letting the Agent *demand* a different reduction. The
budget is the runtime's parameter, not the Agent's.

---

## 18. ReplayStreaming — transport decision

**Does it need a new transport? (RESEARCH FINDING):** depends on how large
"progressive delivery" needs to be in V3.

Two credible options:

| Option | Characteristics | Compatible with current stack |
|---|---|---|
| **A. Chunked HTTP response** | Standard chunked transfer; the response is one JSON array of chunks (or NDJSON). Natively supported by FastAPI (`StreamingResponse`) and `fetch`/`AbortController` on the frontend. | **YES** — no new dependency. |
| **B. SSE (`text/event-stream`)** | Named events, auto-reconnect. FastAPI supports it via `StreamingResponse` with the right media type; browsers via `EventSource`. | **YES** — no new dependency; browser `EventSource` lacks custom headers (would need `X-RSM-Interaction` via query parameter). |
| **C. WebSocket** | Bidirectional. Overkill for one-way delivery; FastAPI supports it but it introduces a second transport topology. | not recommended. |

**Recommendation:** start with **Option A (chunked HTTP)** — it is the
smallest surface change, keeps the current one-way delivery story, and
doesn't force the frontend into `EventSource` constraints. SSE is a
reasonable V3.x evolution if runtimes ask for named events or heartbeats.

**MCP (ADR 0008):** the MCP transport remains resources-only. ReplayStream
is an HTTP-only concern in V3; MCP consumers continue to see Buckets as
resources.

---

## 19. Minimum new API surface

V3 adds **three** endpoints and **two** error codes. Existing endpoints
grow one required parameter (`interaction_id`).

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/interactions/{interaction_id}` | Read the interaction record. |
| PUT | `/v1/interactions/{interaction_id}` | Set `rsm_enabled`, `source_set`. |
| GET | `/v1/interactions/{interaction_id}/stream` | ReplayStream (chunked HTTP) of the current Snapshot for the interaction's `source_set`. 409 if disabled; 404 if no source_set. |

Existing endpoints — `GET /v1/buckets/{id}/replay` and
`GET /v1/buckets/{id}/snapshot` — accept an `interaction_id` (header
`X-RSM-Interaction` or query parameter) and return `409 RSM_DISABLED` when
the stored record says `rsm_enabled: false`. They continue to work without
an `interaction_id` for V1/V2 callers who do not use the interaction model
(backward-compatible default: no gating when no interaction is named).

**New error codes (RECOMMENDATION):**

- `409 RSM_DISABLED` — any delivery attempt while OFF.
- `409 SNAPSHOT_STALE` — reserved for V3.x caching.

**MANUAL `[Replay]`:** maps to the frontend posting `delivery_cursor = null`
on the interaction, then re-reading `/stream`. No new verb.

---

## 20. Minimum new domain model

**One** new Pydantic model, no new Python package required outside the
daemon.

```python
# proposed shape (NOT YET IMPLEMENTED)
class InteractionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interaction_id: str
    rsm_enabled: bool = False
    source_set: list[str] = []
    delivery_cursor: str | None = None       # last Snapshot integrity.value
    last_streamed_at: datetime | None = None
```

Stored on `DaemonService` in-memory, same discipline as classification and
execution records (FACT: both are in-memory per `service.py:21–115`).
Persisting these to the FS store is deferred (OPEN QUESTION §28).

**No new objects for:**

- `SourceRevision` — the Bucket parent/child chain already handles revisions
  (§8).
- `ReplayStream` — the stream is a transport pattern over existing
  `Snapshot` + `delivery_cursor`; the daemon does not store the stream.
- `ReplayChunk` — chunks are the ordered sub-slices of the Snapshot
  `content.text` chosen by the chunking strategy; no object identity.
- `Attachment` — the runtime's attachments are *its* domain. RSM-sourced
  content remains `Bucket → Snapshot → Replay`; the UI may say "Sources"
  (user-facing).

---

## 21. Right rail — what to show, what to call it

**Role:** context *control surface* for the current interaction. Not a
workspace, not a file manager, not a dashboard, not a second chat.

**Compact surface (RECOMMENDATION):**

```
┌─ RSM ─────────────────────────┐
│ [ ON / OFF ]  (switch)        │
│ Sources           N selected  │
│ Snapshot          READY       │
│ Representation    PRESERVED   │
│ Context           3.2k / 8k   │
│ Stream            IDLE        │
│ [ Replay ]        (refresh)   │
└───────────────────────────────┘
```

Fields:

- **ON / OFF** — authoritative toggle (`role="switch"`, APG).
- **Sources** — count of Buckets in `source_set`; expanded view lists them.
- **Snapshot** — `READY | NOT READY | FAILED | STALE`.
- **Representation** — `PRESERVED | REDUCED` (from `SnapshotKind` /
  `SnapshotContent.kind`).
- **Context** — size / budget, pulled from `source_size_*` and
  `context_budget.value`.
- **Stream** — `IDLE | STREAMING | DELIVERED | CANCELLED`.
- **[Replay]** — manual re-replay (§11).

Expanded details (user-triggered "Details"):

- Snapshot ID (snap_…), Bucket IDs, source count, last generated at.
- Reduction audit — included / reduced / omitted (from
  `Snapshot.included_sources`, `.reduced_sources`, `.omitted_sources`).
- Bucket integrity hash + Snapshot integrity hash.
- Snapshot replayability (`REPLAYABLE | NOT_YET_REPLAYABLE | ...`).

**Terminology (RECOMMENDATION):** "Sources" is the clearest user-facing
label. "External Context" is clearest when disambiguating from Main Chat.
"RSM" is for engineers reading the API surface. The UI uses the first; the
docs use the second; the code keeps the third.

**What the UI must not imply:**

- Tasks, workflow stages, agent processing ownership, source completion,
  or Agent understanding.
- Round 1 Round-rail recommendations about `role="switch"`,
  `aria-expanded`, `prefers-reduced-motion`, and keyboard reachability
  carry forward — W3C ARIA Authoring Practices Guide
  (`https://www.w3.org/WAI/ARIA/apg/`).

---

## 22. The 25 required architectural questions — answered

1. **Is RSM an external-context preparation layer rather than a memory
   store?** YES. RSM owns source identity, normalization, bounded derivation,
   and delivery; it does not store Agent output, Main-Chat history, or
   long-term memory. V2 already encoded this; V3 reinforces it with the
   ReplayStreaming model (§2).

2. **Should RSM ON automatically participate in context delivery when an
   interaction begins?** YES. This is the Round 2 correction (§5): ON means
   participation, not merely permission. The initial Snapshot of the
   `source_set` is streamed when the interaction starts.

3. **Is ReplayStreaming the correct abstraction?** YES as the delivery
   pattern (§18); the transport implementation starts as chunked HTTP in V3,
   with SSE as a V3.x evolution. It is not a new domain object (§20).

4. **Does manual Replay remain necessary, and what does it mean?** YES, as
   re-replay / refresh / retry (§11). It resets `delivery_cursor` and
   re-streams the current Snapshot; it never bypasses ON/OFF.

5. **Source vs Snapshot vs Replay vs ReplayStreaming — what is the
   difference?** Source = authoritative A1-frozen Bucket. Snapshot = bounded
   derived projection. Replay = read-only wrapper (envelope with provenance
   + integrity). ReplayStreaming = progressive delivery of the Snapshot
   over chunked HTTP (§6, §18).

6. **How should large documents be reduced without becoming keyword
   extraction?** Via the pluggable `SummaryProvider` returning a bounded
   cohesive representation that preserves structure, claims, constraints,
   definitions, and caveats within budget (§7). RSM core enforces the
   budget and the derivation marker; a specific template is not mandated.

7. **How should cohesive summaries be represented and audited?** As
   `SnapshotKind.SUMMARY` with `summary_provider` recorded, `reduced_from_*`
   + `omitted_*` sizes recorded, Snapshot `integrity.value` separate from
   the Bucket's, and `provenance.derived_from.bucket_hash` linking back
   (FACT, already shipped in V2). V3 adds no new audit fields.

8. **How should small user edits invalidate / rebuild derived
   representations?** Edit = new Bucket (A1 forbids mutating the old one);
   old Snapshot becomes stale by hash mismatch; rebuild is a pure function
   of the new Bucket + budget (§8). RSM does NOT claim selective rewrite.

9. **Can derived representations be recomputed without rewriting the
   authoritative source?** YES — already true in V2 (`build_snapshot` is
   pure, `canonical_preimage` excludes mutable fields; §9).

10. **When should targeted source retrieval be used?** When the Agent (via
    the runtime) determines the Snapshot omitted something it needs
    (§10). RSM returns an authoritative source segment with provenance.

11. **V3, V3.x, V4, or future-only for targeted retrieval?** **V3.x.**
    Validate ReplayStreaming first (§10, §27).

12. **How should stale Snapshots behave?** Hash-mismatch check (§12). V3
    builds on demand; V3.x caches with the stale check as a mandatory
    guard.

13. **What does RSM know about delivery?** DELIVERED only (optionally
    RECEIVED via an ack hook). PROCESSED and UNDERSTOOD are runtime/Agent
    facts RSM must never claim (§13).

14. **What must remain runtime-owned?** `AgentContext` composition, Agent
    reasoning, context-window arithmetic for the model, caching of Agent
    output, deciding whether to include RSM content in a given turn, and
    enforcement of prompt-injection discipline on received content
    (§14, §24).

15. **What happens when RSM is enabled mid-conversation?** Next turn
    streams from `delivery_cursor = null`; prior turns are not retro-
    augmented (§15).

16. **What happens when RSM is disabled during an active run?** The
    daemon flips the flag; in-flight stream is cancelled; already-
    delivered chunks remain with the runtime; subsequent calls return
    `409 RSM_DISABLED` (§16).

17. **What happens when the Agent needs information omitted from the
    Snapshot?** Short term: full Bucket read (`GET /v1/buckets/{id}`),
    subject to runtime budget. Medium term: targeted retrieval (V3.x,
    §17, §10).

18. **Does ReplayStreaming require a new transport?** NO (chunked HTTP via
    FastAPI `StreamingResponse` is sufficient). SSE and WebSocket are not
    V3 (§18).

19. **Minimum new API surface?** 3 endpoints (`GET`/`PUT` interactions,
    `GET` stream) + 2 error codes (`409 RSM_DISABLED`,
    `409 SNAPSHOT_STALE` reserved) + an `interaction_id` parameter on the
    existing replay/snapshot endpoints (§19).

20. **Minimum new domain model?** 1 Pydantic model, `InteractionRecord`
    (§20). No new Snapshot fields, no `SourceRevision`, no
    `ReplayStream` object.

21. **Does the right rail need to expose reduction status and source
    status?** YES — Sources, Snapshot readiness, Representation
    (preserved / reduced / stale), Context budget, Stream state, ON/OFF,
    `[Replay]` (§21).

22. **What should the user see when a source is too large to fully
    represent?** Representation = REDUCED, with the audit (included /
    reduced / omitted) visible on expand. If no provider is wired,
    Snapshot = FAILED with reason `SUMMARY_UNAVAILABLE` (existing V2
    error, FACT).

23. **What should happen when reduction fails?** `422
    SNAPSHOT_BUILD_FAILED` (existing V2 error) or `409
    SUMMARY_UNAVAILABLE` (existing V2 error); UI shows "Reduction
    failed" and does not stream; ON remains honoured so a retry via
    `[Replay]` is possible.

24. **What should happen when a source changes while a replay is in
    progress?** The in-flight stream is still delivering the pre-edit
    Snapshot; on completion, the right rail flags the current Snapshot as
    STALE; the user `[Replay]` to resend the new Snapshot (§12, §16).
    RSM must not silently splice edited content into an in-flight stream.

25. **How can the system prove which source revision produced a
    Snapshot?** `snapshot.provenance.derived_from.bucket_hash` ==
    `Bucket.hash.value`; both are SHA-256 over canonical bytes
    (`canonical_preimage`); already enforced (FACT). The ReplayStream
    carries the Snapshot's `integrity.value` so the runtime can verify
    on receipt.

---

## 23. Required state / data-flow model

```
                       ┌──────────────────────────┐
                       │       EXTERNAL SOURCE    │
                       │  (any: text/pdf/web/zip) │
                       └─────────────┬────────────┘
                                     ▼
                     ┌────────────────────────────────┐
                     │   INGESTED  (rsm.extraction)   │
                     │   Bucket @ RECEIVED → STORED   │
                     │   A1-frozen after STORED       │
                     └─────────────┬──────────────────┘
                                   ▼
                     ┌────────────────────────────────┐
                     │   NORMALIZED (rsm.normalization)│
                     │   pure fn of frozen Bucket     │
                     └─────────────┬──────────────────┘
                                   ▼
                     ┌────────────────────────────────┐
                     │ SNAPSHOT PREPARED (rsm.snapshot)│
                     │ kind = preserved | summary      │
                     │ budget obeyed; integrity.value  │
                     │ provenance.derived_from.bucket_ │
                     │ hash == Bucket.hash.value       │
                     └─────────────┬──────────────────┘
                                   ▼
                 ┌────────────────────────────────────┐
                 │ READY FOR REPLAY                   │
                 │ (interaction.source_set non-empty, │
                 │  interaction.rsm_enabled == true)  │
                 └──────────────┬─────────────────────┘
                                ▼
                 ┌────────────────────────────────────┐
                 │ REPLAYSTREAMING                    │
                 │ chunked HTTP; delivery_cursor      │
                 │ advanced after each chunk;         │
                 │ final cursor = snapshot.integrity  │
                 └──────────────┬─────────────────────┘
                                ▼
                 ┌────────────────────────────────────┐
                 │ RUNTIME RECEIVED                   │
                 │ runtime acks (optional); composes  │
                 │ AgentContext.                      │
                 └────────────────────────────────────┘
```

### Failure states (clearly separated from RSM state)

| Failure | Where surfaced | Who recovers |
|---|---|---|
| SOURCE INVALID (bad PDF, oversized, forbidden path) | `rsm.extraction` + `boundaries.*` config → ingest fails with `BOUNDARY_VIOLATION` or `VALIDATION_FAILED`. | user re-ingests. |
| SNAPSHOT TOO LARGE (no provider; `reduce=null`) | `/snapshot` → `409 SUMMARY_UNAVAILABLE`. | user raises budget or wires a provider. |
| REDUCTION UNAVAILABLE (provider configured but refuses) | `/snapshot` → `409 SUMMARY_UNAVAILABLE` from the provider. | user chooses different provider or budget. |
| REDUCTION FAILED (provider returned over-budget text) | `/snapshot` → `422 SNAPSHOT_BUILD_FAILED`. | fix provider. |
| SNAPSHOT STALE (future caching) | `/stream` → `409 SNAPSHOT_STALE` (reserved) OR silent rebuild (V3.x policy). | automatic. |
| RSM OFF | all delivery endpoints → `409 RSM_DISABLED`. | user toggles ON. |
| UNKNOWN INTERACTION | `/stream` / `/replay?interaction=…` → default record → `409 RSM_DISABLED` (fail closed). | runtime provides `interaction_id`. |
| REPLAY BLOCKED (lifecycle: RETIRED or NOT_YET_REPLAYABLE) | `/replay` → `replayability: NOT_REPLAYABLE | NOT_YET_REPLAYABLE`. | advance lifecycle or wait. |
| RUNTIME UNAVAILABLE | `/stream` connection error. | runtime retries; RSM does not. |
| SOURCE CHANGED DURING REPLAY | stream completes with old content; right rail flags STALE; user `[Replay]` to resend. | user. RSM does NOT splice. |

### What stays runtime state

- Which turn of the conversation is being composed.
- Whether a given stream was *used* in that turn.
- Which model is being called.
- Model-specific tokenization and overhead reservations.
- Agent output.

---

## 24. Security / data-boundary model

```
┌──────────────────────┐    source material only; never instructions
│       USER SOURCE    │─────────────────────────────────────────┐
└──────────┬───────────┘                                          │
           ▼                                                      │
┌────────────────────────────┐    ingestion:                     │
│   RSM — ingest + validate  │  • path traversal: sanitised       │
│  (rsm.extraction + bound.) │  • archives OPAQUE                │
└──────────┬─────────────────┘  • PDF via pymupdf (ADR 0007)     │
           ▼                     • bounded recursion / size      │
┌────────────────────────────┐                                   │
│  RSM — Bucket + Integrity  │  A1 frozen under FROZEN_FIELDS   │
│  (bucket + integrity)      │  SHA-256 identity                │
└──────────┬─────────────────┘                                   │
           ▼                                                      │
┌────────────────────────────┐                                   │
│  RSM — Normalize + Snapshot│  deterministic; no execution;    │
│  (normalization + snapshot)│  no LLM call in core (ADR 0002)  │
└──────────┬─────────────────┘                                   │
           ▼                                                      │
┌────────────────────────────┐  AUTHZ GATE                      │
│  RSM — ReplayStream        │  rsm_enabled == true (per IR)    │
│  (new; /interactions/.../  │  interaction_id present           │
│   stream)                  │  fail-closed on unknown           │
└──────────┬─────────────────┘                                   │
           ▼                                                      │
┌────────────────────────────┐  payload tagged source="rsm" +    │
│   RUNTIME                  │  provenance + integrity so the    │
│                            │  runtime can distinguish and      │
│                            │  escape it from Main Chat.        │
└──────────┬─────────────────┘                                   │
           ▼                                                      │
┌────────────────────────────┐                                   │
│          AGENT             │   PROMPT INJECTION HAZARD:        │
│                            │   runtime treats content as DATA, │
│                            │   not instructions (its policy).  │
└────────────────────────────┘                                   │
                                                                 │
     ◄── Main Chat remains an independent channel ──────────────┘
```

**Where each discipline enforces:**

- **Authorization** — daemon-side (`InteractionRecord.rsm_enabled`); UI is a
  mirror, not the authority. `409 RSM_DISABLED` fails closed.
- **Integrity** — SHA-256 on both Bucket (A1) and Snapshot (independent).
- **Provenance** — on every delivered payload (W3C PROV-JSON).
- **Prompt injection** — RSM carries `"source": "rsm"` plus provenance; the
  runtime MUST treat payloads as source material, not instructions. RSM
  cannot prevent prompt injection unilaterally — this is a runtime policy
  (§13).
- **Source execution prohibition** — RSM never executes source bytes;
  `rsm.extraction` is byte-faithful (markdown preserved as text, PDF via
  deterministic text extraction, archives opaque).
- **Main Chat separation** — V1 §15 preserved: user Main-Chat messages
  never auto-ingest; Agent output never auto-promotes.
- **Cross-interaction leakage** — `interaction_id` is opaque and
  runtime-supplied; the daemon never invents one or cross-reads. Each
  record is keyed only by that string.

### New V3 risk table

| Risk | Mitigation |
|---|---|
| Prompt injection via source body | `source="rsm"` + provenance on every chunk; runtime enforces (RSM makes it detectable, cannot prevent). |
| Stale stream silently reused | `delivery_cursor` + Snapshot `integrity.value`; mismatch forces re-stream. |
| Cross-interaction leakage | `interaction_id` keyed records; unknown ⇒ fail closed. |
| OFF → ON toggle race (two concurrent requests, OFF briefly) | Daemon reads the record under its service-level lock; the first request that observes `false` is rejected. No cross-interaction effect. |
| ReplayStream disclosure of a Bucket outside `source_set` | Daemon validates the Snapshot's `bucket_id` is in `interaction.source_set` before streaming. |
| MCP escalation (tools) | ADR 0008 preserved — resources only, no MCP tools. |
| LLM dependency creep in RSM core | `check_forbidden_deps.py` + `test_e2e_12_no_ai` keep the ban. |

### Boundary rule, carried forward and strengthened

> Source content ≠ Agent instruction. Normalisation preserves bytes; it
> never promotes them. The runtime surface distinguishes RSM-sourced
> material via `source: "rsm"` and `provenance.derived_from`. RSM asserts
> DELIVERED; it never asserts PROCESSED or UNDERSTOOD.

---

## 25. Justified ADRs

Each ADR below is proposed if and only if it embodies a decision this
investigation makes.

| Proposed ADR | Rationale | Required? |
|---|---|---|
| **0009 — RSM ON = participation (ReplayStreaming on interaction start)** | Encodes the Round 2 correction (§5). | **YES** |
| **0010 — ReplayStreaming transport (chunked HTTP in V3; SSE deferred)** | Encodes §18. | **YES** |
| **0011 — Source vs Snapshot authority (A1 preserved; derived marker)** | Codifies §6, §7, §9 — mostly reiterates V1/V2 for V3 contributors. | **optional**; §6 is already captured by V1 ADR 0003 + V2 docs. |
| **0012 — Source revision as new Bucket, not mutation** | Encodes §8. | **YES** |
| **0013 — Right-rail as context control surface, not workspace** | Encodes §21. | **YES** |
| **0014 — Local AI / Host AI via SummaryProvider; no vendor coupling** | Reiterates ADR 0002 and the V2 Protocol. | **optional**; ADR 0002 already covers the ban; V2 docs cover the provider. |
| **0015 — Targeted source retrieval deferred to V3.x** | Encodes §10, §17. | **YES** |

Candidate ADRs 0011 and 0014 are not strictly required (§6, §7, §9, §14 are
already covered by V1 ADR 0003 / V2 docs). Writing them anyway is low-cost
documentation hygiene for V3 contributors; implementation turn decides.

---

## 26. Documentation this round produces

- **This file** (`docs/rsm-v3-investigation.md`) — Round 2 investigation,
  replaces Round 1.

No other documentation is created or modified in this research round. The
V1/V2 documentation (`docs/architecture/*.md`, `docs/decisions/0001–0008`,
`docs/api/http.md`, `docs/security/threats-and-mitigations.md`,
`docs/verification-matrix.md`) stays as-is.

---

## 27. V3 scope separation

### V3 MUST HAVE

- `InteractionRecord` Pydantic model (one new object; §20).
- `rsm.api.routers.interactions` with `GET` + `PUT` (§19).
- `rsm.api.routers.interactions.stream` — chunked HTTP streaming the current
  Snapshot (§18, §19).
- Existing `/replay` and `/snapshot` accept `interaction_id` (header or
  query) and gate on `rsm_enabled` (§19).
- New error `409 RSM_DISABLED` (§19).
- Fail-closed default: unknown `interaction_id` → `rsm_enabled: false`.
- Right-rail Tailwind drawer wiring the above (§21).
- Backward-compatible: calls without `interaction_id` continue to behave as
  V2 (no gating), so existing tests keep passing.
- Tests: PUT/GET round trip; stream delivers; stream refused on OFF;
  unknown interaction refused; A1/A2/A3 regression.
- ADRs 0009, 0010, 0012, 0013, 0015 authored.

### V3 SHOULD HAVE

- A RECEIVED ack hook on `/stream` (optional runtime POST back) so
  `[Replay]` retry is bounded (§13, §19).
- Snapshot cache keyed by `(bucket_id, context_budget, provider_name)` with
  the stale-check guard (§12). Reserved error `409 SNAPSHOT_STALE` added
  only when cache is wired.
- `GET /v1/capabilities` advertising schema versions and supported
  `BudgetUnit` values (previously deferred OPEN QUESTION).

### V3.x / FUTURE

- Targeted source retrieval (§10, §17): `GET /v1/buckets/{id}/segment` or
  JSON-path selector.
- Multi-Bucket Snapshot aggregation (§5 — `source_set` length > 1 today
  only *selects* a Bucket; aggregation into one Snapshot is V3.x).
- SSE transport (§18) for runtimes that need named events / heartbeats.
- `InteractionRecord` persistence to the FS store (same pattern that
  classification/execution would need for durability).
- Audience / expertise-matched Snapshot providers.

### V4 / FUTURE ARCHITECTURE

- Richer segment selectors (semantic region, section heading).
- Bidirectional streaming (WebSocket) for Agent-side requests.
- Partial-recompute optimisation inside providers (opt-in).

### OUT OF SCOPE (hard; see §28 of the task)

- Task management, project management.
- Workflow / stage orchestration (do NOT turn source examples into
  workflow concepts).
- Agent orchestration or agent runtime inside RSM.
- Second chat; dashboards; file manager.
- Vector database; provider registry; vendor-specific logic.
- Model-specific tokenization inside RSM core.
- Autonomous research or browsing by RSM.
- Automatic Agent-output ingestion into RSM; automatic promotion of Agent
  output into canonical source.
- OpenAI-specific attachment or project primitives.
- Fake frontend data.
- Any API or domain object not justified by §19 / §20.

---

## 28. Open questions

1. **RECEIVED ack hook — mandatory or optional?** If mandatory, every runtime
   must POST back on stream completion; if optional, retry policy on
   `[Replay]` is best-effort. Recommendation: optional in V3.
2. **Cache or not in V3?** V3 could ship stateless (Snapshots built on each
   `/stream`) or add the cache + stale-check. Recommendation: stateless in
   V3; cache in V3.x.
3. **Chunking strategy for ReplayStream.** Deterministic byte windows vs
   section-boundary chunks vs single-shot JSON. Recommendation: single JSON
   envelope streamed as one chunk in V3 (simplest honest implementation);
   multi-chunk is a V3.x optimisation.
4. **`source_set` length > 1 in V3?** Keep it a list in the model (for V3.x
   forward-compat) but enforce length ≤ 1 at the daemon in V3? Or allow N
   but only stream the first Bucket's Snapshot? Recommendation: enforce
   length ≤ 1 for V3; relax in V3.x along with aggregation.
5. **Primary-source URLs for ChatGPT Projects / OpenAI Work interop.**
   Carried over from Round 1 OPEN QUESTION 6 — fetch at implementation
   time; nothing in V3 depends on it.
6. **`GET /v1/capabilities` payload shape.** If added, which fields? At
   minimum: `schema_version`, supported `BudgetUnit`, supported
   `SummaryProvider` names.
7. **Observability.** Should the daemon event log append a
   `rsm_stream_delivered` event (interaction_id + snapshot integrity)? V3
   SHOULD; V2's `EventLog` can carry it without a schema change.
8. **UX wording** — "Sources" vs "External Context" vs "RSM" in the right
   rail. Recommendation (§21): "Sources" user-facing, "External Context"
   contextual, "RSM" engineer-facing. Decided; not open.

---

## 29. Verification confirmation

Executed in the sandbox against the current repository, both before and
after this document was written:

```
pytest -q tests/backend        : 107 passed, 2 intentional skips  (UNCHANGED)
check_boundaries.py            : boundary gate OK
check_forbidden_deps.py        : forbidden-dep gate OK
check_pymupdf_import.py        : pymupdf-import gate OK
```

No production source files were modified during this investigation.

---

## 30. FINAL REPORT

```
STATUS:
RESEARCH COMPLETE

CURRENT V1:
UNCHANGED

CURRENT V2:
UNCHANGED

CORE RSM PURPOSE:
External-context preparation and delivery layer. RSM owns:
  (a) authoritative source identity (Bucket, A1-frozen),
  (b) deterministic normalization,
  (c) bounded derived representation (Snapshot, LLM-free core, SummaryProvider-pluggable),
  (d) delivery to a consuming runtime (Replay envelope + ReplayStreaming),
  (e) provenance + integrity on every payload.
RSM does NOT own: AgentContext composition, Agent reasoning, Main-Chat
history, runtime cache, task/project/workflow state, long-term memory.

SOURCE MODEL:
Authoritative, A1-frozen Bucket (schema_version "1"). A content edit is a
NEW Bucket with provenance.derived_from pointing back to the previous
Bucket. The old Bucket is never mutated; its hash remains verifiable.
Supported origins (FACT): markdown, text, pasted, stdin, chatgpt_export,
pdf, folder, opaque. Any supported source — pasted sentence, webpage, PDF,
research folder, attachment — flows through the same Bucket primitive. No
`task` / `stage` / `workflow` / `version-tracked requirement` concept is
introduced.

DERIVED REPRESENTATION:
Bounded, non-authoritative, regenerable. Snapshot owns `snapshot_id`,
`integrity.value`, `context_budget`, `included/reduced/omitted` audit,
`SnapshotKind` (preserved | summary), and `provenance.derived_from`
pointing at the Bucket by id + hash. The full source always remains
recoverable via GET /v1/buckets/{id}. A derived summary is marked
derived (`summary_provider` recorded) and never claims to be the source.

SNAPSHOT:
Unchanged from V2 (model + builder + SummaryProvider). V3 adds no fields.
Delivery is via ReplayStreaming (new); construction is still on demand.
Staleness is the SHA-256 hash comparison between
`snapshot.provenance.derived_from.bucket_hash` and the current Bucket
hash — relevant when V3.x adds caching.

REPLAY:
Existing read-only envelope with source="rsm" + provenance + integrity
(FACT). Preserved in V3. Replay is NOT the admission gate for RSM content;
ON/OFF is (see RSM ON/OFF below).

REPLAYSTREAMING:
New in V3 as a delivery pattern (not a new domain object). Transport is
chunked HTTP (FastAPI StreamingResponse) in V3; SSE is a V3.x option.
WebSocket is not V3. The stream carries the current Snapshot (one or more
ordered chunks) plus its integrity.value, and advances the interaction's
`delivery_cursor` on completion. The stream delivers; it does NOT assert
the Agent processed or understood the content.

RSM ON/OFF:
ON = RSM participates in the current interaction's external-context feed;
ReplayStreaming runs automatically when the interaction begins (and after
any user-triggered manual Replay). OFF = RSM MUST NOT release anything
into the interaction (409 RSM_DISABLED). Default is OFF (fail closed).
Per-interaction authoritative value lives on the daemon
(`InteractionRecord.rsm_enabled`); the UI is a mirror; the API carries it;
the daemon enforces it. Toggling ON mid-conversation primes the next turn
for a stream; toggling OFF during an active stream cancels in flight and
cannot un-send already-delivered chunks.

MAIN CHAT ↔ RSM BOUNDARY:
Three named context domains:
  MAIN_CHAT_CONTEXT     — owner: runtime (RSM must not persist it)
  RSM_CONTEXT           — owner: RSM (Bucket + Snapshot + Replay/stream payload)
  RUNTIME_AGENT_CONTEXT — owner: runtime (composition of the above)
RSM never composes AgentContext. Main-Chat messages are never auto-ingested
into Buckets (V1 §15 preserved); Agent output is never auto-promoted.
`source="rsm"` + provenance tag everything RSM releases so the runtime
can distinguish and quote-wrap it.

SOURCE REVISION:
A user correction creates a NEW Bucket (A1 forbids mutation after STORED)
with `provenance.derived_from = <old bucket_id>`. The new Bucket has its
own hash. The old Snapshot (if cached) is stale by hash mismatch and must
be rebuilt. RSM does NOT promise selective rewrite of only the changed
sentence; a single edit can legitimately alter the whole cohesive
representation, and the Snapshot is a pure function of the new Bucket.

SNAPSHOT INVALIDATION:
Rule: `snapshot.provenance.derived_from.bucket_hash != current Bucket.hash`
⇒ Snapshot STALE. V3 builds on demand so staleness is a forward safeguard;
V3.x caches, at which point the comparison is a cache-lookup precondition.
On stale: rebuild (silent) OR 409 SNAPSHOT_STALE (explicit) — policy
decision deferred to the V3.x implementation turn.

TARGETED SOURCE RETRIEVAL:
Deferred to V3.x. Allowed shape: GET /v1/buckets/{id}/segment with a
bounded byte range or JSON-path selector, returning an authoritative
source segment with its own integrity envelope. Not in V3 so that V3's
one-way delivery security story can be validated first.

AGENT RESPONSIBILITY:
Composing AgentContext, reasoning, interpretation, review, planning,
caching, next-step preparation, deciding when/whether to include RSM
content, enforcing prompt-injection discipline on received content,
model-specific tokenization and overhead budgeting. RSM provides no
runtime, no agent orchestration, no planner, no task manager.

RSM RESPONSIBILITY:
Source (Bucket) + normalization + bounded Snapshot + Replay envelope +
ReplayStreaming + provenance + integrity + ON/OFF enforcement +
explicit refusal when disabled. Reports DELIVERED only; never PROCESSED
or UNDERSTOOD.

RIGHT-RAIL:
Context control surface, not workspace. Shows ON/OFF switch, source
count, Snapshot readiness, Representation (preserved | reduced | stale),
context usage vs budget, stream state, and a [Replay] manual re-replay
button. Expanded view surfaces snapshot_id, bucket_id(s), reduction
audit (included / reduced / omitted), both integrity hashes, and
replayability. Accessibility follows W3C ARIA APG (switch, disclosure).
Terminology: "Sources" (user), "External Context" (contextual),
"RSM" (engineer).

LOCAL AI / HOST AI:
Framework-first and vendor-neutral. All AI participation enters RSM
through the existing `SummaryProvider` Protocol
(`summarize(text, budget_bytes, budget_chars) -> str`). Implementations
may be local models, host runtime models, external APIs via adapters,
or deterministic reductions. RSM core imports no AI/LLM/agent SDK
(enforced by `check_forbidden_deps.py` and e2e_12_no_ai). AI-derived
output is always marked derived; it is never canonical source.

CONTEXT BUDGET:
Three independent limits:
  CAPTURE LIMIT         — `rsm.config.Boundaries.max_source_bytes`
                          (etc.) — what RSM accepts/stores.
  SNAPSHOT LIMIT        — `ContextBudget{unit, value, is_hard_limit}`
                          — what the Snapshot carries.
  RUNTIME REPLAY LIMIT  — the runtime's own model-context budget
                          — not RSM's concern.
BudgetUnit = {bytes, characters, tokens_estimate}; tokens_estimate =
ceil(chars/4) — deterministic heuristic, never claimed as an exact
model token count. V3 adds no new budget types.

SECURITY:
Preserved: A1 immutability; byte-faithful ingestion; opaque archives;
bounded PDF/folder; path traversal sanitisation; forbidden-deps gate;
MCP resources-only (ADR 0008); no AI SDK in rsm.*. Added in V3:
`InteractionRecord.rsm_enabled` is the authoritative delivery gate;
unknown or OFF interactions fail closed (409 RSM_DISABLED); payloads
tagged source="rsm" + provenance for the runtime to recognise and
quote-wrap (prompt-injection discipline is enforced by the runtime,
not by RSM); daemon validates every streamed Snapshot's bucket_id is
within the interaction's source_set.

API CHANGES REQUIRED:
YES, minimal. Three new endpoints:
  GET  /v1/interactions/{interaction_id}
  PUT  /v1/interactions/{interaction_id}
  GET  /v1/interactions/{interaction_id}/stream
and an `interaction_id` parameter (header X-RSM-Interaction or query)
on the existing /replay and /snapshot. Two new error codes:
  409 RSM_DISABLED
  409 SNAPSHOT_STALE  (reserved; emitted only when V3.x cache lands)
Backward-compatible: V2 callers that do not supply `interaction_id`
continue to see current behaviour (no gate), so existing tests keep
passing.

DOMAIN MODEL CHANGES:
ONE new Pydantic model, `InteractionRecord`
  { interaction_id, rsm_enabled, source_set, delivery_cursor,
    last_streamed_at }
stored in-memory on `DaemonService` (same pattern as classification +
execution). No new Snapshot fields; no SourceRevision object; no
ReplayStream object; no Attachment object.

IMPLEMENTATION SCOPE:
V3 MUST: InteractionRecord model + interactions router + stream endpoint
+ /replay and /snapshot gate on interaction + 409 RSM_DISABLED + fail-
closed defaults + right-rail Tailwind drawer wiring the above + the
backward-compat path for V2 callers + regression tests + ADRs 0009,
0010, 0012, 0013, 0015.
V3 SHOULD: optional RECEIVED ack POST on /stream; GET /v1/capabilities;
`rsm_stream_delivered` event in the event log.

V3.x / FUTURE:
Targeted source retrieval (/v1/buckets/{id}/segment). Multi-Bucket
Snapshot aggregation (source_set length > 1 produces one aggregated
Snapshot). Snapshot cache + 409 SNAPSHOT_STALE enforcement. SSE
transport. InteractionRecord persistence. `GET /v1/capabilities` if
not shipped in V3 SHOULD.

OUT OF SCOPE:
Task / project / workflow management; agent orchestration; second
chat; vector database; provider registry; vendor-specific provider
logic; model-specific tokenization in RSM core; autonomous research
or browsing; agent runtime inside RSM; automatic Agent-output
ingestion; automatic promotion of Agent output into canonical source;
OpenAI-specific attachment or project primitives; fake frontend data;
UI dashboards or file managers; any new API or domain object not
listed under API CHANGES REQUIRED / DOMAIN MODEL CHANGES.

OPEN QUESTIONS:
1. RECEIVED ack mandatory or optional (recommend optional in V3).
2. Cache in V3 or defer to V3.x (recommend defer).
3. Chunking strategy for ReplayStream (recommend single JSON chunk
   in V3; multi-chunk in V3.x).
4. source_set length > 1 enforcement in V3 (recommend enforce ≤ 1
   in V3; relax in V3.x with aggregation).
5. Primary-source URLs for ChatGPT Projects / OpenAI Work interop —
   fetch at implementation time; nothing in V3 depends on them.
6. GET /v1/capabilities payload shape (minimum: schema_version,
   supported BudgetUnit values, supported SummaryProvider names).
7. rsm_stream_delivered event in the daemon event log — recommend YES
   (V3 SHOULD).

FILES CHANGED:
docs/rsm-v3-investigation.md  (REPLACED — this document; was Round 1
                                investigation; no production code
                                changed; V1 + V2 remain frozen).

TESTS:
pytest -q tests/backend         107 passed, 2 intentional skips (UNCHANGED)
check_boundaries.py             boundary gate OK
check_forbidden_deps.py         forbidden-dep gate OK
check_pymupdf_import.py         pymupdf-import gate OK
(Executed before and after this document was written.)

RESEARCH SOURCES:
- Direct inspection of this repository:
    backend/src/rsm/bucket/{model.py, schema.py, serializer.py, immutability.py}
    backend/src/rsm/lifecycle/{states.py, transitions.py, events.py}
    backend/src/rsm/integrity/sha256.py
    backend/src/rsm/provenance/{model.py, prov_json.py}
    backend/src/rsm/normalization/model.py
    backend/src/rsm/snapshot/{model.py, builder.py, summary_provider.py}
    backend/src/rsm/replay/{readiness.py, envelope.py}
    backend/src/rsm/transports/{canonical.py, http/view.py, mcp/view.py,
                                 json_export.py, stdout.py}
    backend/src/rsm/api/{app.py, errors.py, routers/*.py}
    backend/src/rsm/daemon/{service.py, store.py, eventlog.py}
    backend/src/rsm/mcp_server/server.py
    backend/src/rsm/config/schema.py
    backend/tools/{check_boundaries.py, check_forbidden_deps.py,
                   check_pymupdf_import.py}
    tests/backend/{unit, integration, e2e, security}
    frontend/web/src/{lib/rsm-client.ts, types/bucket.ts, app/**}
    docs/{architecture/*, decisions/0001–0008, api/http.md,
          security/threats-and-mitigations.md, verification-matrix.md}
- RSMFInalStructure.txt (governing spec; frozen).
- W3C PROV-JSON — https://www.w3.org/TR/prov-json/
- W3C ARIA Authoring Practices Guide — https://www.w3.org/WAI/ARIA/apg/
  (switch, disclosure, dialog patterns referenced in §21).
- Model Context Protocol — https://modelcontextprotocol.io/ and
  https://py.sdk.modelcontextprotocol.io/ (resources-only discipline
  preserved from ADR 0008).
- JSON Schema Draft-07 — the canonical bucket schema's declared dialect.
- FastAPI documentation on StreamingResponse (chunked HTTP) — the V3
  transport choice (§18) does not require a new dependency.
- HTML Living Standard EventSource / SSE — surveyed for V3.x option
  (§18); not adopted for V3.
```
