# OneShot Build Assignment 10: MCP and Tool Integrations

> **This is one independent build assignment.** It does not authorize or execute any other prompt.

---

## Assignment Contract

```yaml
assignment:
  id: "10"
  objective: >
    Implement MCP (Model Context Protocol) that exposes existing operations only — using
    Databricks Unity Catalog functions, AI Gateway, or MLflow tools. MCP must NOT implement
    core logic, pause/resume, approval, Task Management, Research, Plan, or Build. Enforce
    least privilege via UC permissions. Verify correct tool selection, error handling, and
    provider compatibility.

  authority_source:
    repository: "github.com/itz1508/OneShot"
    branch: "main"
    accepted_decisions:
      - "MCP exposes existing operations; it does NOT implement core logic."
      - "Use Databricks Unity Catalog functions or AI Gateway for tool exposure."
      - "Least privilege enforced via UC permissions, not application-level checks."
      - "MCP must NOT implement pause/resume, approval, Task Management, Research, Plan, or Build."

  scope:
    create_only_if_required:
      - "mcp_tools.py — MCP tool exposure using host capabilities"
      - "tests/test_mcp_tools.py — contract and E2E tests"
    exclusions:
      - "Must NOT implement core agent logic through MCP."
      - "Must NOT bypass UC permissions."
      - "Must NOT create new tools that duplicate existing host capabilities."

  acceptance:
    tests:
      - "Call MCP tool → returns expected result from underlying operation."
      - "Call MCP tool without permission → access denied by UC."
      - "Call MCP tool with invalid input → error returned, no side effects."
      - "Verify MCP does not expose pause/resume, approval, or workflow logic."
    vertical_behavior:
      - "MCP tools map to existing UC functions or AI Gateway endpoints."
      - "Permissions enforced by Unity Catalog, not application code."
      - "Invalid input returns structured error, no partial execution."
      - "MCP exposes only existing operations — no new logic."
      - "Tool selection is correct for the requested operation."
    required_evidence:
      - "MCP tool call results with input/output."
      - "Permission denial test showing UC enforcement."
      - "Error handling test with invalid input."
      - "Verification that no core logic is implemented in MCP layer."

  color_eval:
    green: "All four tests pass: results correct, permissions enforced, errors handled, no core logic."
    yellow: "Some tools work but permissions not enforced by UC or error handling incomplete."
    red: "MCP implements core logic or bypasses UC permissions."

  stop_boundary:
    next_prompt_authorized: false
```

## Detailed Instructions

### 1. Use Unity Catalog Functions for Tool Exposure

Expose existing operations as UC functions:
* Wrap existing operations as Unity Catalog functions.
* Use AI Gateway for model-facing tool endpoints.
* Use MLflow model registry for model serving tools.

Do NOT create new operations — only expose what already exists.

### 2. Enforce Least Privilege

* Permissions enforced by Unity Catalog (GRANT/REVOKE).
* Each tool has minimum required permissions.
* No tool has blanket access.
* Application-level permission checks are backup, not primary.

### 3. Verify Error Handling

For each MCP tool:
* Invalid input → structured error returned.
* No side effects on error.
* Error message does not leak sensitive information.
* Timeout handled gracefully.

### 4. Verify No Core Logic

MCP layer must NOT contain:
* Pause/resume logic.
* Approval or authorization.
* Task Management.
* Research, Plan, or Build logic.
* Workflow orchestration.

### 5. Write Tests and Run Color Eval