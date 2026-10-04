# Refactor plan — `D:\OneShot\` monorepo (RSM v6.1 → OneShot workspace)

**Target shape:** the layout the user provided (OneShot monorepo with `apps/rsm/`, `apps/oneshot/`, `packages/rsm-client/`, `frontend/web/`, root-level `docs/`, `tools/`, `tests/`, `store/`, GitHub workflows, `uv.lock`).
**Baseline:** `rsm-v6.1-export.zip` (`ppf.01a10583-c6b3-7679-acc7-70eef7a1a05f`) — **324 passed**, 4 CI gates green, 5,131 LOC across 25 `rsm.*` subpackages.
**Scope rule:** this is a **repository-shape refactor**, not a redesign. RSM Core is untouched *in behaviour*; only its filesystem home moves. OneShot is additive. Playwright + Next.js frontend keeps the same source tree, only its position relative to the repo root changes.

---

## 0. Hard decisions you need to make before touching code

Three choices change the plan. Pick each, then follow Phase 1+.

| # | Choice | Default I recommend | Why |
|---|---|---|---|
| D1 | **Keep `rsm` import name** (`import rsm.bucket`) or re-brand to `oneshot_rsm` | **Keep `rsm`** | Zero import rewrites in `backend/src/rsm/**`. Package-under-app layout (`apps/rsm/src/rsm/`) is a Python monorepo norm (`setuptools.packages.find.where = ["src"]`). |
| D2 | **Move submodules into new umbrellas** (`domain/`, `ingestion/`, `infrastructure/`) or **keep flat** | **Keep flat** (do NOT nest) | The user's tree groups packages visually; actually re-nesting means rewriting every `from ...bucket.serializer` into `from ...domain.bucket.serializer`, invalidating `check_boundaries.py`'s FORBIDDEN map, and voiding ADR 0017's three-layer split naming. If you want the *visual* grouping, use `README.md` + an `ARCHITECTURE.md` map, not real packages. |
| D3 | **Keep `pnpm` for the frontend** or **go npm-only** | **Keep `pnpm`** | `pnpm-workspace.yaml` + `pnpm-lock.yaml` are already in v6.1; switching lockfiles creates install drift with no benefit for a single workspace. |

The plan below assumes **D1 = keep `rsm`**, **D2 = keep flat**, **D3 = keep pnpm**. If you choose differently I'll flag the exact extra steps per phase.

---

## 1. End-state tree (what the plan reaches)

