# OneShot Modal deployment

This repository now includes two separate Modal surfaces:

- `modal_app.py` — the Modal ASGI deployment that reuses `mvp.api:app` and serves `live.html` plus `/api/*` from the same origin.
- `deployment/modal/app.py` — the standalone sandbox boundary used for Modal serverless validation and the isolated health endpoint.

## What is deployed

### ASGI app

- The existing API, including task creation, Research/Audit execution, event streaming, and artifact access.
- The same FastAPI app also serves `GET /live.html` and redirects `/` to that page.
- Durable task/session state is stored in a Modal Volume mounted at `/data`.

### Standalone sandbox boundary

- A separate Modal health endpoint for the sandbox layer.
- A separate read-only GitHub example that does not expose host workflow authority.

## Files added

- `modal_app.py` — Modal ASGI entrypoint.
- `mvp/api.py` — serves `live.html` from the repository bundle.
- `deployment/modal/app.py` — standalone Modal sandbox boundary.
- `deployment/modal/github_clone.py` — optional read-only Modal GitHub example.
- `deployment/modal/README.md` — standalone deployment notes.
- `.github/workflows/deploy-modal.yml` — manual Modal deploy workflow.

## Environment

Modal should provide or mount the following at deploy time for the ASGI app:

- `ONESHOT_STATE_ROOT=/data`
- optional `ONESHOT_ALLOWED_HOSTS`
- optional `ONESHOT_WEB_ORIGIN_REGEX`

The backend still uses the existing host-owned workflow contract. No new login system was introduced.

## Deploy

Typical Modal deployment flow:

1. Confirm the existing Modal workspace/App is the one you want to reuse.
2. Keep your isolated build work in a Sandbox.
3. Deploy the ASGI app from `modal_app.py`.
4. Open the HTTPS endpoint and verify:
   - `GET /api/health`
   - `POST /api/tasks`
   - `POST /api/tasks/{id}/research` or `/audit`
   - `GET /api/tasks/{id}/stream`
   - `GET /live.html`

## Notes

- `live.html` is now served from the same origin as the API, so its `/api/*` calls work without a separate host.
- If your Modal app uses a different domain, set `ONESHOT_ALLOWED_HOSTS` and `ONESHOT_WEB_ORIGIN_REGEX` accordingly.
- Keep build-only operations in the Sandbox; use the deployed App only for the live HTTPS endpoint.
