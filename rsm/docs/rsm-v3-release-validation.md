# RSM V3 — Release-validation report

**Decision:** READY WITH DEFERRED ITEMS.

The two documented deferrals are **Browser E2E** (sandbox cannot keep
`next start` + `uvicorn` alive across tool calls) and **Vision**
(Reader capability flag; images / opaque files are honestly recorded
as `FILE_FAILED(reason="vision_unavailable" | "opaque")` per the
isolation invariant).

## Fixture matrix

- `tests/backend/fixtures/scenarios.py` — 29 deterministic scenarios
  across Source / Files / Reader / Content / Processor / Security.
  Matrix size locked by a compile-time assertion in that file.
- `tests/backend/integration/test_release_matrix.py` — one
  parametrized validation test per scenario, plus three HTTP
  security tests (ON/OFF, unknown interaction, cross-interaction
  isolation). 32 pytest ids in total.
- The 10,000-file scalability scenario is a synthetic folder manifest
  injected directly into a Bucket; no 10,000 real files are
  materialised.

## Scope discipline (observed)

No new production domain object introduced. No new routes. No new
dependencies. The host-application product model stays — `next build`
route table remains `/` + `/_not-found`.
