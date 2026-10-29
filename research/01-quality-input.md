# OneShot Build Assignment 02: Quality Input

> **This is one independent build assignment.** It does not authorize or execute any other prompt.

---

## Assignment Contract

```yaml
assignment:
  id: "02"
  objective: >
    Implement Quality Input: the component that validates essential requirements before
    execution. Must STOP when required inputs are missing, request clarification from the
    host, and resume after clarification. Must preserve original user intent, supplied
    content, admitted references, accepted decisions, and exclusions — without discarding
    source content, fabricating values, or inferring confirmation from model text.

  authority_source:
    repository: "github.com/itz1508/OneShot"
    branch: "main"
    stale_document_references: false
    accepted_decisions:
      - "Quality Input validates before execution; it does NOT execute or plan."
      - "Missing essential input must trigger STOP, not inference."
      - "Resume after clarification must preserve all prior context."
      - "Model text is not confirmation — only explicit user/host response counts."

  scope:
    create_only_if_required:
      - "quality_input.py — input validation and STOP/resume implementation"
      - "tests/test_quality_input.py — contract and E2E tests"
    exclusions:
      - "Must NOT perform Research, Plan, or Build."
      - "Must NOT fabricate missing values or infer confirmation."

  acceptance:
    tests:
      - "Provide complete input → system proceeds normally."
      - "Provide incomplete input (missing required field) → system STOPS and requests clarification."
      - "After clarification, provide complete input → system resumes with full context preserved."
      - "Provide ambiguous input → system flags ambiguity and requests disambiguation."
    vertical_behavior:
      - "Required fields validated before execution begins."
      - "Missing-input STOP is enforced — no silent inference or default filling."
      - "Clarification request includes which fields are missing and why."
      - "Resume preserves all prior context including already-provided fields."
      - "Exclusions and contradictions are recorded, not silently dropped."
    required_evidence:
      - "Test output showing STOP on missing input."
      - "Test output showing resume after clarification with context preserved."
      - "Test output showing ambiguity detection and disambiguation request."

  color_eval:
    green: "All four tests pass: complete proceeds, incomplete stops, resume preserves context, ambiguity detected."
    yellow: "Some tests pass but STOP or resume behavior not fully verified."
    red: "System proceeds with missing input or loses context on resume."

  stop_boundary:
    next_prompt_authorized: false
```

---

## Prerequisites

* Task Management implemented (Assignment 01) for state persistence during STOP/resume.
* Host platform available for clarification requests.

## Detailed Instructions

### 1. Define Required Input Schema

Specify which fields are required vs optional for any task:
* Required: user intent, repository reference, execution context.
* Optional: file references, accepted decisions, exclusions.

### 2. Implement STOP on Missing Input

When a required field is missing:
* Halt execution immediately.
* Record which fields are missing and why they are required.
* Request clarification from the host (not from model inference).
* Persist current state via Task Management for resume.

### 3. Implement Resume After Clarification

When clarification is provided:
* Restore full context from Task Management.
* Merge clarified values with prior context (no overwriting of provided fields).
* Re-validate completeness.
* Proceed if all required fields now present.

### 4. Implement Ambiguity Detection

For ambiguous inputs (e.g., conflicting references, unclear intent):
* Flag the ambiguity with specific details.
* Request disambiguation from the host.
* Do NOT resolve ambiguity by inference or default selection.

### 5. Preserve Source Content

All user-supplied content must be preserved — including:
* Original intent text (verbatim, not paraphrased).
* Supplied file references (paths, not contents inferred).
* Accepted decisions (as stated, not interpreted).
* Exclusions (as stated, not overridden).
* Contradictions (flagged, not silently resolved).

### 6. Write Tests and Run Color Eval

Write the four acceptance tests and assign Color Eval based on results.