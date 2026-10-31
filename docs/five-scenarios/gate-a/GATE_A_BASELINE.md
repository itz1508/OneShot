# Gate A — Source and Baseline (read-only)

Captured: 2026-10-31T23:41:49Z

## A01 — Physical source identity

```
repo_root  = /work/OneShot-git
branch     = feat/five-contract-scenarios
HEAD       = bba1a26905f819d5c3c874ae069563e591a4cf5f
main_head  = bba1a26905f819d5c3c874ae069563e591a4cf5f
remote     = https://github.com/itz1508/OneShot
status     = 1 tracked changes
```

## A02 — Documentation and configuration inventory

| File | Lines | Purpose |
|------|------:|---------|
| `AGENTS.md` | 173 | present |
| `README.md` | 49 | present |
| `agent/contracts/README.md` | 44 | present |
| `tools/README.md` | 27 | present |
| `pyproject.toml` | 73 | present |
| `.github/workflows/ci.yml` | 53 | present |
| `Makefile` | 33 | present |
| `conftest.py` | 9 | present |

## A03 — Source tree and controller surface

Lines-of-code (source only, no __init__):

```
    32 agent/adapters/evidence_locator.py
    42 agent/adapters/content_integrity.py
    58 tools/text_metrics.py
   101 agent/adapters/repository_inventory.py
   101 agent/adapters/trace_projection.py
   119 tools/search_sources.py
   128 tools/mcp_tools.py
   145 tools/build_executor.py
   159 agent/adapters/source_comparison.py
   162 tools/fixtures.py
   188 tools/task_management.py
   243 tools/color_eval.py
   276 tools/repo_summary.py
   391 agent/output_registry.py
   605 agent/gap_analysis.py
  1465 agent/contracts/models.py
  1539 agent/main.py
  5756 total
```

OneShotController public methods:

```
131:    def __init__(self):
134:    def register(self, desc: CapabilityDescriptor) -> None:
141:    def get(self, cap_id: str) -> CapabilityDescriptor | None:
147:    def list_capabilities(self) -> list[CapabilityDescriptor]:
150:    def check_effect(self, cap_id: str, requested_effect: str) -> bool:
171:    def _resolve(ref: str) -> bool:
193:    def resolve(ref: str) -> bool:
217:    def __init__(self, storage_path: str | None = None):
224:    def _register_default_capabilities(self) -> None:
241:    def start_task(self, request_ref: str, metadata: dict | None = None) -> str:
253:    def transition_stage(self, task_id: str, to_stage: WorkflowStage, detail: str = "") -> None:
265:    def request_user_decision(
294:    def provide_user_decision(self, task_id: str, input_request_id: str, answer: str) -> bool:
312:    def has_pending_decision(self, task_id: str) -> UserDecisionWait | None:
319:    def checkpoint(self, task_id: str, checkpoint_data: dict) -> None:
323:    def resume(self, task_id: str) -> dict | None:
330:    def complete_task(self, task_id: str, results: dict) -> None:
334:    def fail_task(self, task_id: str, error: str) -> None:
338:    def run_gap_analysis(
353:    def run_gap_recheck(self, previous_result: dict, repo_root: str | None = None) -> dict:
361:    def run_capability_preflight_with_correction(
440:    def get_status(self, task_id: str) -> dict:
460:    def list_tasks(self) -> list[dict]:
478:    def research_plan(self, task_id, objective, repo_root):
715:    def review_research_plan(self, task_id, research, evidence_index, repo_root):
1149:    def build_plan(self, task_id, plan, evidence_index, repo_root):
1416:    def run_workflow(self, objective, repo_root, storage_path=None):
```

## A04 — Baseline tooling

```
python  : Python 3.11.18
pytest  : pytest 9.2.0
ruff    : ruff 0.17.3
mypy    : mypy 2.4.1 (compiled: yes)
```

Test suite:

```
281 passed, 55 skipped in 15.01s
```

Lint:

```
All checks passed!
```

Type check:

```
Success: no issues found in 21 source files
```

## A05 — Test inventory (per-file)

```
tests/test_agent_e2e.py: 14
tests/test_agent_workflow.py: 20
tests/test_authorization.py: 10
tests/test_capability_preflight.py: 54
tests/test_color_eval.py: 9
tests/test_content_integrity.py: 4
tests/test_contract_models.py: 42
tests/test_evidence_locator.py: 3
tests/test_gap_analysis.py: 15
tests/test_memory_retrieve.py: 6
tests/test_output_registry.py: 44
tests/test_repo_summary.py: 12
tests/test_repository_inventory.py: 4
tests/test_research_plan_build.py: 34
tests/test_source_comparison.py: 8
tests/test_task_management.py: 6
tests/test_text_metrics.py: 7
tests/test_trace_projection.py: 6
tests/test_workflow_contracts.py: 38

```

Skip reasons (from `-rs`):

