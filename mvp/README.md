# OneShot MVP — host-backed application slice

The MVP runs separately from the canonical OneShot workflow. It persists real
task input artifacts and HostController task state, projects host events over
SSE, and allows CAS-controlled input revision. **No agent execution is simulated.**
MCP is owned by the separate Codex implementation and is not yet connected.

## Start backend

From the repository root with Python 3.11+:

    uv sync --locked --extra meta
    uv pip install -r mvp/requirements.txt
    ONESHOT_STATE_ROOT=.oneshot-state uv run --no-sync uvicorn mvp.api:app --host 127.0.0.1 --port 8000

The local .oneshot-state directory is runtime state, not repository source.
Do not expose the unprotected development API to the public internet.

## Start frontend

    cd web
    npm install
    npm run dev

Open http://localhost:5173. The Vite server proxies /api to 127.0.0.1:8000.
The backend CORS origin defaults to http://localhost:5173.

## Verify

    uv run --no-sync pytest tests/e2e/test_mvp_service.py
    uv run --no-sync pytest tests/e2e/test_mvp_api.py
    cd web && npm run build

## Codex MCP handoff

MCP is a tool transport/discovery boundary only. The OneShot host controls
tool permission, task transitions, evidence and completion receipts.

The integration adapter requires an MCP endpoint/transport, authentication
mechanism, tool list and schemas, one successful live read-only tool call,
one negative test, and a repeatable startup command. Until verified,
the health endpoint returns mcp_connected: false.

## Explicitly deferred

No approved Build/effects, automatic Research/Audit/Plan execution,
independent E2E Build completion, memory promotion, or PR #21 merge
is claimed by this MVP. An input edit creates a new immutable revision;
it does not automatically restart workflow execution.

## Research integration (Codex MCP first slice)

Configure exactly one host-controlled transport, then restart the API:

- Local stdio: set ONESHOT_MCP_COMMAND to executable, and ONESHOT_MCP_ARGS_JSON to a JSON array of args.
- Local HTTP: set ONESHOT_MCP_URL to an HTTP loopback MCP endpoint.
- Model API credentials belong to the MCP server, not FastAPI tool arguments.

POST /api/tasks creates an immutable task input. POST /api/tasks/{task_id}/research
negotiates an MCP session, discovers oneshot_research, and passes
ProviderRequest.prompt as JSON with task_id and stage_payload.
Successful responses must carry a real ResearchRecord in artifact, the exact
task/run bindings, the Codex content-derived artifact_id, and a matching RFC 8785 digest.
The host independently computes the identity and digest and checks that the
MCP result's structuredContent equals its JSON text block.
The stdio adapter forces MCP_SERVER_MODE=oneshot in the subprocess environment,
while MODEL_API_BASE_URL, MODEL_API_MODEL and MODEL_API_KEY must be injected into
the host process environment and inherited by the trusted child process.
The host persists the artifact, marks its WorkTodo completed, and advances Research
through the existing HostController gate. Any verification error blocks advancement.
GET /api/tasks/{task_id}/artifacts returns _research.json only when persisted.

This is not a live Codex MCP E2E claim: isolated CI tests inject a controlled
MCP response. Real endpoint credentials, handshake, and tool invocation remain
to be independently verified after Codex delivers its runnable server.

## Direct connected integration probe

After cloning and building itz1508/oneshot-mcp-server (main) in a trusted local
directory, configure the OneShot MVP host process with:

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
