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
5. Run **Actions > Deploy Modal Serverless > Run workflow**, entering the
   target Modal environment name. For the supplied dashboard URL this appears
   to be `OneShot`; verify the name in Modal before executing.
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

## Optional read-only GitHub inspection

`github_clone.py` is a separate Modal App, **not** exposed as a public
endpoint and **not** deployed by the default health workflow. It uses a
separate Modal secret named `github-secret`, containing `GITHUB_TOKEN`.
Grant the token only read access to the repositories it must inspect.

Create this Modal secret in the dashboard; do not upload `.env` or paste
credentials into GitHub source. Then run:

```sh
modal run --env <modal-environment> deployment/modal/github_clone.py --repo-url https://github.com/<owner>/<repo> --branch main
```

The function validates GitHub repository URLs, avoids embedding credentials
in clone URLs, and removes the temporary checkout before returning. It only
returns top-level names and does not modify the remote repository.

`MODAL_PROXY_TOKEN_ID` / `MODAL_PROXY_TOKEN_SECRET` authenticate requests
to protected inference endpoints. They do **not** deploy Modal Apps.
Deployment requires `MODAL_TOKEN_ID` (`ak-`) and `MODAL_TOKEN_SECRET` (`as-`).

## Credentials and readiness

The GitHub Actions deployment workflow requires a complete Modal API token
pair (`MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET`). Webhook proxy tokens cannot
be used for deployment. A token ID without its matching secret is insufficient.

The optional `github_clone.py` example needs a **separate** Modal Secret
named `github-secret` containing `GITHUB_TOKEN`. Neither the GitHub token
nor the Modal token pair belongs in a committed `.env` file.

CI and syntax validation do not prove the Modal workspace environment exists,
that secrets have been provisioned, or that deployment and authenticated
GitHub operations work. Those claims require live runtime evidence.