```
SKIPPED [1] tests/test_authorization.py:123: D1: no host-permission surface in current source — ExecPlan D1.
SKIPPED [1] tests/test_authorization.py:127: D1: no binding verification surface in current source — ExecPlan D1.
SKIPPED [1] tests/test_authorization.py:131: D1: no model-text rejection surface in current source — ExecPlan D1.
SKIPPED [1] tests/test_content_integrity.py:20: Real V18 FileStore not installed
SKIPPED [1] tests/test_content_integrity.py:28: Real V18 FileStore not installed
SKIPPED [1] tests/test_content_integrity.py:36: Real V18 FileStore not installed
SKIPPED [1] tests/test_content_integrity.py:42: Real V18 FileStore not installed
SKIPPED [1] tests/test_gap_analysis.py:115: GapAnalysisSpecialist removed; see test_capability_preflight.py
SKIPPED [1] tests/test_gap_analysis.py:126: GapAnalysisSpecialist removed; see test_capability_preflight.py
SKIPPED [1] tests/test_gap_analysis.py:142: GapAnalysisSpecialist removed; see test_capability_preflight.py
SKIPPED [1] tests/test_gap_analysis.py:154: GapAnalysisSpecialist removed; see test_capability_preflight.py
SKIPPED [1] tests/test_gap_analysis.py:171: GapAnalysisSpecialist removed; see test_capability_preflight.py
SKIPPED [1] tests/test_gap_analysis.py:186: GapAnalysisSpecialist removed; see test_capability_preflight.py
SKIPPED [1] tests/test_gap_analysis.py:199: GapAnalysisSpecialist removed; see test_capability_preflight.py
SKIPPED [1] tests/test_gap_analysis.py:241: GapAnalysisSpecialist removed; see test_capability_preflight.py
SKIPPED [1] tests/test_gap_analysis.py:247: GapAnalysisSpecialist removed; see test_capability_preflight.py
SKIPPED [1] tests/test_gap_analysis.py:257: GapAnalysisSpecialist removed; see test_capability_preflight.py
SKIPPED [1] tests/test_gap_analysis.py:63: GapAnalysisSpecialist removed; see test_capability_preflight.py
SKIPPED [1] tests/test_gap_analysis.py:88: GapAnalysisSpecialist removed; see test_capability_preflight.py
SKIPPED [1] tests/test_gap_analysis.py:99: GapAnalysisSpecialist removed; see test_capability_preflight.py
SKIPPED [1] tests/test_repository_inventory.py:19: Real V18 Scanner not installed
SKIPPED [1] tests/test_repository_inventory.py:33: Real V18 Scanner not installed
SKIPPED [1] tests/test_repository_inventory.py:46: Real V18 Scanner not installed
SKIPPED [1] tests/test_repository_inventory.py:54: Real V18 Scanner not installed
SKIPPED [1] tests/test_source_comparison.py:101: Real V18 comparison owner unavailable
SKIPPED [1] tests/test_source_comparison.py:26: Real V18 comparison owner unavailable
SKIPPED [1] tests/test_source_comparison.py:42: Real V18 comparison owner unavailable
SKIPPED [1] tests/test_source_comparison.py:54: Real V18 comparison owner unavailable
SKIPPED [1] tests/test_source_comparison.py:62: Real V18 comparison owner unavailable
SKIPPED [1] tests/test_source_comparison.py:73: Real V18 comparison owner unavailable
SKIPPED [1] tests/test_source_comparison.py:79: Real V18 comparison owner unavailable
SKIPPED [1] tests/test_source_comparison.py:83: Real V18 comparison owner unavailable
SKIPPED [1] tests/test_trace_projection.py:20: Real V18 trace reader unavailable
SKIPPED [1] tests/test_trace_projection.py:32: Real V18 trace reader unavailable
SKIPPED [1] tests/test_trace_projection.py:40: Real V18 trace reader unavailable
SKIPPED [1] tests/test_trace_projection.py:44: Real V18 trace reader unavailable
SKIPPED [1] tests/test_trace_projection.py:53: Real V18 trace reader unavailable
SKIPPED [1] tests/test_trace_projection.py:59: Real V18 trace reader unavailable
SKIPPED [3] tests/test_research_plan_build.py: D2: tools/research_review.py retired by d90b655 — ExecPlan D2 decision pending.
SKIPPED [4] tests/test_research_plan_build.py: D2: tools/plan_review.py retired by d90b655 — ExecPlan D2 decision pending.
SKIPPED [5] tests/test_research_plan_build.py: D2: tools/approval.py retired by d90b655 — see tests/test_authorization.py for the migrated user-approval surface.
SKIPPED [5] tests/test_research_plan_build.py: D2: tools/research_output.py retired by d90b655 — ExecPlan D2 decision pending.
```

## A06 — Effect-observer availability

Per approved design (user authorization of 2026-10-31):

- **Observer target**: isolated SQLite DB in a temp directory per test case
- **Observer process boundary**: separate OS process (`subprocess.Popen`)
- **Observer independence**: direct `sqlite3` query of committed external state, not routed through TaskManager
- **Observer cleanup**: `tempfile.TemporaryDirectory` scope
- **Not available in sandbox**: no real external service / live host; this is the deliberate test design ("disposable local fixture repositories and an externally observed, durable effect target" — ExecPlan G)

## Gate A verdict

PASS. No source edits made. Baseline is reproducible and the HEAD / branch / status snapshot above is the pre-edit reference for Gate H diff work.
