# OneShot Build Assignment 11: Full E2E and Clean Delivery

> **This is one independent build assignment.** It does not authorize or execute any other prompt.

---

## Assignment Contract

```yaml
assignment:
  id: "11"
  objective: >
    Verify the complete end-to-end lifecycle with real tool calls, handoffs, and results.
    Must test: complete task success, restart and recovery, invalid input handling, and
    persisted results. Must NOT be the first meaningful vertical test — each earlier
    assignment exercises its own vertical path. Must NOT introduce release or promotion
    requirements. Color Eval for E2E: GREEN = all pass, YELLOW = partial, RED = E2E failure.

  authority_source:
    repository: "github.com/itz1508/OneShot"
    branch: "main"
    accepted_decisions:
      - "E2E verifies real execution — structural checks and SQL scans are insufficient."
      - "Must NOT be the first meaningful vertical test — earlier assignments exercise their own paths."
      - "Must NOT introduce release or promotion requirements."
      - "Restart, recovery, and invalid input must be tested with real outcomes."

  scope:
    create_only_if_required:
      - "tests/test_e2e.py — full E2E test suite"
    exclusions:
      - "Must NOT skip any lifecycle step."
      - "Must NOT use mocked or stubbed tool calls."
      - "Must NOT claim E2E success without observed results."

  acceptance:
    tests:
      - "Complete task: input → Quality Input → Research → Plan → Build → artifacts → validation. All steps succeed with real tool calls."
      - "Restart recovery: interrupt mid-execution → restart → verify state resumed from last checkpoint, no duplicate work."
      - "Invalid input: provide malformed input → verify error handling, no side effects, system remains stable."
      - "Persisted results: verify all task records, artifacts, and traces are persisted and queryable after completion."
    vertical_behavior:
      - "Full lifecycle observable: each step produces evidence."
      - "Tool calls are real (not mocked) — results come from actual operations."
      - "Restart resumes from checkpoint without losing progress."
      - "Invalid input is rejected with structured error, system remains operational."
      - "All results persisted in Task Management and queryable after completion."
      - "Execution trace shows complete Agent → Tool → Result → Agent chain."
    required_evidence:
      - "E2E test output: all four tests pass with real results."
      - "Execution trace showing each lifecycle step with tool calls."
      - "Restart recovery output showing state before and after interruption."
      - "Invalid input handling output showing error and system stability."
      - "Persisted results query showing all task records and artifacts."

  color_eval:
    green: "All four E2E tests pass with real tool calls and observed results."
    yellow: "Some tests pass but restart recovery or invalid input handling incomplete."
    red: "E2E test fails, tool calls mocked, or results not persisted."

  stop_boundary:
    next_prompt_authorized: false
```

## Detailed Instructions

### 1. Test Complete Task Success

Run a full task through the entire lifecycle:
* Input → Quality Input validates.
* Research → produces findings with provenance.
* Research Review → confirms with Color Eval.
* Plan → gap passes complete.
* Approval → authorized.
* Build → executes, artifacts produced, fixtures pass.
* All steps must use real tool calls, not mocks.
* Record evidence at each step.

### 2. Test Restart and Recovery

* Start a task, interrupt mid-execution (after Research, before Build).
* Restart the system.
* Verify state resumed from last checkpoint (Research preserved).
* Verify no duplicate Research execution.
* Verify Build proceeds with confirmed Research.

### 3. Test Invalid Input Handling

* Provide malformed input (missing required fields, invalid paths).
* Verify Quality Input detects and blocks.
* Verify error is structured (not a crash).
* Verify no side effects (no partial artifacts created).
* Verify system remains operational for next valid task.

### 4. Test Persisted Results

After E2E completion:
* Query Task Management for the task record.
* Verify all state transitions are logged.
* Verify artifacts are retrievable with hashes.
* Verify execution trace is available.
* Verify Color Eval results are recorded.

### 5. Run Color Eval for E2E

* GREEN: all four tests pass with real results and observed tool calls.
* YELLOW: some tests pass but recovery or invalid input handling incomplete.
* RED: any test fails, tool calls mocked, or results not persisted.

A confirmed RED in any test makes the entire E2E RED — no averaging.

### 6. Clean Delivery

After E2E passes:
* Verify no orphaned resources (temp files, partial artifacts).
* Verify all results are in Task Management.
* Verify execution traces are complete.
* Produce delivery summary with Color Eval per assignment (00-11).