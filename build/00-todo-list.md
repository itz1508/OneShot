# OneShot Build Assignment 09: Build Execution and Post-Build Validation

> **This is one independent build assignment.** It does not authorize or execute any other prompt.

---

## Assignment Contract

```yaml
assignment:
  id: "09"
  objective: >
    Execute the approved Build using host tools (Databricks Jobs, MLflow, OpenAI Agents SDK).
    Capture and hash actual artifacts, validate output schemas, execute the full fixture set,
    and observe end-to-end success criteria. Must follow the Agent → Tool → Result → Agent
    continuation pattern. Finalization occurs only after observed success. Color Eval:
    GREEN = all tests pass, YELLOW = partial, RED = build failure.

  authority_source:
    repository: "github.com/itz1508/OneShot"
    branch: "main"
    accepted_decisions:
      - "Build uses host execution tools (Databricks Jobs, MLflow), not custom runners."
      - "Agent → Tool → Result → Agent continuation must be observable."
      - "Finalization only after observed success — no assumed completion."
      - "Partial failures are preserved, not silently cleaned up."
      - "Build must use verified application languages and SDKs, not assume Python only."

  scope:
    create_only_if_required:
      - "build_executor.py — build execution using host tools"
      - "tests/test_build_executor.py — contract and E2E tests"
    exclusions:
      - "Must NOT execute without approved Plan and fixtures."
      - "Must NOT clean up partial failures silently."
      - "Must NOT claim success without observed test results."

  acceptance:
    tests:
      - "Build executes approved plan → artifacts produced and hashed."
      - "Output validated against schema → schema validation passes."
      - "Full fixture set executed → all positive pass, all negative fail correctly."
      - "Agent → Tool → Result → Agent continuation observable in trace."
    vertical_behavior:
      - "Build artifacts captured with SHA-256 hashes."
      - "Output schema validated against expected schema."
      - "All fixtures executed with results recorded."
      - "Tool calls and results traced through the execution (MLflow or equivalent)."
      - "Partial failures preserved with error details."
      - "Finalization only after all tests pass."
    required_evidence:
      - "Artifact hashes (SHA-256) for all build outputs."
      - "Schema validation results (pass/fail per field)."
      - "Fixture execution results (all cases, pass/fail)."
      - "Execution trace showing Agent → Tool → Result → Agent pattern."
      - "Finalization confirmation with all checks passed."

  color_eval:
    green: "All four tests pass: artifacts hashed, schema valid, fixtures pass, continuation traced."
    yellow: "Some checks pass but schema validation or fixture execution incomplete."
    red: "Build fails, artifacts not produced, or fixtures fail when they should pass."

  stop_boundary:
    next_prompt_authorized: false
```

## Detailed Instructions

### 1. Execute Using Host Tools

Use host execution capabilities:
* Databricks Jobs for orchestrated execution.
* MLflow for artifact logging and trace recording.
* OpenAI Agents SDK (via databricks-openai) for agent-tool interaction.

Do NOT build a custom execution engine. Reuse what the host provides.

### 2. Capture Artifacts

For each build output:
* Record the artifact path.
* Compute SHA-256 hash.
* Validate against expected output schema.
* Store artifact metadata in Task Management.

### 3. Execute Fixtures

Run the full fixture set from Assignment 07:
* All positive cases must pass.
* All negative cases must fail with expected error types.
* Results recorded with pass/fail status.

### 4. Trace Agent → Tool → Result → Agent

Following the OpenAI Agents SDK pattern:
* Each tool call is logged with input and output.
* Results are fed back to the agent for continuation.
* The full chain is observable in the execution trace.
* Use MLflow autolog or equivalent for trace recording.

### 5. Handle Partial Failures

When some tests fail:
* Preserve the failure details (not cleaned up).
* Record which tests passed and which failed.
* Do NOT finalize — finalization only after all tests pass.
* Store partial results in Task Management for debugging.

### 6. Write Tests and Run Color Eval