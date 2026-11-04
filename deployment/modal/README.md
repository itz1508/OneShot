# Modal serverless deployment starter

This is an isolated Modal deployment entry point for OneShot. It does **not**
replace the Python Host Controller, implement MCP, start Builder sandboxes, or
issue host authorization receipts. The only deployed function is a GET health
endpoint; it does not accept task input or execute arbitrary code.

## Deployment

1. In GitHub Settings > Environments, create the `modal` environment. Add
   required reviewers if desired.
2. Create a limited-permission Modal service-user token authorized for the
   intended Modal environment.
3. Set GitHub Actions secrets `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`.
4. Merge the reviewed changes into `main`.
5. Run **Actions > Deploy Modal Serverless > Run workflow**.
6. Use the URL reported by Modal to verify the endpoint returns
   `{ "status": "ok", "service": "oneshot-serverless" }`.

The deploy is manual so no cloud resources are created merely by pushing a
commit. Modal SDK is pinned to 1.6.3 in this standalone GitHub workflow; it
is intentionally not added to OneShot's existing `pyproject.toml` / `uv.lock`.

## Integration boundary

Modal Sandboxes may be used for authorized Build execution in a subsequent
host-integration task. Do not expose sandbox creation over the public health
endpoint or permit Builder execution without frozen Plan and Build Admission
receipts, scoped permissions, checkpoint/reconciliation handling, and E2E
verification.
