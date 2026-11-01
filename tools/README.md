# Tools — OneShot workflow components

This directory contains the active tool implementations used by the OneShot workflow harness. All tools are pure-Python, importable via `tools/` (configured in `conftest.py` and `pyproject.toml`), and tested by the suite in `tests/`.

## Tool inventory

| File | Responsibility |
|------|----------------|
| `task_management.py` | Task state, checkpoints, resume, event log |
| `color_eval.py` | GREEN/AMBER/RED evaluation with evidence |
| `fixtures.py` | FixtureRegistry with independent expected results |
| `search_sources.py` | Repository file search and inventory |
| `text_metrics.py` | Text counting (characters, bytes, words) |
| `build_executor.py` | Build execution with trace and artifact capture |
| `mcp_tools.py` | MCP tool registry (no core logic, permission-gated) |
| `repo_summary.py` | Repository summary with gap matrix |

## Design principles

- Each tool owns one responsibility; no duplications
- Tools are called by `agent/main.py` (the controller), not directly by the workflow
- Failures fail closed — no fabricated success receipts
