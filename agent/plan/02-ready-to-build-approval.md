# OneShot Build Assignment 08: Ready-to-Build Approval

> **This is one independent build assignment.** It does not authorize or execute any other prompt.

---

## Assignment Contract

```yaml
assignment:
  id: "08"
  objective: >
    Verify that exact bindings (scope, sources, revisions, fixtures, schemas, checks,
    execution context) are established and that approval authority is confirmed before
    Build may proceed. Authorization must be enforced by the host system (Databricks
    workspace permissions, existing infrastructure), not merely described in prompts.
    Build should not proceed without user confirmation.

  authority_source:
    repository: "github.com/itz1508/OneShot"
    branch: "main"
    accepted_decisions:
      - "Approval is enforced by the host system, not by text convention."
      - "Hash binding is necessary but insufficient — approval principal must be confirmed."
      - "Model-written data cannot authorize execution."
      - "Unauthorized Build must be physically blocked, not just discouraged."

  scope:
    create_only_if_required:
      - "approval.py — approval gate implementation"
      - "tests/test_approval.py — contract and E2E tests"
    exclusions:
      - "Must NOT execute Build."
      - "Must NOT bypass approval checks."
      - "Must NOT accept model text as authorization — only explicit user confirmation counts."

  acceptance:
    tests:
      - "Attempt build without approval → system blocks execution."
      - "Provide approval from authorized principal → build proceeds."
      - "Attempt build with model-written authorization → system blocks."
      - "Verify all bindings are present: scope, sources, revisions, fixtures, schemas, checks."
    vertical_behavior:
      - "Approval gate checks: confirmed Research revision, approved Plan, verified fixtures."
      - "Missing any binding → Build blocked with specific missing item listed."
      - "Approval from unauthorized principal → blocked."
      - "Approval from authorized principal with all bindings → Build proceeds."
      - "Model text presented as authorization → rejected."
    required_evidence:
      - "Test output showing blocked execution without approval."
      - "Test output showing build proceeds with valid approval."
      - "Test output showing rejection of model-written authorization."
      - "Binding verification table: all bindings present and confirmed."

  color_eval:
    green: "All four tests pass: unauthorized blocked, authorized proceeds, model text rejected, bindings verified."
    yellow: "Some checks work but model text not rejected or bindings incomplete."
    red: "Unauthorized Build can execute or model text accepted as authorization."

  stop_boundary:
    next_prompt_authorized: false
```

## Detailed Instructions

### 1. Implement Approval Gate

The approval gate must verify:
* Confirmed Research revision (from Assignment 05) — revision ID and digest match.
* Approved Plan (from Assignment 06) — gap passes complete, no unresolved gaps.
* Verified fixtures (from Assignment 07) — positive and negative cases pass.
* Execution context — repository, branch, commit SHA all confirmed.
* Scope — all bindings (scope, sources, revisions, fixtures, schemas, checks) present.

### 2. Enforce Authorization

Authorization must be enforced by the host system:
* Use existing infrastructure for access control.
* Only authorized principals can approve Build.
* Model text is NEVER accepted as authorization — only explicit host-level approval.

### 3. Block Unauthorized Build

When approval is missing or invalid:
* Build execution is physically blocked (not just warned).
* The specific missing item is reported.
* No partial execution is allowed.

### 4. Write Tests and Run Color Eval