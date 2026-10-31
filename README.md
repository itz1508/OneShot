# OneShot — Workflow Harness

The OneShot Workflow Harness executes a multi-phase plan (Research → Plan → Build) with source-grounded evidence, contract validation, and connected E2E verification.

## Verified implementation

| Milestone | Status | Evidence |
|-----------|--------|----------|
| M0 — Source/host discovery | VERIFIED | Git reconciled, 68 files inventoried |
| M1 — Contract checks | VERIFIED | 5 validators + evidence_index_resolver, 38 contract tests pass |
| M2 — Controller continuity | VERIFIED | OneShotController with checkpoint/resume/restart, 20 workflow tests pass |
| M3 — Research artifact generation | VERIFIED | SearchSources + SHA-256 evidence, validate_research 0 errors |
| M4 — Scanner/Gap Fix | VERIFIED | SourceInspection (68 files) + SourceComparison (49 findings, 0 missing) |
| M5 — Fixture/Chaos | VERIFIED | FixtureRegistry 4/4 pass, chaos not_applicable (deterministic) |
| M6 — Build | VERIFIED | context_counter.py E2E 4/4, Color GREEN |
| M7 — Post-Build E2E | VERIFIED | Connected E2E + recovery (checkpoint→restart→resume) + negative checks |
| M8 — Reconcile/cleanup | VERIFIED | README, AGENTS.md, ExecPlan updated |

## Test suite

```
python -m pytest tests/ -v
```

159 passed, 22 skipped. Path resolution is automatic via `conftest.py` and `[tool.pytest.ini_options]` in `pyproject.toml` — no manual `PYTHONPATH` required.

## Key files

- `agent/main.py` — OneShotController (stage routing, Scanner invocation, fixture validation, workflow harness)
- `agent/contracts/models.py` — Pydantic v2 validators for Research/Plan/Build records
- `agent/adapters/repository_inventory.py` — Scanner inventory adapter (wraps host RepositoryInspector)
- `agent/adapters/source_comparison.py` — Scanner comparison adapter (wraps host SourceComparator)
- `tools/fixtures.py` — FixtureRegistry with independent expected results
- `tools/color_eval.py` — GREEN/AMBER/RED evaluation
- `tools/task_management.py` — Task state, checkpoints, resume
- `bin/context_counter.py` — demo build target

## Architecture

The harness uses existing owners — no duplications:
- TaskManager owns task state, checkpoints, resume
- ContractChecker owns record validation
- ColorEvaluator owns GREEN/RED assignment
- Scanner is host-provided (git + hashlib), wrapped by adapters
- FixtureRegistry owns fixture validation with independent oracles

Previous implementation preserved in branch `archive/pre-rebuild-2026-10-29`.

`.gitignore` excludes local credentials, temporary artifacts, and runtime state.