```
D:\OneShot\
├── .github/workflows/
│   ├── ci.yml            # pytest + 4 gates + bun/pnpm typecheck/lint + Playwright (dev-host-only tagged)
│   └── deploy.yml        # placeholder — no deploy target in v6.1 yet
├── .gitignore
├── .editorconfig
├── LICENSE
├── README.md             # trimmed root; links into docs/ and apps/*/README.md
├── pyproject.toml        # workspace root; dependency groups + tool configs only, NO [project] section
├── uv.lock               # workspace lock
│
├── docs/                 # was: rsm/docs/
│   ├── architecture/     ├── overview.md
│   │                     ├── boundaries.md   ← NEW: codifies check_boundaries.py in prose
│   │                     ├── rsm.md          ← NEW: pointer to apps/rsm/README.md
│   │                     ├── classification-and-execution.md
│   │                     ├── data-boundary.md
│   │                     ├── lifecycle-state-machine.md
│   │                     ├── replay-readiness.md
│   │                     ├── snapshot.md
│   │                     ├── transport-parity.md
│   │                     └── bucket-schema.json
│   ├── api/http.md
│   ├── decisions/        # ADR 0001–0017 (identical bytes)
│   ├── lifecycle/
│   └── security/
│
├── apps/
│   ├── rsm/
│   │   ├── pyproject.toml                       # [project] name="rsm", requires-python=">=3.11"
│   │   │                                        # [tool.setuptools.packages.find] where=["src"]
│   │   │                                        # [tool.pytest.ini_options] testpaths=["tests"]
│   │   ├── README.md                            # pointer to docs/architecture/rsm.md
│   │   ├── rsm.conf.toml.example
│   │   ├── src/rsm/
│   │   │   ├── __init__.py
│   │   │   ├── __main__.py                      # NEW: `python -m rsm` = daemon entrypoint
│   │   │   ├── api/                             # (identical bytes)
│   │   │   │   ├── __init__.py app.py errors.py
│   │   │   │   └── routers/
│   │   │   │       ├── __init__.py assessment.py buckets.py events.py
│   │   │   │       ├── interactions.py prov.py reader.py
│   │   │   │       ├── replay.py                ← NEW thin file (see Phase 5)
│   │   │   │       └── health.py                ← NEW thin file (see Phase 5)
│   │   │   ├── assessment/        bucket/       classification/
│   │   │   ├── cli/               config/       daemon/
│   │   │   ├── execution/         extraction/   integrity/
│   │   │   ├── interaction/       lifecycle/    loading/
│   │   │   ├── mcp_server/        normalization/
│   │   │   ├── prepared/          provenance/   reader/
│   │   │   ├── replay/            snapshot/     transports/
│   │   │   └── vision/
│   │   └── tests/
│   │       ├── unit/ integration/ security/ e2e/ fixtures/
│   │
│   └── oneshot/
│       ├── pyproject.toml                       # [project] name="oneshot", depends on {"rsm": "*"}
│       ├── README.md                            # OneShot shell overview
│       └── src/oneshot/
│           ├── __init__.py
│           ├── __main__.py                      # OneShot entrypoint (SCAN-only in Phase 7)
│           └── (empty — populated by the OneShot build task when it starts)
│
├── packages/
│   └── rsm-client/
│       ├── package.json                         # name="@oneshot/rsm-client"
│       ├── tsconfig.json
│       └── src/
│           └── rsm-client.ts                    # moved from frontend/web/src/lib/rsm-client.ts
│
├── frontend/
│   └── web/                                     # unchanged content; only its tsconfig import of
│       ├── package.json                         # rsm-client switches to the workspace package
│       ├── pnpm-workspace.yaml (root-level)
│       ├── public/
│       └── src/
│           ├── app/
│           │   ├── chat/page.tsx
│           │   ├── layout.tsx
│           │   └── page.tsx
│           ├── features/
│           │   ├── chat/
│           │   └── rsm-rail/
│           ├── lib/                             # now just transport.ts; rsm-client.ts moves out
│           └── types/bucket.ts
│
├── tests/                                        # cross-app tests only; apps/rsm/tests stays per-app
│   ├── integration/                              # future: oneshot↔rsm wiring tests
│   └── fixtures/                                 # shared fixture bytes used by both apps
│
├── tools/
│   ├── dev/                                      # one-off scripts (local run helpers, no CI)
│   ├── build/                                    # package / release scripts
│   └── verification/                             # the four CI gates:
│       ├── check_boundaries.py
│       ├── check_forbidden_deps.py
│       ├── check_pymupdf_import.py
│       └── check_no_agent_tools.py
│
└── store/
    ├── attachments/        # was: attachment/      (plural; matches end-state tree)
    ├── buckets/            # NEW empty dir — FsStore writes here by default via config override
    └── snapshots/          # NEW empty dir — reserved; no code writes to it in v6.1
```

**What stays byte-identical:** every file under `backend/src/rsm/` and `tests/backend/`, the ADRs, the frontend `src/` tree (minus `lib/rsm-client.ts` which moves), `rsm.conf.toml.example`, `LICENSE`, `.editorconfig`, `.gitignore`.

**What changes:** `pyproject.toml` splits into a workspace root + two app manifests; the four `check_*.py` scripts move from `backend/tools/` into `tools/verification/` (one path fix in each); the `rsm-client.ts` moves from `frontend/web/src/lib/` into `packages/rsm-client/src/`; the frontend imports it via its workspace alias instead of a relative path.

---

## 2. Dependency map and import contracts (unchanged)

The refactor **does not touch** the `check_boundaries.py` FORBIDDEN map. All 15 package rows there stay valid because every `rsm.*` package keeps its name and its position inside `rsm/`. The only thing that moves is the Python *package root* (`<repo>/apps/rsm/src/` instead of `<repo>/backend/src/`).

Gate script update per Phase 4 — one line each:

