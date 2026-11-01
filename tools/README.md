# Tools — OneShot workflow primitives

Reusable, pure-Python primitives used by `agent/main.py::OneShotController`. Each module owns ONE responsibility; the controller does the orchestration. All modules are importable via `tools/` (configured in `conftest.py` and `pyproject.toml`) and exercised by the suite in `tests/`.

## Tool inventory

| File | Responsibility | Test module |
|------|----------------|-------------|
| `task_management.py` | Task state, events, checkpoints, resume, atomic/CAS persistence (`set_task_metadata(if_revision=…)`, `set_decision_wait`, `CorruptStoreError` fail-closed on every reload) | `tests/test_task_management.py` + `tests/scenarios/test_g11_persistence.py` |
| `color_eval.py` | GREEN / YELLOW / RED evaluation with evidence; one RED collapses the overall color | `tests/test_color_eval.py` |
| `fixtures.py` | FixtureRegistry with independent expected results and the G03 `expected_rejection` shape | `tests/test_research_plan_build.py::TestFixtures` + `tests/scenarios/test_fixtures_negative_shape.py` |
| `search_sources.py` | Repository file inventory via `git ls-tree` / `git grep` (same view the agent-read deny list sees) | `tests/test_research_plan_build.py::TestSearchSources` |
| `scanner/__init__.py` + `scanner/__main__.py` | `scan_match_variable` extracts names/pattern matches, `scan_edit_change` previews immutable digest-bound changes, `scan_edit_write` requires explicit Build-only authorization and allowed paths, and `scan_filesystems` inventories Git-visible files; JSON-stdin CLI is `python -m tools.scanner` | `tests/test_scanner_api.py` |
| `text_metrics.py` | Deterministic text counting (Unicode code points, UTF-8 bytes, whitespace words) — zero external calls | `tests/test_text_metrics.py` |
| `build_executor.py` | Build execution with SHA-256 artifact hashes, Agent → Tool → Result tracing, and 06.6 authorization refusal of a non-callable `tool_fn` | `tests/test_research_plan_build.py::TestBuildExecutor` + `tests/scenarios/test_build_executor_authorization.py` |

The optional root `Scanner.ts` is a typed facade over the Python `tools.scanner` CLI, not a second scanner implementation. Audit Discovery may use matching, preview, and inventory only. The effectful write function is an explicitly authorized Build-only operation; the caller still owns Build admission and durable receipts.

## Design principles

- Each tool owns one responsibility; no duplications. Nothing in `tools/` orchestrates — orchestration lives in `agent/main.py::OneShotController`.
- Failures fail closed. No fabricated success receipts, no silent swallow of exceptions, no "any exception counts as pass" (see the G03 `expected_rejection` fix in `fixtures.py`).
- Scanner / inventory primitives shell out to `git` so their view matches `git grep` and the agent-read deny list in `.agents/settings.json`.
- Previously-tracked modules (`approval.py`, `memory_retrieve.py`, `plan_review.py`, `research_output.py`, `research_review.py`, `mcp_tools.py`, `repo_summary.py`) were consolidated into `agent/main.py` and `agent/adapters/` during the OneShotController migration. The RepoSummary / MCPToolRegistry stacks were the last remnants of the retired 00–11 numbered-prompt set and are no longer referenced by live code.

## Related

- Provider abstraction lives in [`agent/providers/`](../agent/providers/) — unified request/response/capabilities, registry factory, and the deterministic `EchoAdapter` reference. See the [AGENTS.md Provider abstraction section](../AGENTS.md#provider-abstraction--one-unified-client-many-adapters) for the ownership rule and `UnsupportedCapabilityError` contract.
- Prompt Authoring lives in [`agent/prompt_authoring/`](../agent/prompt_authoring/) — generates / evaluates / versions reusable prompts for the Research / Plan / Build roles. See the [AGENTS.md Prompt Authoring section](../AGENTS.md#prompt-authoring--development-capability-not-a-workflow-stage) for the status machine and ownership boundaries.
