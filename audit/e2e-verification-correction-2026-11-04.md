# Connected E2E verification scope correction

This note corrects the scope of `e2e-verification-record-2026-11-04.md` without changing its historical observations.

The record's `E2E_VERIFIED: YES` verdict applies to a Python MCP server used for a protocol and OneShot host integration run. It does **not** verify execution of the reference TypeScript MCP server, its model client, or a live model provider. The TypeScript server was not built or run in that verification environment.

The record pins OneShot commit `ebac44627448b9b3ec7c6ce1e9fcaed07e5c4fe1` and MCP server commit `7915b8bf9219071a1349f12f1a3afd3c64a38551`. The OneShot commit predates Audit capability commits `bb7afb8` and `85080a7`; the record cannot establish E2E status for those changes or this working tree. Its temporary HTTP probe script was not committed, so that exact run cannot be replayed from this repository.

The current E2E gate is a connected run against the intended, pinned MCP server revision with independently checked source evidence, host artifact persistence, receipt binding, and task stage transition. Browser and Audit capability behavior require their own connected checks. Local unit and integration tests establish narrower results and should be reported separately from that gate.

## Current working-tree checks

On the uncommitted working tree based on `85080a7`, Python 3.12 ran `uv run --no-sync --python 3.12 pytest -ra`: 422 passed, 0 skipped. `uv lock --check`, deptry, Ruff lint and format checks, mypy, `npm ci`, and `npm run build` also completed successfully. A committed test fixture starts a deterministic Python MCP server over stdio and verifies real negotiation, tool discovery, Research artifact persistence and one host stage transition. `ONESHOT_TEST_PYTHON=3.12 npm run test:browser` passed three Playwright tests using local API and Vite servers: Research through that MCP fixture with persisted artifact and reload; Audit task creation, scan, persisted artifact, reload and read-only display; and rejection of cross-purpose API dispatch. Connected browser tests run serially because they share the API process. These checks do not exercise the reference TypeScript MCP server, a live model provider, or the six-stage Build workflow. The browser workflow is configured in `.github/workflows/audit-capabilities.yml` and still requires an observed CI result.
