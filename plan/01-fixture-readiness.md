# OneShot Build Assignment 07: Fixture Readiness

> **This is one independent build assignment.** It does not authorize or execute any other prompt.

---

## Assignment Contract

```yaml
assignment:
  id: "07"
  objective: >
    Create fixtures with independent expected results: paired positive cases (known-good
    input → expected pass) and negative cases (known-bad input → expected fail). Fixtures
    must use realistic data from the actual repository, not self-validating assertions.
    The executor must be verified before fixtures may be used for Build validation.
    Color Eval for fixtures: GREEN = all pass, YELLOW = partial, RED = fixture failure.

  authority_source:
    repository: "github.com/itz1508/OneShot"
    branch: "main"
    accepted_decisions:
      - "Fixtures must have independent expected results, not self-validating assertions."
      - "Positive and negative cases are both required."
      - "Fixtures must use realistic data from the actual repository."
      - "The executor must be physically verified before VALID may be claimed."

  scope:
    create_only_if_required:
      - "fixtures/ — fixture data directory"
      - "fixtures/positive_cases.py — known-good input cases"
      - "fixtures/negative_cases.py — known-bad input cases"
      - "tests/test_fixtures.py — fixture validation tests"
    exclusions:
      - "Must NOT create self-validating fixtures (expected = actual from same source)."
      - "Must NOT use synthetic data disconnected from the actual repository."

  acceptance:
    tests:
      - "Run positive fixtures → all pass with expected results."
      - "Run negative fixtures → all fail with expected error types."
      - "Expected results are independent (not computed from the implementation under test)."
      - "Fixture data references actual repository content (file paths, commit SHA)."
    vertical_behavior:
      - "At least 5 positive cases with known-good expected results."
      - "At least 5 negative cases with known-bad expected results."
      - "Expected results defined before execution (not derived from output)."
      - "Fixture data grounded in actual repository state."
      - "Executor verified to run fixtures correctly."
    required_evidence:
      - "Positive case results: all pass with expected values."
      - "Negative case results: all fail with expected error types."
      - "Evidence that expected results are independent."
      - "Fixture data provenance (file paths, commit SHA)."

  color_eval:
    green: "All positive pass, all negative fail correctly, expected results independent."
    yellow: "Some fixtures work but expected results not fully independent or provenance missing."
    red: "Fixtures self-validate or negative cases pass when they should fail."

  stop_boundary:
    next_prompt_authorized: false
```

## Detailed Instructions

### 1. Define Independent Expected Results

For each fixture:
* Define the expected result BEFORE running the implementation.
* The expected result must come from an independent source (manual calculation, specification, or ground truth).
* Do NOT derive expected results from the implementation's output (self-validation).

### 2. Create Positive Cases (Known-Good)

At least 5 positive cases using realistic data from the repository:
* Example: `git rev-parse HEAD` on main branch → expected: valid commit SHA.
* Example: `git status` on clean repo → expected: nothing to commit.
* Example: Quality Input with complete fields → expected: proceeds without STOP.
* Example: Task Management create → expected: returns unique task ID.
* Example: Repo search on main → expected: returns README.md and .gitignore.

### 3. Create Negative Cases (Known-Bad)

At least 5 negative cases with expected failures:
* Example: Quality Input with missing required field → expected: STOP.
* Example: Task Management retry after failure → expected: no duplicate execution.
* Example: Research with fabricated finding → expected: RED from review.
* Example: Plan item without Research grounding → expected: gap flagged.
* Example: Build without approval → expected: blocked.

### 4. Verify Executor

The fixture executor must be verified:
* Can run all positive and negative cases.
* Reports pass/fail correctly.
* Does not swallow exceptions or mask failures.

### 5. Write Tests and Run Color Eval