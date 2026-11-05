# OneShot — Modal ASGI Audit Demo Deployment

**Implementation:** `modal_app.py` wraps the existing `mvp.api:app`, serving the same-origin `/live.html` and `/api/*` routes. **Deployment:** unverified until an authenticated Modal execution returns a real HTTPS URL and live acceptance checks pass.

## Deploy without rebuilding the architecture

The App is the API serving layer; the Modal Sandbox is independent, isolated Builder execution. No new login system, server implementation, or competing API is introduced.

The newer `main` branch also contains a **separate** health-only entrypoint `deployment/modal/app.py`, its read-only reference files, and `.github/workflows/deploy-modal.yml`. That deployment is *not* the OneShot ASGI API. This document and `.github/workflows/modal-deploy.yml` apply only to `modal_app.py`; keep both workflows distinct, do not deploy the health-only app in place of the API, and do not change the standalone package as part of this repair.

1. In the authorized Modal workspace, inspect existing resources before creating any: `modal app list --json`, `modal app info <app>`, `modal volume list`. For named Sandboxes, use `modal.Sandbox.list()`/`from_name()` or the Modal dashboard. Preserve any existing Sandbox and Volume.
2. Reuse their names via `ONESHOT_MODAL_APP_NAME` and `ONESHOT_MODAL_VOLUME_NAME` in the deploying process; defaults are `oneshot` and `oneshot-state`.
3. Ensure the executor is authenticated with `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` (or an active Modal CLI profile). **Proxy tokens are not deployment credentials.** Never put tokens in Git or browser JavaScript.
4. Use `modal deploy --strategy recreate modal_app.py` to avoid a rolling-overlap period where two deployment revisions could modify the same SQLite files.
5. Capture the **actual** HTTPS URL printed by Modal. Do not infer an endpoint from the App name.

A manual workflow is provided at `.github/workflows/modal-deploy.yml` for execution by a GitHub Actions runner **after that workflow is available on the default branch**. It requires GitHub Actions secrets `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`; its dispatch inputs identify the existing App and Volume. It does not attach a model secret. The workflow inspects resources, deploys, and gates completion on live Python API/SSE and Chromium browser checks. On a development branch, the authenticated subagent may execute the same commands directly rather than claiming the task impossible because its parent chat cannot run Modal CLI.

## Bundled source and working API

The image uses the existing `uv.lock` with the `meta` and `mvp` extras. Modal's `uv_sync` does **not** install the local project, so the entrypoint mounts the needed packages and runtime assets under `/root/oneshot-source` and adds that directory to `PYTHONPATH`.

The source bundle includes `agent/`, `mvp/`, `api_fundamentals/`, `.agents/`, `settings/`, and `web/`, excluding local `.env*`, dependencies, browser results and build outputs. `live.html` is served from `web/public`. No virtual environment is inside the scanned workspace.

At runtime, before importing `mvp.api`, `web()` sets:

- `ONESHOT_STATE_ROOT=/data` — backed by the existing named Modal Volume.
- `MCP_WORKSPACE_ROOT=/root/oneshot-source` — source bundle for the read-only Audit scanner.
- `MCP_TRUSTED_ANCESTRY=true` — host-controlled assertion for this specific immutable deployment bundle, **not** permission to scan arbitrary paths.

The public demo does **not** attach `MODEL_API_KEY` or configure an MCP Research transport. Its `POST /api/tasks/{id}/research` route is explicitly denied with HTTP 403, even if a transport leaks into the process environment. For private deployments, set `ONESHOT_MODAL_PRIVATE_MODE=true` and optionally `ONESHOT_MODAL_MODEL_SECRET=<existing-secret-name>`; the code rejects attaching model credentials without private mode. Native Modal `asgi_app(requires_proxy_auth=True)` then requires Modal proxy-auth headers, which protect the API without adding a OneShot login system. Private-mode browser `EventSource` cannot supply those headers directly; do not claim that `live.html` supports private proxy-auth sessions. Model-backed Research still requires a separately deployed, actually connected MCP server; a model key is insufficient by itself. `GET /api/health` should return `mcp_transport_configured=false` in the public demo.

## Concurrency and persistence

`@modal.concurrent(max_inputs=20)` is required because `live.html` holds `GET /api/tasks/{id}/stream` (SSE) open while issuing `POST /audit`. Without it, `max_containers=1` can deadlock at the input queue. This retains one container while allowing simultaneous requests in that container. Mutating HTTP requests and their `Volume.commit()` calls are serialized by a container-local `asyncio.Lock`; SSE and GET remain concurrent. This does not provide cross-container isolation or distributed locking.

`max_containers=1` prevents unrestricted multi-container access to the same SQLite files. The write-response middleware issues `Volume.commit()` after `POST`/`PATCH`, and a failed commit prevents a successful response. This is an MVP workaround, **not** cross-process transactionality or proof of crash consistency. Modal Volumes explicitly warn against concurrent writes to the same files. Test restart/reconciliation against the actual backend, and migrate to a transactionally coordinated store before horizontal scaling.

## Verification gates

```bash
# Run in the authenticated deployment workspace:
modal deploy --strategy recreate modal_app.py
python3 scripts/modal_live_probe.py --base-url "https://ACTUAL-ENDPOINT.modal.run"

# Run browser tests against that same real endpoint:
cd web
npm ci
npx playwright install chromium
MODAL_BASE_URL="https://ACTUAL-ENDPOINT.modal.run" npx playwright test --config=playwright.modal.config.js
```

The automated Python probe asserts same-origin page/API reachability, MCP disabled, task creation, real SSE connected while Audit POST completes, persisted artifact, task restoration and event replay. The deployment workflow then uses `modal app rollover --strategy recreate` and `--verify-task-id` to independently read the **same** task, Audit artifact and events from a replacement container. The Chromium test submits from `live.html`, requires real completion and confirms reload restores the result. Neither test represents an active model-backed MCP nor the Builder Sandbox.

Separate deployment acceptance still requires verified Modal workspace identity, actual image build, App revision, deployment logs and test evidence; the workflow now executes the replacement-container recovery check when it runs successfully. Mark each missing check as `NOT_VERIFIED`. Never label Modal or six-stage OneShot E2E as complete based on repository CI alone.

### Exposure

The public demo currently has no end-user login and is not a general-purpose authenticated production API. Its Audit endpoint reads the deliberately bundled source and may still be abused for resource consumption or expose source-derived findings. Keep the source bundle non-sensitive; limit public exposure, add operator-approved edge controls/rate limits before broader public use, and do not attach model credentials to this unprotected API.
