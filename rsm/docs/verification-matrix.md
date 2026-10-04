# RSM V1 Verification Matrix

Status captured against the artifact in this archive.

## Backend

| Area | State | Evidence |
|---|---|---|
| Pytest suite | **79 passed, 2 intentional skips** | `pytest -q tests/backend` under Python 3.11.11 |
| Boundary gate | **OK** | `backend/tools/check_boundaries.py` |
| Forbidden-dep gate | **OK** | `backend/tools/check_forbidden_deps.py` |
| PyMuPDF import gate | **OK** | `backend/tools/check_pymupdf_import.py` |
| HTTP transport | **VERIFIED** | `tests/backend/integration/test_daemon_http.py` + `test_api_v1_full.py` + `test_api_errors.py` + `test_classification_does_not_alter_integrity.py` |
| MCP transport | **VERIFIED** | `tests/backend/integration/test_daemon_mcp.py` |
| Transport parity | **VERIFIED** | HTTP · MCP · JSON export · stdout — same canonical payload |
| Lifecycle | **VERIFIED** | 8 legal, exhaustive illegal rejection, RETIRED terminal |
| A1 immutability | **VERIFIED** | FROZEN_FIELDS enforced by `rsm.daemon.store.FsStore.write` |
| A2 schema_version | **VERIFIED** | `canonical_schema()` emits `{"const": "1"}` across every transport |
| A3 folder identity | **VERIFIED** | manifest with `source_count`, `unsupported_count`, `opaque_count`, `skipped_permission_denied`, `max_depth_observed`, `deterministic_ordering = "sorted_posix_path_ascending"`; children derive_from parent |
| Integrity | **VERIFIED** | `canonical_preimage()` reproduces `hash.value` across every lifecycle transition, every classification change, every execution-state change |
| Provenance | **VERIFIED** | W3C PROV-JSON projection with derivation link |
| Classification | **VERIFIED** | Independent of lifecycle; does NOT alter A1 |
| Execution state | **VERIFIED** | Independent of lifecycle/content; does NOT auto-close bucket |
| Replay readiness | **VERIFIED** | DERIVED from (state, classification); RETIRED → NOT_REPLAYABLE; RELEASED+READY_EXECUTION → REPLAY_BUILDABLE |

## Frontend

| Area | State | Evidence |
|---|---|---|
| Dependencies installed | **PASS** | `npm install` → 365 packages; `node_modules/.bin/next --version` → Next.js v16.3.8 |
| TypeScript | **PASS** | `tsc --noEmit --skipLibCheck` exit 0, 0 diagnostics |
| ESLint | **PASS** | `eslint 'src/**/*.{ts,tsx}'` exit 0, 0 diagnostics |
| `next dev` server | **PASS** | Compiled every route; all 5 responded 200; title `RSM — Replay State Memory` |
| Real daemon integration | PENDING live TCP | Covered by backend TestClient tests; live socket demo blocked by sandbox |
| Production build (`next build`) | **BLOCKED — HOST FILESYSTEM** | Overlayfs stalls optimization step; sandbox 12-min cap terminates process before `.next/BUILD_ID` is written |
| Playwright | **BLOCKED — depends on production build** | — |

## Acceptance

| AC | State |
|---|---|
| AC-1 Canonical bucket model + validation | PASS |
| AC-2 Bucket immutability (A1) | PASS |
| AC-3 schema_version="1" across transports (A2) | PASS |
| AC-4 Folder identity + provenance (A3) | PASS |
| AC-5 Lifecycle state machine | PASS |
| AC-6 SHA-256 integrity | PASS |
| AC-7 W3C PROV-JSON | PASS |
| AC-8 Fail-closed configuration | PASS |
| AC-9 No forbidden AI/LLM/agent SDKs | PASS |
| AC-10 PyMuPDF import discipline | PASS |
| AC-11 Local-first Next.js UI builds and renders | **BLOCKED — HOST FILESYSTEM** |

AC-11 remains BLOCKED (not PASS, not FAIL). The code is proven buildable
(TypeScript + ESLint + Next.js dev-mode compilation all succeed on this
host). The production bundling step requires a standard filesystem.
