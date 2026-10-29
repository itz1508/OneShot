# OneShot — Greenfield local implementation

This is an independently written, host-callable **local** implementation. It does not copy the archived OneShot repository or its skills and does not deploy to Modal.

## Structure

- `input/main.py`: accepts typed input envelopes; no execution.
- `output/main.py` and `output/schema/`: validates Research, Plan and Build results.
- `scanner.py`: bounded, read-only local source inspection.
- `task.py`: one SQLite owner for scoped task state, results, events and recovery receipts.
- `build.py`: tightly bounded, authorized artifact writes, hash readback and owned-resource cleanup.
- `mcp_server.py`: the **only** MCP stdio server; exposes existing operations through the official SDK.
- `tests/`: independent contract, negative, restart, build cleanup and client integration tests.

There is no general-purpose Agent runtime, installed skill collection, workflow engine, second Scanner or provider router. Research and Plan content is **authored by the host** and is structurally validated, not independently certified for semantic truth. Build does not execute arbitrary code, run shell commands, modify existing source, or start cloud jobs.

## Installation

Python **3.12+**, `pip install -r requirements.txt` from the source root. The MCP server requires the official Python MCP SDK supplied in project dependencies.

Run `python -m pytest -q`. When the MCP SDK is installed, the stdio host-to-server integration test executes instead of skipping.

## Trusted host configuration

The MCP server is a **local single-trusted-host tool**, not a network multi-user authentication service. The launching host must define:

- `ONESHOT_STATE_DB`: an authorized writable SQLite database path.
- `ONESHOT_TASK_SCOPE`: the host's trusted task/thread scope.
- `ONESHOT_SOURCE_ROOT`: optional, explicitly authorized local source directory.
- `ONESHOT_ALLOWED_SOURCES`: optional comma-separated **relative file names** admitted for read-only scanning.
- `ONESHOT_BUILD_ROOT`: optional, exclusively owned writable sandbox directory.
- `ONESHOT_APPROVED_BUILDS`: optional comma-separated `<task-id>:<plan-id>` grants set by the operator **outside the MCP client**.

The server must be launched only by an authorized host that controls this environment. Client-supplied task IDs, source names, plan records or output JSON **do not grant access**. An untrusted host with control over process environment is outside the security boundary.

Run `oneshot-mcp`, or `python -m mcp_server`, with that trusted environment. The MCP protocol uses stdio; do not write ordinary logs to stdout.

Example (local PowerShell, replace values with the authorized paths; no automatic grant):

```powershell
$env:ONESHOT_STATE_DB = 'D:\OneShot-state\tasks.sqlite'
$env:ONESHOT_TASK_SCOPE = 'trusted-thread-1'
$env:ONESHOT_SOURCE_ROOT = 'D:\OneShot-sources'
$env:ONESHOT_ALLOWED_SOURCES = 'fixture.txt'
python -m mcp_server
```

For Build, the operator must separately configure the sandbox and exact task/plan grant. Without it the Build tool refuses execution.

## Scope and known limitations

- The built-in Scanner detects **exact duplicate nonblank lines** from fully read UTF-8 text; it does not establish semantic equivalence or identify arbitrary conflicts.
- Build only creates up to eight new UTF-8 files, each at most 128,000 bytes, whose filenames appear as committed Plan targets. Existing artifacts cannot be overwritten. This is not a general shell-code Builder.
- Cleanup removes only the generated per-build temporary staging directory. Permanent output, task state, evidence and other builds' files remain.
- Interrupted-build reconciliation is an explicit trusted operator operation after confirming the original worker has stopped. It never retries an unknown execution or claims success.
- Persistence, path-boundary and protocol tests run in this sandbox; Windows, Codex-host activation, Modal, real cloud inference, and a live MCP stdio session require their own environments/evidence.
- Python stdlib file/path checks reduce traversal and symlink risks but are not a defense against hostile concurrent replacement of files in the trusted roots.
- Do **not** use the uploaded Modal Proxy Token. Rotate previously shared credentials before any future cloud integration.

## Declarative workflow templates (candidate)

The packaged `templates/catalog.json` is the single definition of the three
available stage IDs. `workflow_templates.py` provides read-only `list_templates()`,
`load_template(stage)` and `validate_quality_input(stage, input_dict)` APIs.
The host supplies the explicit stage ID; these APIs **never** select an Agent,
choose a tool, create a task, grant permission or auto-advance a workflow.

Each stage uses one shared Draft 2020-12 input contract at
`templates/schema/input.json`. Inputs preserve the original request, context
references, accepted decisions and blocking unknowns. A `blocked` input is
valid only when it declares at least one blocking unknown. A `ready` Build
input requires a Plan ID and approval reference; the reference is informational
and never replaces the existing independently enforced BuildPolicy grant.

The existing output schemas remain canonical. `research.json` now optionally
accepts `validation_values` containing a criterion, expected value and source
references. `plan.json` optionally accepts `validation_value_refs` tied to a
Research ID. The SQLite store persists these fields without creating another
record owner. It rejects duplicate Research validation-value IDs and Plan
references to unknown validation-value IDs within the linked Research record.
The schemas verify structure, while the store verifies these identifier links;
neither establishes factual evidence, semantic equivalence, Agent reasoning,
or whether any referenced source was independently inspected.

Example for a host that has *already* determined the appropriate stage:

```python
from workflow_templates import load_template, validate_quality_input

instructions = load_template("research")["instructions"]
quality_input = validate_quality_input("research", {
    "template_id": "research", "task_id": "task-1", "request_id": "req-1",
    "original_request": "Investigate the authorized fixture",
    "context_refs": ["source:fixture.txt"], "accepted_decision_refs": [],
    "unknowns": [], "readiness": "ready"
})
```

This candidate remains separate from any uninspected Windows checkout. No
connected ChatGPT MCP execution is implied by local template or store tests.
