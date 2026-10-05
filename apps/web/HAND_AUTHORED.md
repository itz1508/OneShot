# apps/web — hand-authored RSM UI (verified on this host)

The authored Next.js 16 / App Router / TypeScript / Tailwind UI is the real
RSM client. All components call the authoritative daemon through
`@/lib/rsm-client`. No mock/demo data.

## Verified on this host (direct evidence)

| Check | Result |
|---|---|
| `node_modules/.bin/next --version` | **Next.js v16.3.8** |
| `node_modules/react/package.json` | **19.3.0** |
| `node_modules/react-dom/package.json` | **19.3.0** |
| `tsc --noEmit --skipLibCheck` | **PASS** (exit 0, 0 diagnostics) |
| `eslint 'src/**/*.{ts,tsx}'` | **PASS** (exit 0, 0 diagnostics) |
| `next dev` serves `/`, `/buckets`, `/ingest`, `/lifecycle`, `/replay` | **PASS** (all 200; title `RSM — Replay State Memory`) |
| `next dev` App Router compilation for every route | **PASS** (reported inline by Next's own log) |

## NOT verified on this host (sandbox limits)

| Blocker | Evidence |
|---|---|
| `next build` production bundle | Overlayfs stalls Next's optimization step; multiple attempts > 480 s produced "Creating an optimized production build …" with no further progress and no `.next/BUILD_ID`. The sandbox's per-shell 12-minute cap terminates the process. |
| Live `curl http://127.0.0.1:8787/healthz` over a TCP socket | Sandbox terminates background processes between shell commands; `uvicorn` cannot stay bound across turns. The HTTP contract is covered end-to-end by `apps/rsm/tests/integration/test_daemon_http.py` (FastAPI `TestClient` → real ASGI). |
| Playwright | Depends on `next build` + live-TCP. |

## Dev-host recovery (exact procedure)

```bash
cd apps/web
pnpm install              # or: npm install  (both work)
pnpm --filter ./apps/web build
pnpm start                # or: npm start

# Separate terminal
uvicorn rsm.api.app:create_app --factory --host 127.0.0.1 --port 8787

# Then from tests/frontend/e2e/
#   point Playwright at http://127.0.0.1:3000
```
