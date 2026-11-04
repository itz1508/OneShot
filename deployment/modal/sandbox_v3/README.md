# Modal Build Sandbox v3 — standalone implementation

**Scope:** disposable, offline, one-Sandbox-per-attempt execution of a host-supplied candidate text patch, bounded host-selected checks, complete observed-delta export and independent host-side verification. No OneShot imports, frontend, ASGI service, MCP, model calls, Build Admission issuer, or authoritative repository promotion.

## Safety boundary

- Candidate `.patch` and manifest carry **no authorization**. The invoking trusted host must already have verified Build Admission against exact task/plan/fixture/repository/command/profile revisions and immutable records. The local `profile_digest` is a coherence check, **not** host authorization.
- The standalone package additionally checks archive/bundle hashes, full tree, preimages, accepted file paths and command plan before remote resource creation. Any changed file outside admitted paths blocks success. The host independently recomputes export content and reproduces the patch against the accepted snapshot.
- Each Sandbox has `block_network=True`, no secrets, no volumes/mounts, no OIDC, no GPU, no exposed ports and no authoritative source checkout. Modal credentials remain in the trusted host process only.
- The initial applicator handles canonical UTF-8, same-path Git unified-diff **create/modify/delete**. Renames, binary content and chmod changes are rejected, not silently accepted. These are documented limitations requiring separately admitted future contracts.
- No automatic retries of uncertain effects. AttemptStore keeps durable pre-create intent, exact attempt identities, sandbox names/IDs and transition journal. An operator must reconcile and explicitly start a new attempt ID after an interruption.
- A valid Sandbox result is **not** OneShot final Build success. Integrated CAS promotion, independent E2E and trusted host receipts are outside this standalone package.

## Install and local checks

```sh
uv python install 3.11
uv lock
uv sync --locked --group dev
uv run pytest -q tests --ignore=tests/integration
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run python -m compileall -q src
```

`uv.lock` must be generated from this `pyproject.toml` and verified with `uv lock --check` in an environment that can access the package registry. Do **not** fabricate a lock. This delivery was created in a restricted Python 3.13 container without network access.

## Real Modal execution

1. Reuse an existing authorized Modal App if available. An operator may explicitly permit creation with `--create-app`; no resource is created by default.
2. Prebuild an immutable image with Python 3.11, Pydantic v2, pytest, and a `sleep` command. Resolve and pin its immutable Modal image object ID. No runtime network dependency downloads.
3. Have the trusted host create a deterministic source archive, candidate patch/manifest ZIP, exact expected source/preimage hashes, and an authorized `SandboxExecutionRequest` JSON. Use `archive_directory`, `build_candidate_bundle`, `commands_digest` and `profile_digest` as deterministic *serialization helpers*, **not** as authorization.
4. Validate offline: `modal-build-sandbox validate /path/to/request.json`.
5. After trusted admission, execute: `modal-build-sandbox execute /path/to/request.json --app <existing-modal-app>`.
6. Inspect the private `.outputs/<operation>/<attempt>/` export and `.state/attempts.sqlite` transition history. Keep the source and all exported raw evidence out of public logs and source control.

Run `python scripts/verify_modal_environment.py` for a non-mutating local readiness check. A connected test is in `tests/integration/test_modal_e2e.py`; to run it, supply `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET`, `ONESHOT_MODAL_IMAGE_ID`, and `ONESHOT_MODAL_APP_NAME`, then `RUN_MODAL_E2E=1 uv run pytest -q tests/integration/test_modal_e2e.py`. No token values are printed.

## Staged limitations / admission

This package is a standalone adapter. OneShot integration must separately validate Build Admission, authorized tool versions/digests, promotion CAS, integrated tests, host approval and receipt provenance. Until the live Modal failure → repair → success → termination test passes, call the package **LOCAL_VALIDATION_ONLY**, not production-ready. Do not use the CLI to run arbitrary user-provided requests without trusted host admission.
