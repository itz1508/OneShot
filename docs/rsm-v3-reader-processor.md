# RSM V3 — Reader / Processor boundary (implementation report)

**Status:** complete this round. Backend regression + 3 gates + typecheck +
lint + production build all pass on this host. Browser E2E remains an
honestly documented coverage gap.

## Freeze (from the mission)

```
SOURCE → SCAN → FILES → READER + VISION → READER TRACE
                                          │
                                          ▼
                                        PROCESSOR → REPLAY → AGENT
```

- Scan discovers.
- Reader observes.
- Telemetry shows coverage.
- Processor prepares.
- Replay delivers.
- Agent reasons.

Hard invariants carried into the implementation:

- Source is authoritative; A1 preserved.
- A File is NOT a new Source. `file_id` is `{bucket_id}:fN` (1-based).
- One File failure ≠ whole-Reader failure.
- Processor may prepare + reduce; it does not become the Agent.
- Replay delivers; it does not transform.
- Reader trace reflects actual observation, not simulated progress.

## Files changed

### New backend

```
backend/src/rsm/reader/__init__.py
backend/src/rsm/reader/model.py            # FileRef, ReaderEvent/Kind,
                                           # ReaderStatus, ReaderMethod,
                                           # FailureInfo, FileCoverage,
                                           # ReaderTrace, ScanResult, ReadResult
backend/src/rsm/reader/scan.py             # scan_bucket — fast, shallow,
                                           # deterministic, no LLM, pure
                                           # function of the frozen Bucket
backend/src/rsm/reader/reader.py           # read_bucket — one event per
                                           # discovered File; per-File
                                           # failure is isolated
backend/src/rsm/api/routers/reader.py      # GET /v1/buckets/{id}/scan
                                           # GET /v1/buckets/{id}/reader/read
                                           # GET /v1/buckets/{id}/reader/trace
```

### Modified backend

```
backend/tools/check_boundaries.py          # add rsm.reader to the gate
                                           # (stdlib + pydantic + rsm.bucket only)
backend/src/rsm/api/app.py                 # mount the Reader router under
                                           # /v1/buckets (per-Bucket read)
```

### New backend tests

```
tests/backend/unit/test_reader.py           # SCAN determinism;
                                            # one-File failure isolation;
                                            # Reader does not mutate the Bucket;
                                            # latest_index is monotonic
tests/backend/integration/test_api_reader.py  # /scan + /reader/read +
                                              # /reader/trace shapes;
                                              # unknown bucket → 404 BUCKET_NOT_FOUND
```

### Frontend

```
frontend/web/src/types/bucket.ts                     # ReaderTrace, ScanResult,
                                                     # ReadResult, ReaderEvent,
                                                     # FailureInfo, FileCoverage,
                                                     # FileRef, …
frontend/web/src/lib/rsm-client.ts                   # readBucket → readBucketPayload
                                                     # (V1 payload reader) +
                                                     # scanBucket, readBucket,
                                                     # readerTrace (V3 Reader)
frontend/web/src/features/rsm-rail/ReaderTraceSurface.tsx
                                                     # ONE continuous bar + latest
                                                     # file reached + isolated
                                                     # failures list. No one-bar-
                                                     # per-File. Polls backend
                                                     # trace while incomplete.
frontend/web/src/app/page.tsx                        # mounts <ReaderTraceSurface />
                                                     # below the capture
                                                     # disclosure; subscribes to
                                                     # rsm:source-updated so the
                                                     # surface tracks the current
                                                     # interaction's bucket
docs/rsm-v3-reader-processor.md                      # this file
```

## Decisions

### Reader is deterministic in this build

`read_bucket` is a pure function of the frozen Bucket. It emits exactly one
`ReaderEvent` per discovered File — the loop never aborts on a per-File
failure (invariant §8). On a folder-origin Bucket:

- `supported` entries → `FILE_OBSERVED`.
- `opaque` entries → `FILE_FAILED(reason="vision_unavailable" | "opaque")`.
  Vision is modelled as a Reader capability we have NOT wired in this build.
- `unsupported` entries → `FILE_FAILED(reason="unsupported_extension")`.

### SCAN is shallow and LLM-free

- Simple-source Bucket → one File addressing the Bucket itself.
- Folder-origin Bucket → one File per manifest entry, deterministic order.

`scan_bucket` reads only the frozen Bucket's `full_content`. It never
re-opens child files on disk and never performs OCR / vision / summarisation.

### UI contract

The host page's secondary `<ReaderTraceSurface />` renders exactly:

```
| 1 [████████████████] 247
observed 240   partial 0   failed 7   complete
```

- ONE continuous `role="progressbar"` bar; `aria-valuemax = discovered`,
  `aria-valuenow = latest_index` (both backend values).
- `aria-live="polite"` on the enclosing section so screen readers see
  progress updates without stealing focus.
- Honours `prefers-reduced-motion` via the Tailwind `motion-reduce:`
  utilities on the bar fill.
- Failures are a flat `<details>` list keyed by `file_id` + `index`; the
  surface shows the latest 8 and the total.
- NEVER renders one bar per File.
- NEVER invents progress; `latest_index` comes from `/reader/trace`.

### No new domain object outside Reader

- No `ReaderSession`, `ReadingJob`, `ObservationBundle`, `FileGraph`,
  `ProcessingGraph`, `Unit`, `Artifact`.
- Snapshot remains the current bounded-prepared-representation
  implementation. Reader does NOT touch Snapshot. Replay (via
  `/v1/interactions/.../stream`) continues to deliver the Snapshot as
  before — no change to Replay semantics.

### Boundaries preserved

- `check_boundaries.py` adds `rsm.reader` with the restriction that it
  only depends on stdlib + `pydantic` + `rsm.bucket`.
- `check_forbidden_deps.py` still passes — no AI/LLM SDK imported.
- Interaction gate, A1, A2, A3 all unchanged.
- Host-application product model preserved: no new app routes; `next
  build` route table remains `/` + `/_not-found`.

## Verification (actually executed on this host)

```
pytest -q tests/backend
    143 passed, 2 skipped
    (was 132 → added 11: 6 reader unit + 5 reader integration)

backend/tools/check_boundaries.py            boundary gate OK
backend/tools/check_forbidden_deps.py        forbidden-dep gate OK
backend/tools/check_pymupdf_import.py        pymupdf-import gate OK

tsc --noEmit --skipLibCheck                  0 diagnostics
eslint 'src/**/*.{ts,tsx}'                   0 diagnostics
NEXT_TELEMETRY_DISABLED=1 next build --webpack
    Compiled successfully in 111s · TypeScript 60s · 4 static pages
    BUILD_ID: GHrtjoKcuIcOFOaAJk982
    Route (app)
    ┌ ○ /
    └ ○ /_not-found
```

## Known limitation (unchanged this round)

- Browser E2E (Playwright) specs are not authored; the sandbox cannot
  keep `next start` + `uvicorn` alive across tool calls. Reported
  honestly as a coverage gap, not a PASS.
- Vision is modelled as a Reader capability but NOT wired. Image/opaque
  entries fail per-File with `vision_unavailable`, which is the honest
  state until a Vision reader is added.
