# OneShot MVP — host-backed application slice

The MVP runs separately from the canonical OneShot workflow. It persists real
task input artifacts and HostController task state, projects host events over
SSE, and allows CAS-controlled input revision. **No agent execution is simulated.**
Research can use a configured MCP transport; the external TypeScript MCP server
still requires its own build and connected verification.

## Start backend

From the repository root with Python 3.11+:

    uv sync --locked --extra meta --extra mvp
    ONESHOT_STATE_ROOT=.oneshot-state uv run --no-sync uvicorn mvp.api:app --host 127.0.0.1 --port 8000

The local .oneshot-state directory is runtime state, not repository source.
Do not expose the unprotected development API to the public internet.

## Start frontend

    cd web
    npm ci
    npm run dev

Open http://localhost:5173. The Vite server proxies /api to 127.0.0.1:8000.
The backend CORS origin defaults to http://localhost:5173.

## Verify

    uv run --no-sync pytest tests/e2e/test_mvp_service.py
    uv run --no-sync pytest tests/e2e/test_mvp_api.py
    uv run --no-sync pytest tests/e2e/test_mvp_mcp_research.py
    cd web && npm run build
    npx playwright install chromium
    npm run test:browser

## MCP Research boundary

MCP is a tool transport/discovery boundary only. The OneShot host controls
tool permission, task transitions, evidence and completion receipts.

The configured MCP server supplies the `oneshot_research` tool and its response
schema. OneShot validates tool discovery, task and run identity, artifact identity,
digest, and stage transition before accepting output. The server may use any model
that can produce the required Research contract; model selection belongs to that
server. `GET /api/health` reports API reachability, not MCP connectivity.

## Current HTTP scope

The MVP exposes task input, explicit Research execution, a read-only Audit
capability, artifact reads, and events. Audit collects findings while the
Research stage remains open. Later workflow stages have no MVP execution
routes. An input edit creates a new immutable revision; it does not restart
Research automatically.

## Research integration

Configure exactly one host-controlled transport, then restart the API:

- Local stdio: set ONESHOT_MCP_COMMAND to executable, and ONESHOT_MCP_ARGS_JSON to a JSON array of args.
- Local HTTP: set ONESHOT_MCP_URL to an HTTP loopback MCP endpoint.
- Model API credentials belong to the MCP server, not FastAPI tool arguments.

POST /api/tasks creates an immutable task input. POST /api/tasks/{task_id}/research
negotiates an MCP session, discovers oneshot_research, and passes
ProviderRequest.prompt as JSON with task_id and stage_payload.
Successful responses must carry a real ResearchRecord in artifact, the exact
task/run bindings, the contract-defined artifact_id, and a matching RFC 8785 digest.
The host independently computes the identity and digest and checks that the
MCP result's structuredContent equals its JSON text block.
The stdio adapter forces MCP_SERVER_MODE=oneshot in the subprocess environment.
Only process essentials and the documented MCP model and workspace variables
are passed to the child. The reference TypeScript server reads MODEL_API_BASE_URL, MODEL_API_MODEL and
MODEL_API_KEY from its environment. Other MCP servers may configure their model
provider differently while satisfying the same tool and output contract.
The host persists the artifact, marks its WorkTodo completed, and advances Research
through the existing HostController gate. Any verification error blocks advancement.
GET /api/tasks/{task_id}/artifacts returns _research.json only when persisted.

Unit tests inject a controlled MCP response. A separate connected test starts
`tests/fixtures/mcp_research_server.py` over stdio and verifies MCP discovery,
host persistence and transition. Browser tests use the same deterministic fixture.
These tests do not validate model output. The historical connected Python MCP
server run and its limits are clarified in
`audit/e2e-verification-correction-2026-11-04.md`; it does not verify the
reference TypeScript server or a live model provider.

## Direct connected integration probe

With a trusted local MCP server that implements `oneshot_research`, configure
the OneShot MVP host process. For the reference TypeScript server, use:

    ONESHOT_MCP_COMMAND=node
    ONESHOT_MCP_ARGS_JSON='["/absolute/path/to/oneshot-mcp-server/dist/index.js"]'
    MODEL_API_BASE_URL=<configured provider endpoint>
    MODEL_API_MODEL=<configured model identifier>
    MODEL_API_KEY=<server-side credential>