```python
# tools/verification/check_boundaries.py
ROOT = Path(__file__).resolve().parents[2] / "apps" / "rsm" / "src" / "rsm"

# tools/verification/check_forbidden_deps.py
SCAN_DIRS = [
    ROOT / "apps" / "rsm" / "src" / "rsm",
    ROOT / "frontend" / "web" / "src",
    ROOT / "packages" / "rsm-client" / "src",
]

# tools/verification/check_pymupdf_import.py
SRC = ROOT / "apps" / "rsm" / "src" / "rsm"
PYPROJECT = ROOT / "apps" / "rsm" / "pyproject.toml"

# tools/verification/check_no_agent_tools.py
DEFAULT_SRC = ROOT / "apps" / "rsm" / "src" / "rsm"
```

Everything else in those scripts is unchanged.

---

## 3. Phase-by-phase execution

Each phase ends with a **gate** — a specific command whose exit status is the only thing that advances to the next phase. If the gate fails, you stop and fix before continuing.

### Phase 0 — snapshot & workspace bootstrap

1. From a fresh clone of `v6.1-export`, create `D:\OneShot\` as the new working directory.
2. `git init && git add -A && git commit -m "import rsm-v6.1 baseline"` — this is your rollback anchor.
3. Write a **workspace** `pyproject.toml` at the root:

   ```toml
   [tool.uv.workspace]
   members = ["apps/rsm", "apps/oneshot"]

   [tool.ruff]
   line-length = 100
   target-version = "py311"

   [tool.pytest.ini_options]
   # per-app pytest configs live in apps/*/pyproject.toml;
   # this root key is for the cross-app tests/ tree only.
   testpaths = ["tests"]
   asyncio_mode = "auto"
   ```

   **Note:** the root manifest has NO `[project]` section — that is intentional under `uv` workspaces. The two apps carry their own `[project]`.
4. `uv lock` → generates `uv.lock` at the root.
5. **Gate:** `uv run python -c "print('workspace ok')"` succeeds.

### Phase 1 — move RSM into `apps/rsm/`

1. `mkdir -p apps/rsm/src apps/rsm/tests`
2. `git mv backend/src/rsm apps/rsm/src/rsm`
3. `git mv tests/backend apps/rsm/tests` (per-app tests)
4. `git mv backend/tools tools/verification` (CI gates to the workspace level)
5. `mv backend/README.md docs/architecture/rsm.md` **if** such a file exists (none exists in v6.1; create a stub pointing to `docs/`).
6. Delete the empty `backend/` directory.
7. Write `apps/rsm/pyproject.toml`:

   ```toml
   [project]
   name = "rsm"
   version = "0.0.0"
   description = "RSM V6.1 — Replay State Memory authoritative daemon."
   requires-python = ">=3.11"
   dependencies = [
     "fastapi[standard] >= 0.142",
     "pydantic >= 2.13",
     "pymupdf >= 1.28",
     "mcp >= 2.2",
   ]
   [project.optional-dependencies]
   dev = ["pytest", "pytest-asyncio", "ruff", "mypy", "httpx"]
   [project.scripts]
   rsm = "rsm.cli.main:main"

   [build-system]
   requires = ["setuptools>=68", "wheel"]
   build-backend = "setuptools.build_meta"

   [tool.setuptools.packages.find]
   where = ["src"]

   [tool.pytest.ini_options]
   testpaths = ["tests"]
   asyncio_mode = "auto"
   ```

8. Update the four gate scripts' `ROOT`/`SRC` lines per §2 above.
9. `apps/rsm/src/rsm/__main__.py` — new 3-line file:

   ```python
   from rsm.cli.main import main
   if __name__ == "__main__":
       raise SystemExit(main())
   ```

10. **Gate:**

    ```bash
    cd D:\OneShot
    uv sync
    uv run --package rsm pytest -q apps/rsm/tests        # expect: 324 passed
    uv run python tools/verification/check_boundaries.py
    uv run python tools/verification/check_forbidden_deps.py
    uv run python tools/verification/check_pymupdf_import.py
    uv run python tools/verification/check_no_agent_tools.py
    ```

    All five must be green. **No source file under `apps/rsm/src/rsm/` is modified in this phase** — only moved. If pytest shows anything other than 324 passed, the move is wrong; revert and redo.

### Phase 2 — stand up `apps/oneshot/` empty

1. `mkdir -p apps/oneshot/src/oneshot apps/oneshot/tests/unit`
2. `apps/oneshot/pyproject.toml`:

   ```toml
   [project]
   name = "oneshot"
   version = "0.0.0"
   description = "OneShot — host application shell over RSM."
   requires-python = ">=3.11"
   dependencies = [
     "rsm",   # resolved via the uv workspace
   ]
   [project.optional-dependencies]
   dev = ["pytest", "pytest-asyncio", "ruff", "mypy"]
   [project.scripts]
   oneshot = "oneshot.__main__:main"

   [build-system]
   requires = ["setuptools>=68", "wheel"]
   build-backend = "setuptools.build_meta"

   [tool.setuptools.packages.find]
   where = ["src"]
   ```

3. `apps/oneshot/src/oneshot/__init__.py` — empty.
4. `apps/oneshot/src/oneshot/__main__.py`:

   ```python
   """OneShot entrypoint — Phase 2 placeholder.

   The real OneShot shell is empty on this build. This file exists so
   `uv run oneshot --version` resolves and the workspace is discoverable.
   The next OneShot build task will fill it in.
   """
   from __future__ import annotations
   def main() -> int:
       print("oneshot 0.0.0 (shell placeholder)")
       return 0
   if __name__ == "__main__":
       raise SystemExit(main())
   ```

5. `apps/oneshot/tests/unit/test_placeholder.py` — one asserting-trivial test so pytest exits 0 cleanly.
6. **Gate:**

    ```bash
    uv run --package oneshot pytest -q apps/oneshot/tests   # 1 passed
    uv run oneshot                                          # prints the placeholder line, exit 0
    ```

### Phase 3 — split out `packages/rsm-client/`

1. `mkdir -p packages/rsm-client/src`
2. `git mv frontend/web/src/lib/rsm-client.ts packages/rsm-client/src/rsm-client.ts`
3. `packages/rsm-client/package.json`:

   ```json
   {
     "name": "@oneshot/rsm-client",
     "version": "0.0.0",
     "type": "module",
     "main": "src/rsm-client.ts",
     "types": "src/rsm-client.ts",
     "dependencies": {}
   }
   ```

4. Replace `pnpm-workspace.yaml` (root) with:

   ```yaml
   packages:
     - "frontend/web"
     - "packages/*"
   ```

5. In `frontend/web/package.json`, add:

   ```json
   "dependencies": {
     "@oneshot/rsm-client": "workspace:*"
   }
   ```

   And in `frontend/web/tsconfig.json`, add a path alias so TypeScript resolves it without rewrites:

   ```json
   "paths": {
     "@/lib/rsm-client": ["../../packages/rsm-client/src/rsm-client.ts"]
   }
   ```

6. **Every existing import of `@/lib/rsm-client` keeps working** because the path alias still resolves. Only `frontend/web/src/features/*` already uses `@/lib/rsm-client` (grep confirms); no renames.
7. **Gate:**

    ```bash
    cd frontend/web
    pnpm install
    pnpm exec tsc --noEmit --skipLibCheck
    pnpm exec eslint "src/**/*.{ts,tsx}"
    pnpm exec playwright test --list       # Playwright specs still discovered
    ```

    All four pass. Dev-host filesystem required for `pnpm install` — if you're on the same `overlayfs`-EIO sandbox the v6.1 build hit, use `HAND_AUTHORED.md`'s procedure.

### Phase 4 — root-level `tools/`, `tests/`, `store/`

1. `mkdir -p tools/dev tools/build tools/verification tests/integration tests/fixtures store/attachments store/buckets store/snapshots`
2. `tools/verification/` already has the four gates (moved in Phase 1).
3. Move the empty `attachment/` directory to `store/attachments/` (preserve the directory, it's a runtime target). Config change: `rsm.conf.toml.example` currently has `root = "./.rsm-store"`; add a note that production should set:

   ```toml
   [persistence]
   root = "./store/buckets"

   [loading]
   attachment_dir = "./store/attachments"
   ```

   The config schema already supports this (`backend/src/rsm/config/schema.py:Persistence.root`); no code change needed.
4. `store/snapshots/` stays empty — reserved for V3.x Snapshot persistence (ADR 0015 deferral). Add `store/snapshots/.gitkeep` with a one-line note.
5. `tests/integration/README.md`: *"Cross-app wiring tests live here when OneShot is wired to RSM. Empty in v6.1."*
6. **Gate:** `find store tools tests -type d | sort` matches the end-state tree in §1.

### Phase 5 — thin `health.py` + `replay.py` routers (the user's tree asks for them explicitly)

v6.1 serves health via `GET /healthz` directly on the app, and replay via `/v1/interactions/{id}/stream`. The user's end-state has split routers. Two tiny shims:

1. `apps/rsm/src/rsm/api/routers/health.py`:

   ```python
   """Health endpoint — thin router that mirrors the inline /healthz."""
   from fastapi import APIRouter
   router = APIRouter()

   @router.get("/healthz")
   async def healthz() -> dict:
       return {"status": "ok", "schema_version": "1"}
   ```

2. `apps/rsm/src/rsm/api/routers/replay.py`:

   ```python
   """Replay router — thin re-export of interaction streaming.

   /v1/interactions/{id}/stream is the authoritative replay surface
   (ADR 0010). This router exists only so the OneShot repo layout
   matches the published tree; it adds no new endpoints.
   """
   from fastapi import APIRouter
   from .interactions import router as _interactions_router
   router = _interactions_router
   ```

3. `apps/rsm/src/rsm/api/app.py` — replace the inline `/healthz` with `app.include_router(health.router)`. Do NOT also mount `replay.router`; it is an alias of `interactions.router`.
4. **Gate:**

    ```bash
    uv run --package rsm pytest -q apps/rsm/tests          # still 324 passed
    uv run --package rsm pytest -q apps/rsm/tests -k health_endpoint
    curl -s http://127.0.0.1:8787/healthz    # (only if daemon running)
    ```

   If any test fails, the shim is wrong — the inline-healthz test (`test_api_v1_full.py`) must still pass byte-identically.

### Phase 6 — `.github/workflows/`

1. `.github/workflows/ci.yml` — single-job CI covering everything:

   ```yaml
   name: ci
   on:
     push: { branches: [main] }
     pull_request:
   jobs:
     test:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: astral-sh/setup-uv@v3
         - run: uv sync --all-packages
         - run: uv run --package rsm pytest -q apps/rsm/tests
         - run: uv run python tools/verification/check_boundaries.py
         - run: uv run python tools/verification/check_forbidden_deps.py
         - run: uv run python tools/verification/check_pymupdf_import.py
         - run: uv run python tools/verification/check_no_agent_tools.py
         - uses: pnpm/action-setup@v4
           with: { version: 9 }
         - uses: actions/setup-node@v4
           with: { node-version: 20 }
         - run: pnpm install --frozen-lockfile
           working-directory: frontend/web
         - run: pnpm exec tsc --noEmit --skipLibCheck
           working-directory: frontend/web
         - run: pnpm exec eslint "src/**/*.{ts,tsx}"
           working-directory: frontend/web
   ```

2. `.github/workflows/deploy.yml` — placeholder:

   ```yaml
   name: deploy
   on: workflow_dispatch
   jobs:
     noop:
       runs-on: ubuntu-latest
       steps:
         - run: echo "No deploy target configured in v6.1. See docs/architecture/overview.md."
   ```

3. **Gate (local pre-flight before pushing):**

   ```bash
   # Simulate what CI will run, locally:
   uv sync --all-packages
   uv run --package rsm pytest -q apps/rsm/tests
   uv run python tools/verification/check_boundaries.py
   uv run python tools/verification/check_forbidden_deps.py
   uv run python tools/verification/check_pymupdf_import.py
   uv run python tools/verification/check_no_agent_tools.py
   (cd frontend/web && pnpm exec tsc --noEmit --skipLibCheck && pnpm exec eslint "src/**/*.{ts,tsx}")
   ```

   All green = push.

### Phase 7 — final cleanup & doc map

1. Prune empty originals: `rmdir backend` (only if empty); delete `pnpm-workspace.yaml` old copy (replaced in Phase 3) and the old `pyproject.toml` content (replaced in Phase 0).
2. `README.md` at the root — rewrite to a 50-line map pointing at:
   - `apps/rsm/` → the Replay State Memory daemon
   - `apps/oneshot/` → the OneShot host shell
   - `frontend/web/` → the Next.js UI
   - `packages/rsm-client/` → the browser TypeScript client
   - `docs/` → architecture + ADRs
   - `tools/verification/` → the four CI gates
3. `docs/architecture/overview.md` — update the one path reference it has (if any). The content is unchanged; the file position is unchanged (already under `docs/`).
4. `docs/architecture/boundaries.md` — **new file** (one-page) capturing the `check_boundaries.py` rules in prose, so a reader understands why packages can't import each other. Content: paste the FORBIDDEN map and the one-liner for each package. 60 lines max.
5. `docs/architecture/rsm.md` — one-line stub pointing to `apps/rsm/README.md`.

6. **Final gate — the full matrix:**

   ```bash
   # 1. Backend
   uv run --package rsm pytest -q apps/rsm/tests
   # expect: 324 passed

   # 2. OneShot shell placeholder
   uv run --package oneshot pytest -q apps/oneshot/tests
   uv run oneshot

   # 3. CI gates
   uv run python tools/verification/check_boundaries.py
   uv run python tools/verification/check_forbidden_deps.py
   uv run python tools/verification/check_pymupdf_import.py
   uv run python tools/verification/check_no_agent_tools.py

   # 4. Frontend
   (cd frontend/web && pnpm install --frozen-lockfile)
   (cd frontend/web && pnpm exec tsc --noEmit --skipLibCheck)
   (cd frontend/web && pnpm exec eslint "src/**/*.{ts,tsx}")

   # 5. Playwright (dev-host only)
   (cd frontend/web && pnpm exec playwright test)
   ```

   If any of those nine commands fails, that specific step is the fix target; do not continue.

---

## 4. What is deliberately NOT in this plan

| Thing | Why not |
|---|---|
| Renaming `rsm.*` to `oneshot.rsm.*` | 25 import prefixes × dozens of files = pure churn with zero functional change. Package-under-app layout accomplishes the same organisational goal. |
| Nesting `rsm.bucket` under `rsm.domain.bucket` | Breaks `check_boundaries.py`, every ADR cross-reference, every test import. **The user's tree shows these as *visual* groupings; the plan preserves the actual package names and leaves the visual mapping to `docs/architecture/`.** |
| Pulling the four gate scripts into pytest plugins | They're pytest-independent on purpose (ADR 0001 / Spec §6). Keep them as scripts; CI invokes them separately. |
| Introducing a `src/rsm_core/` + `src/rsm_api/` split | `check_boundaries.py` already enforces that split at the subpackage layer. A physical split would duplicate the gate. |
| Adding an `agent/` or `tools/agent/` module to RSM | Forbidden by ADR 0002 / 0008 / 0017 and now by the `check_no_agent_tools.py` gate. OneShot owns anything agent-shaped; RSM stays agent-free. |
| Writing a `rsm-cli` *second* script in `apps/rsm/` | `rsm.cli.main:main` already exists and is wired via `[project.scripts]`. Just promote it. |
| Removing `rsm.conf.toml.example` | Still the config template consumers edit. Keep next to `apps/rsm/pyproject.toml`. |

---

## 5. Risk map

| Risk | Likelihood | Early signal | Mitigation |
|---|---|---|---|
| `pytest` loses discovery after move | Medium | `collected 0 items` after Phase 1 | `apps/rsm/pyproject.toml` sets `[tool.pytest.ini_options] testpaths = ["tests"]`; always run `uv run --package rsm pytest -q apps/rsm/tests`, never `pytest` from the root. |
| `check_boundaries.py` false negatives after path change | Medium | Gate exits 0 but a known bad import sneaks in | Add a one-off sanity test: deliberately introduce `from rsm.bucket import ... in rsm.cli` on a scratch branch, confirm the gate fails. (You already have `test_no_agent_tool_subsystem.py` as a model for the negative test pattern.) |
| `frontend` cannot resolve `@oneshot/rsm-client` under pnpm workspace | Medium | `pnpm install` complains or `tsc` prints `Cannot find module`. | Use the tsconfig path alias (Phase 3 step 5). Avoids depending on `pnpm` symlink materialisation on Windows where `rename`-across-dirs can EIO. |
| CI runs on Linux but a Windows contributor can't reproduce | Low | Playwright passes in CI, fails locally | README documents the Windows path for `pnpm install` and references `frontend/web/HAND_AUTHORED.md` which already covers it. |
| `uv.lock` drifts between apps | Low | `uv sync` warns `lockfile out of date` | Only `uv lock` at the workspace root; never run it per-app. |
| `backend/` left half-moved | Low | `check_pymupdf_import.py` reads from the old path and silently passes | Script's `SRC = ROOT / "apps" / "rsm" / "src" / "rsm"` is a required Phase-1 edit; the final-gate step runs it from the new path, so a missed edit fails loudly. |

---

## 6. Order of operations summary (so you can tick boxes)

- [ ] Phase 0 — `D:\OneShot\` initialised, `uv.lock` at root
- [ ] Phase 1 — `backend/src/rsm/` → `apps/rsm/src/rsm/`; `tests/backend/` → `apps/rsm/tests/`; `backend/tools/` → `tools/verification/`; four gates still green on new paths
- [ ] Phase 2 — `apps/oneshot/` empty shell exists with placeholder entrypoint
- [ ] Phase 3 — `frontend/web/src/lib/rsm-client.ts` → `packages/rsm-client/src/rsm-client.ts`; tsc + eslint still clean
- [ ] Phase 4 — `tools/{dev,build,verification}/` and `tests/{integration,fixtures}/` and `store/{attachments,buckets,snapshots}/` created
- [ ] Phase 5 — `apps/rsm/src/rsm/api/routers/{health,replay}.py` added; same 324 tests still pass
- [ ] Phase 6 — `.github/workflows/{ci,deploy}.yml` added; local pre-flight matches CI
- [ ] Phase 7 — `README.md` + `docs/architecture/{boundaries,rsm}.md` written; empty old dirs removed; final 9-step gate green

**Totals when all phases complete:**

- Files added: ~15 (two app manifests, root manifest, four workflow / shim / docs files, five placeholder `__init__.py` / `__main__.py`, three `.gitkeep`, one README refresh)
- Files moved: ~160 (RSM source tree + tests + four gate scripts + `rsm-client.ts`)
- Files modified: 5 (four gate scripts' root path, one `apps/rsm/src/rsm/api/app.py` include-router line)
- Files deleted: 2 (old root `pyproject.toml`, old `backend/` empty directory)
- Test count: still **324 passed**
- Gate count: still **4 of 4 green**
- RSM Core behaviour: **unchanged** (byte-identical source under `apps/rsm/src/rsm/`)

---

## 7. If you want the "visual grouping" from your tree (`domain/`, `ingestion/`, `infrastructure/`) as *real* packages

This is choice **D2 = re-nest**. Add Phase 1b between 1 and 2:

1. Create umbrella `__init__.py` files that **re-export** the flat packages:

   ```python
   # apps/rsm/src/rsm/domain/__init__.py
   from rsm import bucket, classification, integrity, lifecycle, replay
   __all__ = ["bucket", "classification", "integrity", "lifecycle", "replay"]
   ```

   ```python
   # apps/rsm/src/rsm/ingestion/__init__.py
   from rsm import extraction, loading, normalization, prepared
   __all__ = ["extraction", "loading", "normalization", "prepared"]
   ```

   ```python
   # apps/rsm/src/rsm/infrastructure/__init__.py
   from rsm import config, transports, daemon
   __all__ = ["config", "transports", "daemon"]
   ```

2. **Do not** physically move modules. The umbrellas are *aliases*. All existing imports (`from rsm.bucket.serializer import ...`) stay valid; new code may optionally use `from rsm.domain.bucket.serializer import ...` because `rsm.domain.bucket` IS `rsm.bucket` by `__init__.py` re-export.

3. Update `check_boundaries.py` FORBIDDEN map to also exclude the new umbrella names — a four-line addition since the three umbrellas themselves import nothing forbidden.

4. **Gate:** the same 324-pass pytest + four gates. Zero functional change; the umbrellas are discoverability sugar.

**Cost:** ~15 extra lines total. **Benefit:** `rsm.domain.*` / `rsm.ingestion.*` / `rsm.infrastructure.*` appear as import paths without actually re-nesting the files on disk — matches the "and so on" in your request without rewriting the whole codebase.

---

## 8. One-line verdict

The refactor is **mostly `git mv` plus five small writes**. The baseline (`rsm-v6.1-export.zip` → `ppf.01a10583…`) already runs 324 passed + 4 gates; after each phase that same 324/4 result is the only exit condition that matters.
