# OneShot Build Assignment 03: Repository Search and Source Discovery

> **This is one independent build assignment.** It does not authorize or execute any other prompt.

---

## Assignment Contract

```yaml
assignment:
  id: "03"
  objective: >
    Implement repository search and source discovery using Databricks SDK (WorkspaceClient)
    and Git integration — not a custom filesystem reader. Search the OneShot repository
    for all source files, config, tests, and evidence. Produce a grounded file inventory
    with types, sizes, and content summaries. Start from confirmed Quality Input.

  authority_source:
    repository: "github.com/itz1508/OneShot"
    branch: "main"
    stale_document_references: false
    accepted_decisions:
      - "Use Databricks SDK and Git integration for repository operations."
      - "Do NOT create another filesystem reader, scanner, or discovery service."
      - "Search results must be grounded in actual files, not assumed content."

  scope:
    create_only_if_required:
      - "repo_search.py — repository search using host SDK"
      - "tests/test_repo_search.py — contract and E2E tests"
    exclusions:
      - "Must NOT build a custom filesystem reader or evidence engine."
      - "Must NOT modify repository source files."

  acceptance:
    tests:
      - "Search repository → return file list with paths, types, and sizes."
      - "Search for specific pattern (e.g., *.py) → return only matching files."
      - "Search archived branch (read-only) → return historical file list."
      - "Empty repo (main branch) → return empty list, not error."
    vertical_behavior:
      - "File inventory grounded in actual git ls-tree or SDK listing."
      - "File types correctly identified (.py, .md, .yaml, .json, etc.)."
      - "File sizes are actual bytes, not estimates."
      - "Content summaries based on actual file reading, not inference."
    required_evidence:
      - "File listing from actual repository with verified paths."
      - "Pattern search results showing correct filtering."
      - "Evidence that host SDK was used, not custom scanner."

  color_eval:
    green: "All four tests pass with evidence of actual file discovery via host SDK."
    yellow: "File discovery works but not via host SDK, or sizes/types incorrect."
    red: "Search returns fabricated results or fails on empty repository."

  stop_boundary:
    next_prompt_authorized: false
```

## Detailed Instructions

### 1. Use Databricks SDK for Repository Operations

Use `WorkspaceClient` from the Databricks SDK for:
* Listing workspace files and directories.
* Reading file content.
* Git operations (status, log, branch listing).

Alternatively, use `runGit` CLI operations for git-level file discovery.

Do NOT build a custom filesystem walker, evidence engine, or discovery service.

### 2. Search the OneShot Repository

Search both the main branch and the archived branch:
* Main branch: list all files (expected: README.md, .gitignore only).
* Archive branch: list all files for historical context (read-only).

### 3. Produce Grounded File Inventory

For each file found:
* Record the actual file path.
* Record the file type (by extension).
* Record the actual file size in bytes.
* Read and summarize the first N lines of content.

All inventory entries must be grounded in actual file reads, not assumptions.

### 4. Write Tests and Run Color Eval