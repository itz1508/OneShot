# OneShot Build Assignment 00: Repository Summary and Authority

> **This is one independent build assignment.** It does not authorize or execute any other prompt.

---

## Assignment Contract

```yaml
assignment:
  id: "00"
  objective: >
    Build and verify the repo-summary script/tool that clones and verifies the OneShot
    repository (github.com/itz1508/OneShot, main branch), produces an evidence-backed
    summary of what exists, identifies the market-practice gap matrix (00-11), classifies
    each gap as build/adapt/preserve/retire, and establishes the Color Eval baseline.
    repo-summary is an executable capability, not just a Markdown document. Research
    must begin here.

  authority_source:
    repository: "github.com/itz1508/OneShot"
    branch: "main"
    stale_document_references: false
    accepted_decisions:
      - "Main branch is an intentionally clean starting point — not a completed product."
      - "Previous implementation is archived in archive/pre-rebuild-2026-10-29, not authoritative."
      - "Each prompt is one independent build assignment, not a phase in a continuous build."
      - "Dependencies describe required capabilities, not automatic execution."

  verified_start:
    source: "github.com/itz1508/OneShot"
    branch: "main"
    commit_sha: "<verify with git rev-parse HEAD at execution time>"
    existing_files: ["README.md", ".gitignore"]
    existing_capabilities: []
    missing_capabilities: ["all — main branch is source-free"]

  scope:
    inspect:
      - "Repository file tree and commit history"
      - "README.md content and stated intent"
      - ".gitignore for excluded patterns"
      - "archive/pre-rebuild-2026-10-29 branch for historical context (read-only)"
    modify: []
    create_only_if_required:
      - "repo_summary.py — executable repo-summary script/tool"
      - "tests/test_repo_summary.py — tests verifying the script runs and produces output"
    exclusions:
      - "No production source code may be modified."
      - "The archived branch must not be treated as current architecture."

  dependencies:
    required_capabilities: []
    verification_required: true
    automatic_execution: false

  acceptance:
    tests:
      - "git rev-parse HEAD returns a verifiable commit SHA."
      - "git status shows a clean working tree."
      - "Repository file listing matches expected (README.md, .gitignore only)."
    vertical_behavior:
      - "Repository cloned and verified with concrete commit SHA."
      - "Gap matrix (00-11) produced with evidence from actual repository state."
      - "Each gap classified: build (new), adapt (modify), preserve (keep), retire (remove)."
      - "Color Eval baseline assigned: GREEN (ready), YELLOW (partial), RED (blocked)."
      - "Available built-in tools and existing infrastructure identified for reuse."
    required_evidence:
      - "Verified commit SHA from git rev-parse HEAD."
      - "File listing from actual repository (not assumed)."
      - "Gap matrix table mapping areas 00-11 to build/adapt/preserve/retire."
      - "Color Eval baseline with justification per area."
      - "List of available built-in tools and existing infrastructure for reuse."

  color_eval:
    green: "repo-summary script executes, produces verified output with evidence-backed gap matrix, and available tools are identified."
    yellow: "Script runs but gap matrix lacks evidence or tool inventory incomplete."
    red: "repo-summary script does not execute or repository not accessible."

  stop_boundary:
    next_prompt_authorized: false
```

---

## Prerequisites

Before this assignment may begin:

* The OneShot repository must be cloned and accessible.
* Git must be available for commit verification.
* Available built-in tools and existing infrastructure must be enumerated for reuse.

## Inputs

This assignment consumes:

* The OneShot repository at github.com/itz1508/OneShot (main branch)
* The archived branch archive/pre-rebuild-2026-10-29 (read-only historical context)
* Available built-in tools and existing infrastructure

## Outputs

This assignment produces:

* `repo_summary.py` — executable script that produces the summary
* `tests/test_repo_summary.py` — tests verifying the script runs correctly
* Verified commit SHA and clean working tree confirmation
* Complete file listing of the repository
* Gap matrix table (areas 00-11) with build/adapt/preserve/retire classification
* Color Eval baseline per area with evidence
* Available tools inventory for reuse in subsequent assignments

## Post-Conditions

After this assignment completes successfully:

* The authoritative source is identified and verified.
* The gap matrix is established with evidence from the actual repository.
* Host tools are identified for reuse.
* Color Eval baseline is assigned.
* No production source has been modified.

## Failure State

If this assignment fails or is blocked:

* The blocker reason is recorded (e.g., repository not accessible, git unavailable).
* The assignment may be re-run after the blocker is resolved (idempotent — it does not modify state).

## Detailed Instructions

### 1. Verify the Repository

Clone or access github.com/itz1508/OneShot on the main branch. Verify:

* The repository exists and is accessible.
* The current commit SHA is recorded (run `git rev-parse HEAD`).
* The working tree is clean (run `git status`).
* The file listing matches expectations (README.md, .gitignore only on main).

### 2. Read Repository Intent

Read README.md to understand the stated purpose. The README explicitly states:
* Main branch is a source-free starting point.
* Previous implementation is archived in archive/pre-rebuild-2026-10-29.
* The next implementation must be grounded in accepted requirements.

### 3. Produce the Gap Matrix

Map each area (00-11) from the market-practice gap matrix to the actual repository state:

| Area | Requirement | Current State | Action | Evidence |
|---|---|---|---|---|
| 00 — Authority | Ground decisions in evidence | README states intent | Build | README confirms clean start |
| 01 — Task Management | Persist identity, state, recovery | Not implemented | Build | No source files exist |
| 02 — Quality Input | Validate before execution | Not implemented | Build | No source files exist |
| 03 — Research startup | repo-summary + memory-retrieve | This assignment | Build | Being executed now |
| 04 — Research output | Structured evidence-backed findings | Not implemented | Build | No source files exist |
| 05 — Research review | Evaluate groundedness, contradictions | Not implemented | Build | No source files exist |
| 06 — Plan | Feasible, dependency-aware planning | Not implemented | Build | No source files exist |
| 07 — Fixtures | Independent expected results | Not implemented | Build | No source files exist |
| 08 — Approval | Enforceable execution boundaries | Not implemented | Build | No source files exist |
| 09 — Build | Execute through supported tools | Not implemented | Build | No source files exist |
| 10 — MCP / tools | Reuse supported interfaces | Not implemented | Build | No source files exist |
| 11 — E2E | Test complete task outcomes | Not implemented | Build | No source files exist |

### 4. Assign Color Eval Baseline

For each area, assign a preliminary Color Eval rating:
* GREEN — ready to proceed with implementation.
* YELLOW — partial readiness, some prerequisites missing.
* RED — blocked, cannot proceed.

All areas start as GREEN for build (the repository is clean and ready). RED only if the repository is inaccessible.

### 5. Identify Host Tools for Reuse

Enumerate available built-in tools and existing infrastructure that subsequent assignments should reuse.
Do not mandate specific tools unless the selected runtime requires them. Reuse what exists.
Do not rebuild existing capabilities. Subsequent assignments must reuse available infrastructure.

### 6. Check Archived Branch (Read-Only)

For historical context only, inspect the archive/pre-rebuild-2026-10-29 branch to understand what was previously built. Do NOT treat this as current architecture or authority. Record observations about what worked and what failed for reference.