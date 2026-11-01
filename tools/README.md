# Tools — OneShot workflow components

This directory contains the active tool implementations used by the OneShot workflow harness. All tools are pure-Python, importable via `tools/` (configured in `conftest.py` and `pyproject.toml`), and tested by the suite in `tests/`.

## Tool inventory

| File | Responsibility |
|------|----------------|
| `task_management.py` | Task state, checkpoints, resume, event log, atomic/CAS persistence (`set_task_metadata` with `if_revision`, `set_decision_wait`, `CorruptStoreError`) |
| `color_eval.py` | GREEN/AMBER/RED evaluation with evidence |
| `fixtures.py` | FixtureRegistry with independent expected results (G03 `expected_rejection` shape) |
| `search_sources.py` | Repository file search and inventory |
| `text_metrics.py` | Text counting (characters, bytes, words) |
| `build_executor.py` | Build execution with trace and artifact capture; refuses unauthorized `tool_fn` |
| `mcp_tools.py` | MCP tool registry (no core logic, permission-gated) |
| `repo_summary.py` | Repository summary with gap matrix |

Previously-tracked modules (`approval.py`, `memory_retrieve.py`, `plan_review.py`, `research_output.py`, `research_review.py`) were consolidated into `agent/main.py` and its sibling adapters under `agent/adapters/` during the migration to the OneShotController workflow harness.

## Design principles

- Each tool owns one responsibility; no duplications
- Tools are called by `agent/main.py` (the controller), not directly by the workflow
- Failures fail closed — no fabricated success receipts
