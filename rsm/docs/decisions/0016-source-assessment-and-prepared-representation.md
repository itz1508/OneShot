# ADR 0016 — Source Assessment and Prepared Representation

**Status:** V3. Binding.

## Context

The V3 architecture already encodes the doctrine

```
SOURCE  →  SCAN  →  FILES  →  READER + VISION  →  PROCESSOR  →  REPLAY  →  AGENT
```

in separate boundaries (`rsm.bucket`, `rsm.reader`, `rsm.vision`,
`rsm.snapshot`, `rsm.replay`, `rsm.interaction`). What was missing was:

1. a read-only **Source Assessment** surface that answered the §14
   "RSM-first" question — *does this request materially require external
   source observation?* — without the caller first opting into delivery
   via an `InteractionRecord`;
2. an explicit architectural name for the **Prepared Representation**
   envelope that the Processor hands to Replay — Snapshot already carries
   the prepared text, the replay envelope already carries release
   semantics, and the Reader trace already carries observation coverage,
   but no single name united them.

## Decision

Two small additive modules:

- `rsm.assessment` — pure read-only `assess_source(bucket) ->
  SourceAssessment`. Depends only on stdlib + pydantic + rsm.bucket +
  rsm.reader. Never imports Snapshot, Replay, Classification, Execution
  or any Agent SDK. Enforced by `backend/tools/check_boundaries.py`.
- `rsm.prepared` — typed `PreparedRepresentation` envelope assembled
  from `(assessment, read_result, snapshot, replay_envelope)`. Depends
  on the same boundary modules plus rsm.snapshot + rsm.replay +
  rsm.assessment. Pure composition, no new I/O.

HTTP surface:

- `GET /v1/buckets/{id}/assess` — read-only assessment. **No**
  interaction gate (an assessment describes what RSM *would* release;
  it never releases Source content itself).
- `GET /v1/interactions/{id}/stream` — unchanged behavior; the response
  **adds** a top-level `prepared_representation` key that unites the
  existing `replay` + `snapshot` keys with the new `assessment` and
  `coverage` (ReaderTrace) pieces. Every pre-refactor key keeps its
  exact pre-refactor shape (frozen by `test_api_interactions.py`).

The architectural flow becomes:

```
SOURCE              (rsm.bucket, A1 preserved)
  ↓
SOURCE ASSESSMENT   (rsm.assessment.assess_source, read-only)
  ↓
SCAN + FILES        (rsm.reader.scan_bucket)
  ↓
READER + VISION     (rsm.reader.read_bucket, rsm.vision injected)
  ↓
PROCESSOR           (rsm.snapshot.build_snapshot)
  ↓
PREPARED REPRESENTATION   (rsm.prepared.PreparedRepresentation)
  ↓
REPLAY              (rsm.replay.build_replay_envelope + /stream)
  ↓
AGENT               (consuming runtime — outside RSM)
```

## ON/OFF (`rsm_enabled`) is an override, not the fundamental model

Section 17 asks that the ON/OFF mechanism be preserved as an **explicit
override**, not as the fundamental architecture mechanism determining
whether external source preparation occurs.

The V3 implementation already matches that semantics:

- Whether a request *materially requires* external source observation
  is a property of the request, not of the `InteractionRecord`. The
  host application answers it with `GET /v1/buckets/{id}/assess` (no
  gate, no release) **before** touching an interaction.
- `rsm_enabled` is the **per-interaction** user override — fail-closed
  by default so an unknown or deliberately-off interaction cannot
  silently release Bucket content. It is the mechanism by which the
  user opts into delivery; it is NOT the mechanism by which RSM decides
  that observation is architecturally relevant.

This ADR does not rename `rsm_enabled`. Doing so would break every
V3-era caller, every existing integration test, and the Right-Rail
control surface (ADR 0013). The ADR instead formalises the role:
`rsm_enabled` is the override; `requires_observation` from the
assessment is the architectural signal.

## Non-goals (deferred to V3.x, or declined outright)

- No "intent classifier" that reads conversation turns and decides
  whether to invoke RSM. Source Assessment stays a pure function of the
  frozen Bucket; the application layer owns the user-intent half of §14.
- No Agent request loop for "additional observation". ADR 0015 defers
  multi-Bucket aggregation and targeted retrieval to V3.x; the Prepared
  Representation keeps the single-Bucket contract.
- No cancellation framework. The existing chunked-HTTP delivery (ADR
  0010) returns one JSON chunk; cancelling the HTTP connection stops
  delivery without mutating Source. Not changed.
- No frontend changes. The Right-Rail already renders a single ON/OFF
  switch (ADR 0013); the new assessment endpoint is a backend-only
  read-only surface.

## Verification

- `pytest -q tests/backend` — 247 passed, 2 skipped.
- `python backend/tools/check_boundaries.py` — OK (new boundary rules
  for `rsm.assessment` and `rsm.prepared`).
- `python backend/tools/check_forbidden_deps.py` — OK.
- `python backend/tools/check_pymupdf_import.py` — OK.
