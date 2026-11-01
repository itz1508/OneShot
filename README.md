# OneShot — Workflow Harness

The OneShot Workflow Harness executes a multi-phase plan (Research → Plan → Build) with source-grounded evidence, contract validation, and connected E2E verification.

## Verified implementation

| Milestone | Status | Evidence |
|-----------|--------|----------|
| M0 — Source/host discovery | VERIFIED | Git reconciled; 68 files inventoried at the M0 commit, 90 tracked on current HEAD |
| M1 — Contract checks | VERIFIED | 5 validators + evidence_index_resolver, 38 contract tests pass |
| M2 — Controller continuity | VERIFIED | OneShotController with checkpoint/resume/restart, 20 workflow tests pass |
| M3 — Research artifact generation | VERIFIED | SearchSources + SHA-256 evidence, validate_research 0 errors |
| M4 — Scanner/Gap Fix | VERIFIED | SourceInspection + SourceComparison wired through the eight-category `CapabilityPreflight` (see G05 below); file / findings counts recorded at the M4 commit |
| M5 — Fixture/Chaos | VERIFIED | FixtureRegistry 4/4 pass, chaos not_applicable (deterministic) |
| M6 — Build | VERIFIED | context_counter.py E2E 4/4, Color GREEN |
| M7 — Post-Build E2E | VERIFIED | Connected E2E + recovery (checkpoint→restart→resume) + negative checks |
| M8 — Reconcile/cleanup | VERIFIED | README, AGENTS.md, ExecPlan updated |

## Test suite

```
python -m pytest tests/ -v
```

On the current HEAD: **374 passed, 55 skipped** across 429 collected tests (19 baseline test modules in `tests/` plus 25 scenario modules in `tests/scenarios/`). Path resolution is automatic via `conftest.py` and `[tool.pytest.ini_options]` in `pyproject.toml` — no manual `PYTHONPATH` required.

## Key files

- `agent/main.py` — OneShotController (stage routing, Scanner invocation, fixture validation, workflow harness)
- `agent/contracts/models.py` — Pydantic v2 validators for Research/Plan/Build records
- `agent/adapters/repository_inventory.py` — Scanner inventory adapter (wraps host RepositoryInspector)
- `agent/adapters/source_comparison.py` — Scanner comparison adapter (wraps host SourceComparator)
- `tools/fixtures.py` — FixtureRegistry with independent expected results
- `tools/color_eval.py` — GREEN/AMBER/RED evaluation
- `tools/task_management.py` — Task state, checkpoints, resume
- `bin/context_counter.py` — demo build target

## Five accepted connected E2E scenarios (S1–S5)

The scenario suite in [`tests/scenarios/`](tests/scenarios/) exercises the real `OneShotController` end-to-end (no mocks) and asserts cross-record invariants with `agent/contracts/models.validate_pipeline` plus the hybrid SHA-256 resolver.

| Scenario | File | Cases | Covers |
| --- | --- | --- | --- |
| **S1 — Plan correction** | `test_s1_plan_correction.py` | 2 | Open critical gap on Plan r1 → BLOCKED; Plan r2 resolves the gap → VERIFIED. |
| **S2 — DO_NOT_USE provenance filter** | `test_s2_do_not_use.py` | 2 | Research retains an unsupported claim; Plan assigns `DO_NOT_USE`; Build admission removes the derived milestone (contradiction handling). |
| **S3 — VALIDATE_FIRST gate** | `test_s3_validate_first.py` | 2 | Gated milestone excluded from admission; stale admission attempt refused with the exact cross-record diagnostic. |
| **S4 — Build contradicts Plan** | `test_s4_build_contradicts_plan.py` | 3 | Plan r1 claims the wrong expected observation; Plan r2 aligns with reality → VERIFIED; both attempts persisted. |
| **S5 — Crash / restart** | `test_s5_crash_restart.py` | 4 | Pre-effect crash, post-effect crash, baseline, and blind-retry — all enforced at-most-once via an independent SQLite observer (interrupted-execution recovery). |

Beyond S1–S5, the lineage drives in `test_g09_s{1,3,4,5}_cli.py`, `test_g09_same_task_cli.py`, and `test_g09_lineage.py` subprocess-run the real `oneshot run` / `oneshot continue` CLI, then open a fresh `TaskManager` on the same storage to assert monotonic `plan.revision` with `preceding_record_id` back-references across a fresh-process readback.

## Gap-analysis / integrity closures

The eleven G01–G11 gap closures sit on top of the M-milestones. The acceptance tests live in `tests/scenarios/test_g{05..11}_*.py`, `test_oracles_identity.py`, and `test_scanner_semantic_detectors.py`.

- **G01** — frozen `CaseDefinition` + `OracleCatalog` + `ORACLE_CATALOG_REVISION`.
- **G02** — AST-level semantic detectors (duplication, contradictions, coverage, dependencies), with CLI-entrypoint exemption on duplication.
- **G03** — `expected_rejection` shape required on negative fixtures.
- **G04** — no fault injectors in the oracle module.
- **G05** — `CapabilityPreflight` wired into Plan review; non-VALID blocks resolution.
- **G06** — bounded retry refuses no-change (same-identity) attempts.
- **G07** — `ManifestBinding` is mandatory on complete Builds; `scanner_identity` is a sha-of-source; `validate_pipeline` independently recomputes `fixture_oracle_sha` and `build_receipt_sha` and refuses mismatch.
- **G08** — trusted-test input gated by `ONESHOT_TRUSTED_TEST_INPUT=1`.
- **G09** — `continue` CLI subcommand preserves durable `plan.revision` / `plan.preceding_record_id` / `plan.preceding_revision` lineage across a fresh-process readback.
- **G10** — VERIFIED requires `all_pass AND cross_record_errors == []`.
- **G11** — durable, revision-safe `TaskManager`: portable file lock, atomic replace, fail-closed `CorruptStoreError` on every reload (initial AND mid-run), and public `set_decision_wait` / `set_task_metadata(if_revision=…)` CAS API.

## Provider abstraction

OneShot never hard-codes a vendor. Every model call routes through:

```
ProviderConfig → ProviderRegistry → ProviderAdapter → OneShotController
```

`provider` / `model` / `endpoint` are three independent configuration axes — e.g. Meta Llama can run through many endpoints, each with different capabilities declared by its adapter. Unsupported capabilities are reported explicitly as `UnsupportedCapabilityError`, never silently downgraded.

- Default adapter: `echo` (deterministic, zero deps). Used by tests and CI.
- Install `pip install 'oneshot[openai]'` or `pip install 'oneshot[anthropic]'` to add the matching vendor SDK; the registered adapter stub picks it up automatically.
- See `agent/providers/` for the registry, the adapter Protocol, and the capability matrix. The full architecture rules live in [`AGENTS.md`](AGENTS.md#provider-abstraction--one-unified-client-many-adapters).

## Architecture

The harness uses existing owners — no duplications:
- TaskManager owns task state, checkpoints, resume
- ContractChecker owns record validation
- ColorEvaluator owns GREEN/RED assignment
- Scanner is host-provided (git + hashlib), wrapped by adapters
- FixtureRegistry owns fixture validation with independent oracles

Previous implementation preserved in branch `archive/pre-rebuild-2026-10-29`.

`.gitignore` excludes local credentials, temporary artifacts, and runtime state.