Run from the OneShot repository root:

    uv run --no-sync python -m mvp.integration_probe --state-root .oneshot-probe-state

This invokes the real stdio MCP tool and checks the host's persisted Research
artifact and stage checkpoint. It prints no credential. A reported VERIFIED
result requires the command to exit successfully against the actual server.
For this first slice, zero independently retrieved evidence items is possible;
an artifact digest cannot establish factual grounding. Never expose the
unauthenticated MVP API or untrusted model endpoint publicly.

## Verification boundaries and concurrency

The Research adapter is registered once when `MVPService` initializes, not in
individual requests. A SQLite admission record at the shared state root prevents
concurrent Research calls or input edits for the same task across local processes.
The in-process guard also rejects duplicate calls within one service instance.
Admission is limited to processes sharing one state root; it is not a distributed
lease across separate hosts. Immutable artifacts, Todo CAS and checkpoint CAS
remain separate durable safeguards.

`MCPResearchAdapter.generate()` is synchronous and calls `asyncio.run()`.
FastAPI's synchronous `def start_research` route runs in a worker thread, not
on the application's event loop. Async callers must use an explicit thread
boundary; they must not invoke `generate()` directly inside an active loop.
The server is contacted on demand; a completed Research artifact reports
`research_completed` on task details. No persistent MCP session or connection
probe is maintained by the health endpoint.

An MCP invocation failure leaves the host stage unadvanced. After an interruption,
Research resumes without another MCP call only when the exact output artifact was
already persisted and its identity, digest and work assignment verify. If no
output was persisted, the upstream effect is uncertain and requires manual
reconciliation. Recovery events record failure classifications, not secrets.

## Evidence-grounded Research with the reference server

The pinned reference server revision and its historical verification scope
are recorded in `audit/e2e-verification-correction-2026-11-04.md`. Build and test the
intended server revision before treating its implementation as verified.

The OneShot host can request explicitly authorized repository files by setting:

    MCP_WORKSPACE_ROOT=/absolute/path/to/authorized/repository
    MCP_TRUSTED_ANCESTRY=true
    ONESHOT_RESEARCH_WORKSPACE_PATHS_JSON='["README.md","agent/contracts/research.py"]'

`MCP_TRUSTED_ANCESTRY=true` is an operator assertion for the local workspace,
not proof of path safety. The server must still enforce execution-time containment.
The paths shown are illustrative. Set them to existing, approved relative paths
in the configured repository; do not hardcode an arbitrary project structure.
The host validates the list before assigning Research work. The reference server enforces
execution-time secure file access. The configuration value must be controlled
by the host/operator, not by task text or untrusted client requests. It is
passed inside `stage_payload.evidence_sources.workspace_paths`; this does
not add tools to `tools/list`. Host-supplied snapshots are supported by the
MCP contract but are not yet wired by this MVP adapter, because the host must
first own and authenticate their provenance.

If the variable is absent, Research may return a valid artifact with zero
independent evidence and an unresolved limitation; do not interpret that
as evidence-grounded completion. A green connected E2E requires a workspace
file actually read, its digest independently recomputed by the verifier, and
the host stage transition committed with a valid receipt.

## Read-only Audit capability

The same Research entry point accepts `POST /api/tasks` with `purpose="audit"`
(default: `research`). Invoke `POST /api/tasks/{task_id}/audit` to scan the
host-configured `MCP_WORKSPACE_ROOT` when `MCP_TRUSTED_ANCESTRY=true`
was set at host startup. The root is pinned and checked before scanning.

The result is an immutable `_audit.json` artifact with candidate findings and
limitations, and a completed or blocked host-owned work item. Audit does **not**
produce a `ResearchRecord`, issue a Research completion receipt, or advance
the workflow to Audit Discovery. Selecting `audit` is not permission to invoke
`/research`, and `research` tasks cannot invoke `/audit`.

Run the real API/browser acceptance workflow from
`.github/workflows/audit-capabilities.yml`; fixture tests and source scans
do not substitute for successful browser or provider-connected E2E evidence.
