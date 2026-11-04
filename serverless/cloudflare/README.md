# Cloudflare Worker gateway

A minimal, isolated Cloudflare Workers deployment starter. This is **not** the
OneShot Python Host Controller or a functional MCP endpoint.

## Verified interface contract

- `GET /health`: returns a JSON health response.
- Other requests: return HTTP 404.
- No authorization, task routing, host connection, or build execution is enabled.

## Deploy from GitHub

1. In GitHub Settings > Environments, create `cloudflare` and configure
   required reviewers if desired.
2. Add Actions secrets `CLOUDFLARE_API_TOKEN` (scoped to Workers deployment)
   and `CLOUDFLARE_ACCOUNT_ID`. Never commit credentials.
3. Merge the reviewed branch into `main`.
4. Run Actions > Deploy Cloudflare Worker > Run workflow.
5. Check the deployment URL from the action output and request `/health`.

Deployment is manual by design, and the existing Python CI stays unchanged.
Do not add proxy routes or MCP methods until the host integration and
authorization contracts have been reviewed.
