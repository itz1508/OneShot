# OneShot Build Assignment 06: Plan Review and Gap Passes

> **This is one independent build assignment.** It does not authorize or execute any other prompt.

---

## Assignment Contract

```yaml
assignment:
  id: "06"
  objective: >
    Review confirmed Research, refactor the Plan candidate without substantive invention,
    run two ordered gap passes (Pass 1: Research grounding against actual code; Pass 2:
    applicable market best practices from applicable engineering practices),
    and implement the Call for Help protocol for when new evidence is required.

  authority_source:
    repository: "github.com/itz1508/OneShot"
    branch: "main"
    accepted_decisions:
      - "Plan reviews and refactors; it does NOT invent new requirements."
      - "Two ordered gap passes are required: grounding, then best practice."
      - "Call for Help requests evidence from the host; it does NOT infer answers."
      - "Plan is read-only with respect to the repository — no mutation."

  scope:
    create_only_if_required:
      - "plan_review.py — plan review and gap pass implementation"
      - "tests/test_plan_review.py — contract tests"
    exclusions:
      - "Must NOT modify repository source files."
      - "Must NOT invent requirements not supported by Research."
      - "Must NOT execute Build."

  acceptance:
    tests:
      - "Gap Pass 1: verify each plan item traces to confirmed Research finding."
      - "Gap Pass 2: verify each plan item aligns with at least one market practice reference."
      - "Untraced plan items are flagged as gaps with required evidence listed."
      - "Call for Help produces a request with specific evidence needed, not an inferred answer."
    vertical_behavior:
      - "Gap Pass 1 identifies plan items without Research grounding."
      - "Gap Pass 2 identifies plan items that violate current engineering practices."
      - "Gaps are documented with: what is missing, why it matters, what evidence is needed."
      - "Plan candidate is refactored to resolve gaps where evidence is available."
      - "Call for Help is triggered when evidence is not available locally."
    required_evidence:
      - "Gap Pass 1 results: plan items with Research traceability status."
      - "Gap Pass 2 results: plan items with market practice alignment."
      - "Gap resolution table: what was resolved, what remains open."
      - "Call for Help requests if any gaps remain unresolved."

  color_eval:
    green: "All four tests pass; all gaps resolved or have Call for Help requests."
    yellow: "Some gaps identified but not all resolved or documented."
    red: "Plan items have no Research grounding or market practice violations not detected."

  stop_boundary:
    next_prompt_authorized: false
```

## Detailed Instructions

### 1. Review Confirmed Research

Read the confirmed Research revision (from Assignment 05):
* Verify the revision ID and digest match.
* Enumerate all findings and their provenance.
* Identify the plan candidate from the Research output.

### 2. Gap Pass 1: Research Grounding

For each item in the plan candidate:
* Trace it to a specific finding in confirmed Research.
* If no tracing exists → flag as a gap.
* Gaps must list: what evidence is missing, where to find it.

### 3. Gap Pass 2: Market Best Practice

For each item in the plan candidate:
* Check against applicable engineering practices (tool execution, orchestration, tracing).
* Check against agent structure and tool selection practices.
* Check against agent design recommendations (simple agents, environment feedback, explicit stops).
* Check against state management patterns (thread state vs long-term memory).
* If a plan item violates a best practice → flag as a gap.

### 4. Refactor Plan Candidate

Based on gap pass results:
* Remove items with no Research grounding (or add Call for Help).
* Align items with market best practices.
* Do NOT invent new requirements — only refactor existing ones.

### 5. Call for Help Protocol

When evidence is required but not available locally:
* Produce a specific request: what evidence is needed, where to look, why.
* Do NOT infer the answer from model text.
* Record the request in Task Management for tracking.
* Plan is blocked until the evidence is provided.

### 6. Write Tests and Run Color Eval