# OneShot Build Assignment 05: Research Review and Confirmation

> **This is one independent build assignment.** It does not authorize or execute any other prompt.

---

## Assignment Contract

```yaml
assignment:
  id: "05"
  objective: >
    Implement the Research review and confirmation hook. Research Output triggers an
    optional review that evaluates groundedness, completeness, and contradictions using
    evidence-based quality checks. Must produce a binding confirmation that locks exact
    ID, revision, digest, and evidence snapshot. The confirmed Research revision becomes
    Plan's source of truth. Color Eval (GREEN/YELLOW/RED) is assigned based on evidence quality.

  authority_source:
    repository: "github.com/itz1508/OneShot"
    branch: "main"
    accepted_decisions:
      - "Review evaluates evidence quality; it does NOT rewrite Research."
      - "Confirmation locks the Research revision — Plan must use the confirmed revision."
      - "Color Eval is evidence-backed, not keyword-based."
      - "One confirmed RED finding makes the entire Research RED, regardless of other scores."

  scope:
    create_only_if_required:
      - "research_review.py — review and confirmation implementation"
      - "tests/test_research_review.py — contract and E2E tests"
    exclusions:
      - "Must NOT rewrite or modify Research content."
      - "Must NOT proceed to Plan without confirmed Research."

  acceptance:
    tests:
      - "Provide research with full provenance → review returns GREEN."
      - "Provide research with a contradiction → review returns RED with contradiction flagged."
      - "Provide research with missing provenance → review returns YELLOW with gaps listed."
      - "Confirmation locks revision ID, digest, and evidence snapshot."
    vertical_behavior:
      - "Groundedness check: every finding traces to a source file."
      - "Completeness check: all gap matrix areas (00-11) have findings."
      - "Contradiction check: conflicting findings are detected and flagged."
      - "Color Eval assigned: GREEN/YELLOW/RED based on evidence quality."
      - "Confirmation produces immutable revision with digest."
      - "A confirmed RED finding makes the entire Research RED (critical override)."
    required_evidence:
      - "Review output with Color Eval per finding."
      - "Contradiction detection output showing both sides."
      - "Confirmation record with locked revision ID and digest."

  color_eval:
    green: "All four tests pass: GREEN, RED detection, YELLOW detection, confirmation locks."
    yellow: "Some checks work but contradiction detection or confirmation incomplete."
    red: "Review cannot detect contradictions or confirmation does not lock revision."

  stop_boundary:
    next_prompt_authorized: false
```

## Detailed Instructions

### 1. Implement Groundedness Check

For each finding in the Research Output:
* Verify the cited source file exists at the stated path.
* Verify the commit SHA matches the repository state.
* Verify the content reference (line range) is within the file.
* Findings without provenance → YELLOW.

### 2. Implement Completeness Check

Verify all gap matrix areas (00-11) have at least one finding:
* Missing areas → YELLOW with list of missing areas.
* All areas present → GREEN for completeness.

### 3. Implement Contradiction Check

Detect conflicting findings:
* Two findings stating opposite conclusions about the same subject → RED.
* Finding contradicts repository evidence → RED.
* A confirmed RED makes the entire Research RED (critical override — no averaging).

### 4. Assign Color Eval

* GREEN: all findings have provenance, all areas covered, no contradictions.
* YELLOW: some gaps in provenance or completeness, no contradictions.
* RED: at least one confirmed contradiction or fabricated finding.

### 5. Produce Binding Confirmation

When Research is GREEN or YELLOW (acceptable with caveats):
* Lock the Research revision ID.
* Compute a digest (SHA-256) of the Research content.
* Record an evidence snapshot (file paths, commit SHA, content hashes).
* Store confirmation in Task Management.
* The confirmed revision becomes Plan's source of truth.

### 6. Write Tests and Run Color Eval