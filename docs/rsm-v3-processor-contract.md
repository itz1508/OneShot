# RSM V3 — Processor contract (frozen)

**Status:** boundary freeze. No new architecture; no new domain objects;
no code redesign. Only tests and documentation changed this round.

## Canonical pipeline

```
SOURCE
  │
  │ authoritative
  ▼
SCAN
  │
  │ fast discovery
  ▼
FILES
  │
  │ bounded/addressable source material
  ▼
READER + VISION
  │
  │ observation
  ├──────────────► READER TRACE
  │
  ▼
PROCESSOR
  │
  │ bounded preparation (deterministic by default;
  │  controlled model-assisted preparation is permitted
  │  when explicitly configured — see §Controlled reasoning)
  ▼
SNAPSHOT / PREPARED REPRESENTATION
  │
  │ unchanged delivery
  ▼
REPLAY
  │
  ▼
AGENT
  │
  │ task reasoning
  ▼
RESULT
```

## Responsibility table

| Component       | Responsibility                                                   |
|-----------------|-------------------------------------------------------------------|
| Source          | Authoritative source material                                     |
| Scan            | Fast discovery                                                    |
| File            | Bounded/addressable source material                               |
| Reader          | Actual observation                                                |
| Vision          | Reader capability (not a separate top-level subsystem)            |
| Reader Trace    | Observation/coverage                                              |
| Processor       | Controlled preparation                                            |
| Snapshot        | Current bounded prepared representation (mechanism, not a product)|
| Replay          | Delivery only                                                     |
| Agent           | Task reasoning                                                    |

Short form, frozen:

```
Scan discovers.
Reader observes.
Processor prepares.
Replay delivers.
Agent reasons.
```

## Processor contract

### Definition

The **Processor** is the controlled component that transforms observed source
material into a bounded representation suitable for Replay.

In V3, the Processor is implemented by `rsm.snapshot.build_snapshot` plus
its pluggable `SummaryProvider` interface. The current providers that ship
in RSM core are `NullSummaryProvider` (explicit no-op; raises
`SummaryUnavailable` on overflow) and `PrefixSummaryProvider` (deterministic
bounded excerpt with an explicit marker). Any additional provider is
external to RSM core, invoked through the Protocol, and recorded on the
Snapshot (`SnapshotContent.summary_provider`).

### Allowed (Processor may)

- select
- filter
- order
- normalize
- deduplicate
- chunk
- compress
- reduce
- summarize
- extract
- bound
- perform **controlled, bounded model-assisted preparation** when the
  SummaryProvider implementation is explicitly configured to do so.

### Prohibited (Processor must not)

- execute the user's task
- perform external side effects
- mutate authoritative Source
- rewrite the original Bucket
- become the Agent
- become a workflow engine
- make final user-action decisions
- silently invent source facts
- silently convert output into Source

Processor output is always *derived*. It never replaces Source. Any model
metadata is recorded via the existing Snapshot provenance mechanism
(`SnapshotContent.summary_provider`, `provenance.derived_from.bucket_hash`,
`SnapshotIntegrity`) — RSM core does not add a provider abstraction.

### Controlled reasoning rule (frozen)

The correct invariant is:

> **Agent reasoning never occurs inside RSM.**

The *incorrect* rule — "reasoning never occurs before Replay" — is
explicitly rejected. The Processor may perform bounded reasoning for
*preparation* when its provider is explicitly configured to do so. The
distinction is:

```
PROCESSOR
    "What source material should be prepared for delivery?"

AGENT
    "What does this mean for the user's task, and what should I do?"
```

Those are separate responsibilities. Processor is not the Agent.

## Replay contract

Replay delivers the prepared representation unchanged. Replay must not:

- summarize
- select
- filter
- truncate
- reinterpret
- call Vision
- call a model
- perform Processor work

If transformation is required, it belongs **before** Replay.

In V3, Replay = `rsm.replay.build_replay_envelope` + the chunked-HTTP
delivery in `rsm.api.routers.interactions.stream`. Neither mutates the
Bucket, neither mutates the Snapshot, and neither performs reduction.

## Reader + Vision contract

Reader is the observation boundary. The current implementation
(`rsm.reader`) is accepted and frozen:

- **SCAN** — fast, shallow, deterministic, LLM-free; pure function of the
  frozen Bucket.
- **READER** — one `ReaderEvent` per discovered File. A per-File failure
  is isolated to that `file_id` (invariant **ONE_FILE_FAILURE ≠
  WHOLE_READER_FAILURE**).
- **VISION** — a Reader *capability* (`ReaderMethod.VISION` +
  `vision: bool`). Not wired in this build; opaque / image Files are
  recorded as `FILE_FAILED(reason="vision_unavailable" | "opaque")`.
- **READER TRACE** — backend-authoritative. The UI renders ONE continuous
  bar whose fill is `latest_index / discovered`.

No new domain objects (`ReaderSession`, `ReadingJob`, `ObservationBundle`,
`FileGraph`, …) are introduced. Vision stays a capability flag — no
`VisionReader` / `ImageReader` / `OCRReader` / `DiagramReader` class.

## Source immutability (A1 preserved)

- SCAN does not mutate the Bucket.
- Reader does not mutate the Bucket.
- Processor (`build_snapshot`) does not mutate the Bucket.
- Replay does not mutate the Bucket.
- Agent output never automatically becomes a new RSM Source.

Explicit ingestion remains the only way to introduce new authoritative
source material.

## Provider neutrality

RSM core imports no provider SDK. This is enforced by
`backend/tools/check_forbidden_deps.py` across both `backend/src/rsm/` and
`frontend/web/src/`, and by `tests/backend/integration/test_processor_contract.py::test_E_*`
which asserts the invariant per-module (`rsm.reader`, `rsm.snapshot`,
`rsm.replay`, `rsm.interaction`).

Hard-coded references to OpenAI / Anthropic / Google / Gemini / Claude /
Codex etc. are forbidden in the RSM domain.

## Application-architecture preservation

- Host-application product model intact. `next build` route table remains
  `/` + `/_not-found`.
- RSM rail remains a secondary control surface; no standalone RSM routes
  restored (`/buckets`, `/ingest`, `/lifecycle`, `/replay` stay deleted).
- No RSM dashboard; no second chat; no project / task / workflow UI; no
  client-side RSM store.

## Verification evidence (this round)

```
pytest -q tests/backend                       152 passed, 2 intentional skips
                                              (was 143 → +9 Processor contract tests)
backend/tools/check_boundaries.py             boundary gate OK
backend/tools/check_forbidden_deps.py         forbidden-dep gate OK
backend/tools/check_pymupdf_import.py         pymupdf-import gate OK
tsc --noEmit --skipLibCheck                   0 diagnostics (unchanged)
eslint 'src/**/*.{ts,tsx}'                    0 diagnostics (unchanged)
NEXT_TELEMETRY_DISABLED=1 next build --webpack success (unchanged this round)
```

## Known limitations (unchanged, honestly documented)

- **Browser E2E (Playwright) specs** are not authored; the sandbox cannot
  keep `next start` + `uvicorn` alive across tool calls. Reported honestly
  as a coverage gap — not a PASS.
- **Vision not wired.** Image / opaque Files are recorded as
  `FILE_FAILED(reason="vision_unavailable" | "opaque")` per the Reader
  isolation rule. Wiring a Vision reader is deferred and would be a
  Processor-side extension through the existing `SummaryProvider`
  Protocol, never a top-level RSM domain class.
