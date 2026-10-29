# OneShot Build Assignment 04: Research Output Package

> **This is one independent build assignment.** It does not authorize or execute any other prompt.

---

## Assignment Contract

```yaml
assignment:
  id: "04"
  objective: >
    Produce the Research Output Package: the evidence-backed source of truth containing
    findings, requirements, success criteria, plan candidate, fixture contracts, artifact
    contracts, output schema, contradictions, and open questions — with full provenance
    and traceability from findings to source files. Must include independent validation
    values, not self-validating assertions.

  authority_source:
    repository: "github.com/itz1508/OneShot"
    branch: "main"
    accepted_decisions:
      - "Research output is the source of truth for Plan and Build."
      - "Every finding must cite a source file with provenance."
      - "Independent validation values are required, not self-validating assertions."
      - "Contradictions and open questions must be recorded, not hidden."

  scope:
    create_only_if_required:
      - "research_output.py — research output package generator"
      - "tests/test_research_output.py — contract tests"
    exclusions:
      - "Must NOT execute Plan or Build."
      - "Must NOT fabricate findings without source evidence."

  acceptance:
    tests:
      - "Research output contains findings with source file references."
      - "Each finding has provenance (file path, line range, commit SHA)."
      - "Success criteria are independently verifiable (not self-validating)."
      - "Contradictions and open questions are explicitly recorded."
      - "Plan candidate is derived from findings, not invented."
    vertical_behavior:
      - "Every finding traces to an actual source file with verified path."
      - "Provenance includes commit SHA, file path, and content reference."
      - "Independent validation values provided for each testable claim."
      - "Contradictions flagged with both sides of the conflict."
      - "Open questions listed with what evidence is needed to resolve them."
    required_evidence:
      - "Research output document with findings table."
      - "Provenance table mapping each finding to source file and commit."
      - "Independent validation values for testable claims."
      - "Contradictions and open questions list."

  color_eval:
    green: "All five tests pass with provenance and independent validation values."
    yellow: "Findings present but provenance incomplete or validation values missing."
    red: "Findings fabricated without source evidence or contradictions hidden."

  stop_boundary:
    next_prompt_authorized: false
```

## Detailed Instructions

### 1. Compile Findings from Repository Evidence

Use the file inventory from Assignment 03 and the repository summary from Assignment 00:
* Each finding must cite the actual source file (path, line range).
* Each finding must include the commit SHA for provenance.
* Findings must be grounded in actual file content, not assumptions.

### 2. Define Success Criteria with Independent Validation

For each testable claim in the research:
* Define what the expected result is (independent of the implementation).
* Define how to verify it (test method, not self-referential).
* Example: "Repository has exactly 2 files on main" — verify with `git ls-tree --name-only HEAD`.

### 3. Record Contradictions and Open Questions

* Contradictions: when two findings conflict, record both sides.
* Open questions: when evidence is insufficient, record what is needed.
* Do NOT resolve contradictions by inference — flag them for Plan review.

### 4. Produce Plan Candidate

Derive a plan candidate from the findings:
* What needs to be built (based on gap matrix from Assignment 00).
* What can be reused (host tools from Assignment 00).
* What needs to be adapted vs created new.
* The plan candidate is a proposal, not an authorization — Plan (Assignment 06) owns refinement.

### 5. Write Tests and Run Color Eval