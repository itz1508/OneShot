# ADR 0018 — Single-host Docker Compose deployment (GHCR images, gated deploy)

**Status:** v6.1 deployment baseline. Binding for the deploy path.

## Context

The repository shipped with **no deploy target**: `.github/workflows/deploy.yml`
was a `noop` job, the RSM daemon read configuration only from built-in
defaults, and the frontend hard-coded the daemon base URL. The §10 / ADR 0001
posture is explicit: RSM is the single authority and nothing about it is
exposed beyond loopback.

Three concrete gaps had to close before any host could run this:

1. no config file resolution (daemon root, CORS origins were settings-only),
2. no packaging artifacts (Dockerfiles, compose topology),
3. no build → release → deploy path with a way back (rollback).

## Decision

**Docker Compose on one self-hosted Linux host, GHCR images, gated deploy.**

- **Topology** (`docker-compose.yml`): two services — `rsm` (FastAPI/uvicorn
  factory app) and `web` (Next.js `next start`) — on one host, with the named
  volume `rsm-store` mounted at `/data` for the daemon's store
  (`/data/buckets`, `/data/events.log`).
- **Loopback publishes only.** Compose publishes `127.0.0.1:8787:8787` and
  `127.0.0.1:3000:3000`. Inside the containers the processes bind `0.0.0.0`
  (required for the published port to work); the host edge stays loopback, so
  the ADR 0001 posture is preserved unchanged. The browser on the host is the
  cross-origin client, allowed only via the fail-closed CORS allow-list
  (`[daemon] allowed_origins` in the mounted config).
- **Configuration** is a file, not env soup: `deploy/rsm.conf.toml` is
  mounted read-only at `/etc/rsm/rsm.conf.toml` and selected with
  `RSM_CONFIG` (the only environment variable the daemon reads; resolution
  order lives in `rsm.config.runtime`). Unknown keys/sections fail closed.
- **Images**: `deploy/Dockerfile.api` (python:3.14-slim, pinned `uv`,
  `uv sync --frozen --no-dev`, non-root uid 10001) and `deploy/Dockerfile.web`
  (node:20, corepack pnpm per `packageManager`, non-root `node`, production
  `next build`). `NEXT_PUBLIC_RSM_BASE_URL` is a **build argument** because
  Next.js inlines it; changing the UI's target requires rebuilding the image.
- **Release path** (`deploy.yml`): pushes of `v*` tags and manual dispatches
  build and push both images to GHCR (`ghcr.io/<owner>/oneshot-rsm`,
  `ghcr.io/<owner>/oneshot-web`; tags `sha-<12>` plus `latest`, gha layer
  cache). A dispatch with a `version` input deploys an existing tag without
  rebuilding.
- **Deploy path**: the deploy job runs on the host itself through a
  **self-hosted runner labeled `oneshot`** — outbound-only, no inbound ports —
  behind the `production` environment gate. It runs `deploy/deploy.sh`, which
  records the previously running tag (`.deploy-prev-tag`), pulls the pinned
  images (`deploy/compose.prod.yml` override), restarts the stack, smokes
  `127.0.0.1:8787/healthz` + `127.0.0.1:3000/` for up to 60 s, and
  **automatically rolls back to the previous tag** when smoke fails
  (`deploy/deploy.sh --rollback` is also available to operators).
- **Repository hygiene**: `.gitattributes` pins LF for all text files —
  `deploy/deploy.sh` runs under bash, and Dockerfiles/compose/CI YAML must be
  byte-identical across platforms.

## Consequences

- A single host has no HA and no rolling updates; a deploy is a short
  restart of both containers. Data survives in the `rsm-store` volume.
- Changing the UI's daemon URL or the allowed origins is a config/image
  change plus a redeploy — deliberate, not dynamic.
- Interaction state remains in-memory (ADR 0009/0015): after any restart the
  interaction surface resets to fail-closed OFF. This is expected, not a
  deployment defect.
- Rollback is real: previous image tag, previous config file, same volume.

## Verification

- `docker compose config --quiet` — exit 0 (base + `deploy/compose.prod.yml`
  override with test images/tag).
- `bash -n deploy/deploy.sh` — exit 0; all new YAML parses.
- `next build` (Next 16.3.8, **Turbopack** — the Next 16 default; resolved the
  earlier `--webpack` vs `--turbopack` question) — exit 0 on a standard
  filesystem: compile 22.8 s, types 4.8 s, routes `/`, `/_not-found`, `/chat`.
- RSM suite + cross-app + OneShot suites, 4 verification gates, frontend
  tsc/eslint (0 findings), `playwright --list` (9 tests) — all green; CI now
  runs all of these on every push/PR plus both image builds (Dockerfiles are
  additionally exercised by the new `docker` CI job; the Windows dev host had
  no Docker daemon, so the first real image build happens in CI).
- Deferred, tracked: adopting the full ruff default ruleset as a CI gate
  (baseline has pre-existing style findings; CI currently gates on the
  syntax/undefined-name subset only).
