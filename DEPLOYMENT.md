# OneShot Modal deployment

**Status:** repository configuration only. A successful `modal deploy` and live HTTP checks are required before marking the deployment verified.

The Modal ASGI function reuses `mvp.api:app`; its root and `/live.html` routes are served by that same FastAPI app. The Modal Sandbox is a separate isolated Builder environment and is not required to start the ASGI server.

## Existing resource discovery

Run in the authenticated Modal workspace:

```bash
modal app list
modal volume list
modal secret list
```

Check which App, Volume, Sandbox and endpoint already belong to OneShot. The defaults in `modal_app.py` are `oneshot` and `oneshot-state`; set `ONESHOT_MODAL_APP_NAME` and `ONESHOT_MODAL_VOLUME_NAME` **in the deployment environment** if the existing resource names differ. Do not create duplicate application identities or delete an existing Volume.

## Image and runtime

`modal_app.py` installs the locked `meta` and `mvp` extras using `uv.lock` and mounts the local source and runtime assets: `agent/`, `mvp/`, `api_fundamentals/`, `.agents/`, `settings/`, and `web/public/`. The running container uses `/data` for `ONESHOT_STATE_ROOT`.

A named Modal Secret can be mounted by setting `ONESHOT_MODAL_MODEL_SECRET` to the **existing secret's name**, not the key value. That secret should contain the required `MODEL_API_KEY` and provider settings. Never pass credential files into source-control or print their contents. Deployment authorization requires a Modal authenticated profile or deployment API token, not a proxy token.

Research also requires a working MCP transport. Set exactly one of `ONESHOT_MCP_COMMAND` (plus `ONESHOT_MCP_ARGS_JSON`) or loopback `ONESHOT_MCP_URL` in the runtime environment. Merely mounting `MODEL_API_KEY` does **not** provide an MCP server. Package and connect the intended MCP server separately; do not substitute the test fixture for production Research.

## Deploy and check

```bash
modal deploy modal_app.py
```

Capture the actual HTTPS URL from the deployment output. Verify from the deployed endpoint (not a local TestClient):

1. `GET /` redirects to `/live.html`; `GET /live.html` returns HTML.
2. `GET /api/health` returns `status=ok`. `mcp_transport_configured=true` confirms configuration shape only, **not** live MCP connectivity.
3. `POST /api/tasks` returns a real task ID; `GET /api/tasks/{id}` restores the same task.
4. `GET /api/tasks/{id}/events` and `GET /api/tasks/{id}/stream` replay the persisted events, including on SSE reconnect.
5. With an authorized MCP server configured, `POST /api/tasks/{id}/research` (or `/audit` as appropriate) completes with independently validated artifacts.
6. Restart or replace the container and re-read the existing task and events to verify durable state.
7. Test the same flow through the deployed `live.html` browser interface and record the endpoint, logs, and verification evidence.

## Persistence and security boundaries

The ASGI function is limited to **one container** because the existing host stores mutable SQLite files in the Volume. The Modal-specific HTTP middleware calls `Volume.commit()` after mutating requests; this is an MVP durability measure, **not** a replacement for a transactional database or a guarantee against interrupted multi-process writes. Before increasing replicas, migrate the mutable state to an appropriately coordinated transactional store and repeat crash/restart tests.

The existing app does not implement end-user login. Do not publish a model-backed, unauthenticated task-execution API to untrusted users without an authorized edge access-control or equivalent protection. Keep tokens out of browser JavaScript.

Do not claim ASGI, MCP, Sandbox Builder, SSE or browser E2E success until actual deployment/runtime evidence exists.
