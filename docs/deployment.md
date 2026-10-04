# Deployment — single host, Docker Compose

**Status:** binding for v6.1 (ADR 0018). Scope: one self-hosted Linux host
running the RSM daemon and the local-first Next.js UI as two containers.

## Topology

```
host (Linux, loopback edge)
├── 127.0.0.1:8787 → rsm  container   FastAPI/uvicorn factory app
│                     ├── /etc/rsm/rsm.conf.toml   (deploy/rsm.conf.toml, read-only)
│                     └── /data                     named volume `rsm-store`
│                            └── buckets/ + events.log
└── 127.0.0.1:3000 → web  container   next start (production build)
```

Nothing is published beyond loopback (ADR 0001 preserved). The browser on the
host is the cross-origin client; it is allowed only through the fail-closed
CORS allow-list in the mounted config. Inside the containers the processes
bind `0.0.0.0` — that is container-internal only and required for the
published port to work.

## Quick start (build from source on the host)

```bash
docker compose up --build -d          # daemon on 127.0.0.1:8787, UI on 127.0.0.1:3000
curl -fsS http://127.0.0.1:8787/healthz
docker compose ps                     # rsm should be healthy (healthcheck in compose)
docker compose logs -f rsm            # follow daemon logs
```

`docker compose down` stops the stack; the `rsm-store` volume survives.

## Configuration

`deploy/rsm.conf.toml` is mounted read-only at `/etc/rsm/rsm.conf.toml` and
selected with `RSM_CONFIG` — the only environment variable the daemon reads.
Precedence (see `rsm.config.runtime`): explicit argument → `RSM_CONFIG` →
`./rsm.conf.toml` → built-in defaults. Unknown keys/sections fail closed.

What to change per host:

- `[daemon] allowed_origins` — add `http://<lan-ip>:3000` if the UI will be
  browsed from another machine (then also change the `web` port publish, see
  below). Defaults allow only `localhost:3000` / `127.0.0.1:3000`.
- `[persistence] root = "/data"` — the compose volume. Keep it in sync with
  the volume mount if you change it.

Serving beyond loopback (deliberate, documented change):

- edit `docker-compose.yml` port publishes, e.g. `"3000:3000"` for the UI,
- add the matching origin to `allowed_origins` (exact scheme/host/port —
  CORS is fail-closed; a mismatch yields no `Access-Control-Allow-Origin`),
- **never** publish `8787` beyond loopback: the daemon is the authority
  surface and is meant to be reached only by the browser and local tooling.

The UI's daemon base URL (`NEXT_PUBLIC_RSM_BASE_URL`, default
`http://127.0.0.1:8787`) is **inlined at build time** (`frontend/web/src/lib/rsm.ts`);
changing it requires rebuilding the web image with the build-arg/`vars` value.

## CI (every push / PR)

`.github/workflows/ci.yml` — three jobs:

| job | runs |
|---|---|
| `test` | RSM suite, cross-app `tests/`, OneShot suite, the 4 verification gates, ruff syntax/undefined-name gate (`--select E9,F63,F7,F82`) |
| `frontend` | `pnpm install --frozen-lockfile` (root workspace), `tsc` (web), `eslint` (web), `tsc` (`@oneshot/rsm-client`), production `next build`, `playwright --list` spec integrity |
| `docker` | `docker compose config --quiet` + builds both deploy images |

Note for contributors: the `--basetemp=.tmp/pt` workaround used on the Windows
dev host is **not** needed in CI (normal `/tmp`).

## Releases (GHCR)

`deploy.yml` builds and pushes on `v*` tag pushes and on manual dispatch:

- `ghcr.io/<owner>/oneshot-rsm` and `ghcr.io/<owner>/oneshot-web`
- tags: `sha-<first 12 of the commit>` and `latest`
- UI base URL comes from repository variable `NEXT_PUBLIC_RSM_BASE_URL`
  (default `http://127.0.0.1:8787`).

## Deploy to the host

Prerequisites (one-time):

1. Register the host as a **self-hosted runner** with labels
   `self-hosted, linux, oneshot` (outbound-only; no inbound ports needed).
2. Install `docker` + compose plugin and `curl` on the host; the runner user
   must be in the `docker` group.
3. Optionally add protection rules / required reviewers to the `production`
   environment to gate deploys.

Then: **Actions → deploy → Run workflow** — leave `version` empty to build and
deploy the current commit, or pass an existing tag (`sha-<12>` / release tag)
to deploy it without rebuilding. The deploy job runs `deploy/deploy.sh`:

1. records the currently running tag in `.deploy-prev-tag` (repo checkout on
   the host),
2. `docker compose pull` + `up -d` using
   `-f docker-compose.yml -f deploy/compose.prod.yml`,
3. smokes `127.0.0.1:8787/healthz` and `127.0.0.1:3000/` for up to 60 s,
4. on failure: redeploys the recorded previous tag (or stops the stack when
   there is none) and exits non-zero — the workflow fails visibly.

Manual rollback (operator shell in the repo checkout on the host):

```bash
RSM_IMAGE=ghcr.io/<owner>/oneshot-rsm \
WEB_IMAGE=ghcr.io/<owner>/oneshot-web \
    bash deploy/deploy.sh --rollback
```

## Operations

- **Logs:** `docker compose logs -f rsm web` (`[logging] level` in the config
  controls daemon verbosity).
- **Backup:** everything durable lives in the `rsm-store` volume:

  ```bash
  docker run --rm -v oneshot_rsm-store:/data -v "$PWD":/backup alpine \
      tar czf /backup/rsm-store-$(date +%F).tgz -C /data .
  ```

- **Restore:** stop the stack, extract the tarball back into the volume,
  start again.
- **Upgrade:** run the workflow (above); rollback is automatic on smoke
  failure. **Config changes** are `deploy/rsm.conf.toml` edits + redeploy.
- **State note:** interaction state is in-memory by design (ADR 0009/0015);
  after any restart the interaction surface is fail-closed OFF. Buckets and
  the lifecycle event log persist in the volume.

## Repository hygiene

`.gitattributes` pins LF for all text files. `deploy/deploy.sh` **must stay
LF** — it runs under bash on Linux; never save it with CRLF.

## Known gaps / deferred

- The composed stack was first run on the Windows dev host (2026-10-04):
  both images build, `rsm` reports healthy, `/healthz` and `/` return 200, the
  fail-closed CORS allow-list echoes only `127.0.0.1:3000`, and the Playwright
  suite is **9/9 green** against the containers. GHCR push, the gated `deploy`
  job and `deploy/deploy.sh` itself still need their first execution on the
  self-hosted runner.
- Full ruff ruleset adoption is deferred (pre-existing style baseline);
  CI gates on the bug-class subset (`E9,F63,F7,F82`).
- No TLS/reverse-proxy, no orchestration, no multi-host — single-host scope
  by decision (ADR 0018).
