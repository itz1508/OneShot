# OneShot Build Assignment 01: Task Management and Memory Retrieval

> **This is one independent build assignment.** It does not authorize or execute any other prompt.

---

## Assignment Contract

```yaml
assignment:
  id: "01"
  objective: >
    Build the memory retrieval capability. Memory is initialized and available
    whenever an agent starts — initialization and persistence are NOT Research's
    responsibility. Research performs task-relevant retrieval from available memory.
    Must support restart, resume, retry, and prevent duplicated execution using
    existing infrastructure — do not mandate specific persistence tools.

  authority_source:
    repository: "github.com/itz1508/OneShot"
    branch: "main"
    stale_document_references: false
    accepted_decisions:
      - "Memory is initialized at agent startup; Research retrieves, does not own persistence."
      - "Reuse existing infrastructure for persistence — do not mandate specific tools."
      - "Thread state (current execution) is distinct from long-term memory (historical records)."
      - "Restart must resume from last persisted state without duplicate execution."

  verified_start:
    source: "github.com/itz1508/OneShot"
    branch: "main"
    commit_sha: "<verify at execution time>"
    existing_capabilities: []
    missing_capabilities: ["memory_retrieval", "state_persistence", "recovery"]

  scope:
    inspect: ["repository file tree"]
    modify: []
    create_only_if_required:
      - "memory_retrieve.py — memory retrieval capability"
      - "tests/test_memory_retrieve.py — contract and E2E tests"
    exclusions:
      - "Must NOT own memory initialization or persistence — that is agent startup's job."
      - "Must NOT implement workflow logic, Research, Plan, or Build."
      - "Must NOT implement approval or authorization."
      - "Must NOT mandate specific persistence tools unless the runtime requires them."

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
    green: "Retrieval capability works with evidence of restart, resume, retry, and no-duplicate behavior."
    yellow: "Retrieval works but recovery or no-duplicate behavior not fully verified."
    red: "Memory retrieval fails or restart produces duplicate execution."

  stop_boundary:
    next_prompt_authorized: false
```

---

## Prerequisites

* OneShot repository cloned and verified (Assignment 00 complete).
* Memory initialized and available at agent startup.

## Inputs

* Repository state from Assignment 00.
* Available memory and existing infrastructure.

## Outputs

* `memory_retrieve.py` — memory retrieval capability using existing infrastructure.
* `tests/test_memory_retrieve.py` — Contract and E2E tests.
* Test evidence showing retrieval, restart, resume, retry, and no-duplicate behavior.

## Detailed Instructions

### 1. Build Memory Retrieval

Create a memory retrieval capability that:
* Retrieves task-relevant records from available memory (initialized at agent startup).
* Supports restart from last persisted state using existing infrastructure.
* Prevents duplicate execution (idempotency checks).
* Does NOT own memory initialization or persistence — that is agent startup's job.

### 2. Reuse Existing Infrastructure

Use existing infrastructure for persistence — do not mandate specific tools.
Reuse what the runtime provides. Do NOT build a custom database engine.

### 3. Thread State vs Long-Term Memory

Memory stores both but Research only retrieves:
* Thread state: current execution context (active task, current step, intermediate results).
* Long-term memory: historical task records, completed results, past failures.

Research retrieves from both but does not own persistence.

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