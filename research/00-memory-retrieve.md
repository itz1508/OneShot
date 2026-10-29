# OneShot Build Assignment 01: Task Management and Memory Retrieval

> **This is one independent build assignment.** It does not authorize or execute any other prompt.

---

## Assignment Contract

```yaml
assignment:
  id: "01"
  objective: >
    Implement Task Management that persists task identity, execution state, events,
    recovery, and results. Must support restart, resume, retry, and prevent duplicated
    execution. Use Databricks Unity Catalog tables or MLflow tracking for persistence —
    do not build a custom database. Research must retrieve stored records via this
    component before proceeding.

  authority_source:
    repository: "github.com/itz1508/OneShot"
    branch: "main"
    stale_document_references: false
    accepted_decisions:
      - "Task Management persists state; it does NOT perform workflow reasoning or execution."
      - "Use host persistence (Unity Catalog tables or MLflow), not custom storage."
      - "Thread state (current execution) is distinct from long-term memory (historical records)."
      - "Restart must resume from last persisted state without duplicate execution."

  verified_start:
    source: "github.com/itz1508/OneShot"
    branch: "main"
    commit_sha: "<verify at execution time>"
    existing_capabilities: []
    missing_capabilities: ["task_management", "state_persistence", "recovery"]

  scope:
    inspect: ["repository file tree"]
    modify: []
    create_only_if_required:
      - "task_management.py — Task Management implementation"
      - "tests/test_task_management.py — contract and E2E tests"
    exclusions:
      - "Must NOT implement workflow logic, Research, Plan, or Build."
      - "Must NOT implement approval or authorization."
      - "Must NOT build a custom database engine."

  dependencies:
    required_capabilities: []
    verification_required: true
    automatic_execution: false

  acceptance:
    tests:
      - "Create task → verify task record persisted with unique ID."
      - "Interrupt execution → restart → verify state resumed from last checkpoint."
      - "Retry failed operation → verify no duplicate side effects."
      - "Query task status → verify current state, events, and results returned."
    vertical_behavior:
      - "Task identity persisted with unique ID across restarts."
      - "Execution state (pending, running, completed, failed) tracked and queryable."
      - "Events log records all state transitions with timestamps."
      - "Recovery resumes from last persisted state without re-executing completed work."
      - "No duplicated execution after restart or retry."
      - "Results and receipts persisted and retrievable."
    required_evidence:
      - "Task record with unique ID in persistence store."
      - "State transition log showing restart/resume behavior."
      - "Test output showing no duplicate execution after retry."
      - "Status query returning current state, events, and results."

  color_eval:
    green: "All four acceptance tests pass with evidence of restart, resume, retry, and no-duplicate."
    yellow: "Some tests pass but recovery or no-duplicate behavior not fully verified."
    red: "Task Management cannot persist state or restart fails with duplicate execution."

  stop_boundary:
    next_prompt_authorized: false
```

---

## Prerequisites

* OneShot repository cloned and verified (Assignment 00 complete).
* Databricks Unity Catalog accessible for table creation, or MLflow available for tracking.

## Inputs

* Repository state from Assignment 00.
* Host persistence capabilities (Unity Catalog or MLflow).

## Outputs

* `task_management.py` — Task Management implementation using host persistence.
* `tests/test_task_management.py` — Contract and E2E tests.
* Test evidence showing create, interrupt, restart, resume, retry, and no-duplicate behavior.

## Detailed Instructions

### 1. Implement Task Management

Create a Task Management component that:
* Persists task records with unique IDs (use UUID or host-generated IDs).
* Tracks execution state: pending, running, completed, failed, interrupted.
* Logs state transition events with timestamps.
* Supports restart from last persisted state.
* Prevents duplicate execution (idempotency checks).
* Stores results and receipts.

### 2. Use Host Persistence

Use one of:
* Unity Catalog tables (Delta tables in a dedicated schema) for structured persistence.
* MLflow tracking for experiment-style run logging.

Do NOT build a custom SQLite database or file-based storage. Reuse what the host provides.

### 3. Implement Thread State vs Long-Term Memory

Following LangGraph's distinction:
* Thread state: current execution context (active task, current step, intermediate results).
* Long-term memory: historical task records, completed results, past failures.

Task Management stores both but does not reason about them.

### 4. Write Contract and E2E Tests

Tests must verify:
* Create task → persist → verify retrievable by ID.
* Interrupt → restart → verify state resumed, not restarted from scratch.
* Retry after failure → verify no duplicate side effects.
* Query status → verify complete event log returned.

### 5. Run Color Eval

After tests pass:
* GREEN: all four tests pass with evidence.
* YELLOW: partial — some tests pass but recovery or no-duplicate unverified.
* RED: persistence fails or duplicate execution occurs.