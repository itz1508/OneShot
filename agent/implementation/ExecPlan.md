# OneShot Workflow Harness — Executable Build Plan

**Status:** Proposed / not implemented.  
**Plan date:** 2026-10-29 (America/Los_Angeles).  
**Authoritative Git source:** `itz1508/OneShot`, branch `main`; resolve the current commit when executing.  
**Unverified active source:** The Databricks working copy was reported to have `tools/` with an incomplete staged `src/` migration. Reinspect that physical working tree before editing; GitHub `main` is not proof of its state.  
**Relevant committed contracts:** `agent/contracts/{research.yaml,plan.yaml,build.yaml,check_contracts.py,README.md}` and `tests/test_workflow_contracts.py`.

## Purpose and user-visible result

OneShot must accept an objective, investigate it using actual evidence, produce a research plan and independent acceptance examples, review and correct an executable plan, then execute that *specific* plan using the host's existing tools. It must validate implementation results and then run genuine post-build end-to-end (E2E) tests. A user can see a single task ID and retrieve its Research, Plan, Build, gap corrections, validation receipts, and final outcome after an interruption. The task must not report success when any required stage or actual E2E remains unverified.

**Demo:** Request a small context-counter CLI. Research defines exact Unicode character/byte behavior and independent examples; Plan selects files, tests, and commands; Scanner checks drift, gaps, overlap, and duplicates; Fixture Validation + Chaos validates expectations and failures before Build; Build creates the CLI; E2E invokes its real entrypoint with known inputs, corrupt inputs and a controlled restart. Results are compared against expectations defined *before* implementation. The run must resume by task ID without duplicate effects.

## Authoritative choices and exclusions

1. **Established workflow:** Research → Artifact Output → Plan → Scanner Gap Analysis → Gap Fix + Scanner recheck → Fixture Validation + Chaos → Build → Implementation Validation → post-Build E2E → Complete. Failures route to the responsible earlier responsibility for correction and affected revalidation. Do not create separate mandatory stages for Gap Fix, Chaos or E2E ownership.
2. **One controller:** `agent/main.py` performs routing, host calls, transitions and continuation; detailed Research, Plan and Build instructions live in Markdown. Optional specialist execution is via host-supported operations, not three competing controllers. `research.ts`, `plan.ts`, `build.ts` are *illustrative shorthand*; no TypeScript application exists in the verified public tree.
3. **One persistence owner:** Reuse the active host / Task Management store and its artifact resolver. The YAML contracts are record *shapes*; they are not a second filesystem store or executable scripts. The plan's artifact paths below are logical destinations; map them to the existing store before implementation.
4. **One Scanner owner:** Gap Analysis invokes the existing System Scanner through a verified tool interface and records genuine tool receipts. Do not reimplement Scanner or treat the historical `src/repo_summary.py` as equivalent to the System Scanner.
5. **Source authority:** Latest accepted user requirements override conflicting historical 00–11 prompts. Old sources may provide reusable code but never determine desired design. No fabricated `UserPromptSubmit` hook, authorization service, Quality Input Python subsystem, automatic model/provider installation, or automatic old-module restoration.
6. **Host interaction:** A specialist does not directly ask the user; it returns structured missing information to the Main Agent. Ask only for a blocking user-owned choice after attempting resolution from accepted context; record the answer and resume. Actual tool/hook names must be discovered, not assumed.
7. **Scope:** Build the workflow harness and its test evidence, not unrelated OneShot System Summarizer, UI, plugin viewer, deployment or release features. Do not alter unrelated staged/unstaged changes. Destructive retirement of old files requires source/evidence reconciliation and authorized scope.

## Verified repository inputs and known technical gaps

At the inspected GitHub commit, `agent/contracts/*.yaml`, `agent/contracts/check_contracts.py` and `tests/test_workflow_contracts.py` are present; no `agent/main.py`, root `pyproject.toml`, or root `package.json` is present. `src/` contains historical modules, while the actual Databricks workspace was reported to use `tools/`.

- `agent/contracts/check_contracts.py:117–138` exposes `validate_records(research, plan, build, resolve)`. It verifies all stages together. **Gap:** Research must validate before Plan exists, and Plan before Build exists. Add stage-specific validation of instantiated records, preserving the final combined validation and evidence resolver. Never fabricate empty downstream completed records. **Receipt bootstrap gap:** `_base()` at lines 103–111 requires `handoff.validation_receipt_ref` to validate a completed handoff, although that receipt is typically created *by* successful validation. Use a two-step, revision-guarded host process (preflight substantive evidence and derive readiness → persist a signed/hashed validation receipt → revalidate the committed record including receipt) without accepting self-attested evidence or creating recursive receipt requirements.
- `agent/contracts/check_contracts.py:189–258` checks Plan's Scanner calls, gap dispositions, fixture prevalidation, and stale revisions. The host must actually invoke Scanner, verify receipts, and correct findings; setting fields is not proof.
- `agent/contracts/check_contracts.py:260–338` checks Build milestones, actual requested result, real E2E, and chaos outcomes. The host must bind observed outcomes and evidence to the specific plan revision and task.
- `src/task_management.py` implements a task list and JSON save/restore, but its `_save()` uses direct file replacement and the reviewed portion has no revision-guarded compare-and-swap. Audit the active `tools/task_management.py` before relying on atomic, concurrent or retry semantics. Improve within its existing ownership only if needed.
- `src/search_sources.py` lists `HEAD` with `git ls-tree`, which omits added/untracked and can misrepresent deleted/modified active files. Verify current working-tree inventory separately.
- `src/plan_review.py` currently does simple truthiness checks against `actual_code` and a `practices` mapping; that is **not** Scanner-based drift/overlap/duplication analysis.
- `src/fixtures.py` has a negative-case helper where any exception is treated as success and nonmatching output can pass; do not use such tests as independent correctness oracles without replacement.
- `src/build_executor.py` accepts injected callables in steps; a callback trace alone is not evidence that the intended host ran a tool. Distinguish simulated tool calls from live execution.
- `src/mcp_tools.py` is a local registry; no inspected evidence proves a connected Databricks System Scanner tool in GitHub. Discover actual host interface before calling it.

**Research basis:** Current OpenAI Agents SDK supports manager-style agent orchestration, tools, state and tracing; Codex ExecPlan guidance requires self-contained milestone and decision logs; LangGraph's durable execution guidance emphasizes checkpointed tasks and idempotency for side effects; MCP user elicitation is host/client-capability dependent. These are design references, *not required package selections*. Source URLs are in the final section.

## Proposed repository file / folder structure

```text
OneShot-repo/
├── AGENTS.md                                  # install accepted existing guide if absent
├── README.md                                  # update only after real implementation
├── agent/
│   ├── main.py                                # CREATE: single controller + thin host bridge
│   ├── reference/
│   │   ├── research_guidance.md               # CREATE: research decisions and output steps
│   │   ├── plan_guidance.md                   # CREATE: plan, Scanner gaps, correction, fixture chaos
│   │   └── build_guidance.md                  # CREATE: implementation, checks, post-build E2E
│   ├── templates/                             # CREATE only after reconciling actual catalog
│   │   ├── research_input.md
│   │   ├── output_plan.md
│   │   ├── output_fixture.md
│   │   ├── output_success_criteria.md
│   │   ├── output_validation.md
│   │   └── execplan.md
│   └── contracts/
│       ├── research.yaml                     # KEEP; minor verified changes if required
│       ├── plan.yaml                         # KEEP; minor verified changes if required
│       ├── build.yaml                        # KEEP; minor verified changes if required
│       ├── check_contracts.py                # EXTEND: per-stage validation + final check
│       └── README.md                         # UPDATE: usage and handoff instructions
├── tools/                                     # ACTIVE WORKSPACE ONLY: verify actual files
│   └── <existing_verified_tools>             # reuse, correct or retire by evidence
├── tests/
│   ├── test_workflow_contracts.py            # EXTEND: stage-specific, stale, malformed states
│   ├── test_agent_workflow.py                # CREATE: routing, corrections, resume
│   └── test_agent_e2e.py                     # CREATE: real host + built context-counter
└── <existing_task_storage>/                  # discover in host; DO NOT add a new owner
```

`AGENTS.md` and the template catalog may already exist in the Databricks workspace; **compare before creating**. Reference paths are source-control instructions, not automatically loaded prompts or registered hooks. Use the existing artifact store; the following are example **logical artifact names**, not instructions to add a competing database:

```text
<task_id>/research/todo_search.md
<task_id>/research/evidence.md
<task_id>/research/plans.md                  # Research candidate, not accepted ExecPlan
<task_id>/research/fixture_<case>.md
<task_id>/research/success_criteria_<case>.md
<task_id>/research/validation.md
<task_id>/plan/ExecPlan.md                     # authoritative plan once reviewed
<task_id>/build/implementation_evidence.md
<task_id>/build/e2e_evidence.md
```

### File-by-file actions

| Area | Existing | Proposed action | Outcome |
| --- | --- | --- | --- |
| Controller | `agent/main.py` absent on GitHub | Create after host discovery | One start/resume/status/validate command surface and stage routing |
| Research | `agent/contracts/research.yaml` | Keep; populate via research guidance and existing templates | Evidence-backed candidate plan, fixtures, criteria and trace |
| Plan | `agent/contracts/plan.yaml` | Keep; populate from accepted Research | Exact executable plan with Scanner gaps and corrections |
| Build | `agent/contracts/build.yaml` | Keep; populate from accepted Plan revision | Real work receipts, results, implementation checks, E2E |
| Checker | `agent/contracts/check_contracts.py` | Extend; retain existing final interface | Stage handoffs validated before downstream record creation |
| Task storage | Current active `tools/task_management.py` to inspect | Reuse; repair atomicity/version checks only if necessary | Stable task IDs, checkpoint/revision safety, no duplicate work |
| Source/scanner tools | Active `tools/`, System Scanner interface | Verify and adapt calls; do not create scanner | Evidence-located drift, overlap, duplication, missing/contradiction reports |
| Legacy `agent/research`, `agent/plan`, `agent/build` numbered Markdown | Old assignments in GitHub | Treat as historical evidence, map useful instructions | No superseded assignments remain operative |
| Tests | `tests/test_workflow_contracts.py` and older `tests/` | Extend and replace invalid tests after independent review | Meaningful workflow and actual E2E assertions |
| Documentation | `agent/contracts/README.md`, `README.md`, `TRACEABILITY.md` | Update based on actual verified behavior | Reproducible CLI and no stale architecture claims |

## Execution behavior and function contracts

The controller has one task ID. It calls **logical actions** whose Python implementations can be functions in `agent/main.py`; Markdown templates define required content, not executable imports. Host operations must use the host's actual SDK/tool APIs.

```python
# Illustrative signatures, NOT functioning host/tool integrations.
def start_task(request_ref: str) -> str: ...            # returns stable task_id
def research_plan(task_id: str) -> str: ...             # returns completed Research record_id
def review_research_plan(task_id: str, research_id: str) -> str: ...
                                                      # returns reviewed Plan record_id
def gap_analysis_and_fix(task_id: str, plan_id: str) -> str: ...
                                                      # returns rechecked Plan revision

def fixture_validation_chaos(task_id: str, plan_id: str) -> str: ...
                                                      # returns validated fixture manifest

def build_plan(task_id: str, plan_id: str) -> str: ...  # returns Build record_id
def validate_build_and_e2e(task_id: str, build_id: str) -> str: ...
                                                      # verified result or failure routing
```

**Research (`research_plan`)**
1. Read original request and accepted context; inspect active workspace. Determine necessary inputs without guessing. When truly blocking user-owned information is absent, return a structured request to Main Agent and checkpoint; do not make the specialist ask directly.
2. Read `research_guidance.md`. Create/maintain `todo_search.md` with questions, expected sources, paths, progress. Call actual search/repository/official-reference tools, inspect results, record source identity, revisions and contradictions.
3. Challenge weak proposals with alternatives and evidence; distinguish supported, contradicted, uncertain and not-checked material.
4. Populate `output_plan.md` to produce `plans.md` (candidate plan), `output_fixture.md` to produce independent fixture cases, `output_success_criteria.md` to produce measurable acceptance criteria, and `output_validation.md` for Research assessment. Artifacts preserve original requirement IDs.
5. Fill `research.yaml` as an instantiated record; validate Research *alone* with actual evidence resolver. If incomplete, rerun focused research. Only a passing evidence-backed handoff creates Plan.

**Plan (`review_research_plan`)**
1. Read the exact Research record ID, revision and manifest; detect stale source. Confirm every in-scope requirement maps to evidence, planned file changes, fixtures and criteria.
2. Inspect actual target files, dirty state, runtime, dependencies and commands. Promote candidate `plans.md` to self-contained `ExecPlan.md` with exact file destinations, working directories, milestones, rollback/resume strategy, expected observations and decision log.
3. Invoke **System Scanner** with actual scope: active repository + accepted objective/requirements + Research artifacts + proposed Plan. Retain tool identity, inputs, revisions, evidence locations and receipt. Analyze missing, drift, overlap, duplication, contradictions, dependencies, feasibility, coverage, potential leakage and regressions (supported by Scanner; classify unimplemented checks as not checked).
4. Gap Fix corrects all confirmed actionable in-scope issues regardless of stage. A missing research fact returns to Research; Plan errors correct the Plan; faulty oracle definitions return to fixture preparation; post-build faults correct the proper source. Every fix gets a cause, action, evidence and recheck. No silent drops or unapproved critical deferrals.
5. Rerun Scanner on changed Plan revision and impacted artifacts. Independently review fixture inputs, expected outputs, errors, negative/boundary cases and **chaos fault/recovery cases** before Build. Chaos cases are defined and prevalidated here, executed against the real system in post-build E2E.
6. Validate Plan *alone* against the current Research revision, Scanner receipts, corrected gaps and fixture/chaos evidence. Only a passing handoff permits Build, bound to an exact Plan record ID and revision.

**Build (`build_plan`)**
1. Load exact verified Plan ID + revision and manifest, not `latest` or memory. Inspect current target state; on material drift, return to Plan/Gap Fix before executing.
2. Use the existing host's authorized tools; execute milestones, capture real commands and outputs and persist receipts/checkpoints after each side effect. Never pass raw executable instructions from untrusted Research content to tools without applying actual host policy.
3. Run focused implementation validation per milestone; if failing, diagnose root cause and route through the same Gap Fix responsibility, update affected Plan/fixtures when needed, and revalidate.
4. **Mandatory post-Build E2E:** start the actual built entrypoint in an appropriate test environment; run prevalidated normal, negative, boundary and applicable chaos/recovery cases; compare observations with independent oracle values; independently check the *actual user-requested result*. Check source/artifact manifests and relevant re-runs after corrections.
5. Only after observed E2E and acceptance results pass, validate all three current records together, mark Build `outcome.status: verified` and `handoff.ready: true` with supported receipts, and return an accessible artifact/result. Do not claim success based solely on files existing, synthetic tool traces or passing schema tests.

### States, hooks and stopping

- Logical statuses: `draft`, `in_progress`, `blocked`, `failed`, `complete`; `complete` is derived from validated evidence, not an instruction to the agent to stop early.
- Events: `research_completed`, `plan_reviewed`, `scanner_checked`, `gap_fixed`, `fixture_chaos_prevalidated`, `build_milestone_completed`, `e2e_checked`. These are **logical event names**, *not claims of host-supported hook APIs*. Map to actual host callbacks or tool results on discovery.
- Continue automatically to the next verified milestone. Limit correction loops by **progress evidence**: an unchanged issue/receipt must not count as a fix. On repeated no-progress failure, stop blocked with root cause and next available action; do not pretend success or loop without bound.
- Persist action IDs, upstream revisions, artifact identities/hashes and side-effect receipts. On resume inspect external effects, reconcile uncertain writes, and skip independently verified completed actions. Revalidation is required if inputs/revisions changed.
- Lightweight direct tasks may use an internally compact path but must still respect accepted requirements and truthful validation. The full Research–Plan–Build contract path applies to substantial tasks like the harness itself; don't fabricate a Research run to decorate a trivial command.

## Milestones and acceptance

> Each milestone ends with updated ExecPlan Progress, Surprises, Decision Log, outcomes and commands actually run. Commands below are **commands to implement/test**, not claims they already work in the target environment. Use its configured runner; do not install `uv`, Node or providers unless current manifests authorize it.

### M0 — Source and host discovery

**Files:** active repo `.git`, `agent/`, `tools/` (if present), `src/` (historical in public tree), `tests/`, host API/Scanner registration, actual project configs.  
**Steps:** `git status --short`; `git ls-files`; inspect `agent/contracts/*.yaml`, `agent/contracts/check_contracts.py`, active Task Management and tool invocation APIs. Identify how existing host creates tasks, invokes model/tool operations, resolves evidence, pauses for user input, checkpoints and resumes. Capture manifest/branch, dirty paths, runtime, interpreter, Scanner capabilities and restrictions.  
**Proof:** Inventory and responsibility map names one owner per operation, confirms active `tools/`, lists working callable interfaces and unavailable interfaces, and preserves uncommitted edits. If live host unavailable, mark integration blocked, not implemented.

### M1 — Stage-specific contract checks

**Files:** `agent/contracts/check_contracts.py`, `tests/test_workflow_contracts.py`, `agent/contracts/README.md` (and YAML templates only where actual fields need correction).  
**Steps:** Add library checks for Research handoff given Research only; Plan handoff given accepted Research+Plan only; full final Research+Plan+Build check. Preserve `validate_records()` for completion checks and the host-backed artifact resolver; guard malformed nested structures. Bind each validation to observed revisions and manifest hashes, not only asserted flags. Resolve the handoff receipt circularity with a two-step validation/receipt-commit protocol; test concurrent revision changes between preflight and commit. Keep record validation aligned with the active contracts; when fields change, update templates, checker and tests together without introducing contract-version labels.  
**Command:** `python -m unittest discover -s tests -p 'test_workflow_contracts.py' -v` (or configured runner).  
**Proof:** Research can be validated before Plan creation, Plan before Build creation. Draft/unsupported/partial/malformed/stale/forged-reference records fail explicitly. Stale concurrent revisions cannot be committed ready; validation-receipt creation has no circular dependency. Existing 22 focused contract tests continue passing.

### M2 — Main controller and task continuity

**Files:** `agent/main.py`, verified active Task Management tool only if real missing behavior is reproduced, `tests/test_agent_workflow.py`.  
**Steps:** Implement host-capability discovery, task start, workflow selection, stage dispatch, checkpointed continuation and resume. Do not build a second agent inference loop, scanner, store or auth subsystem. Expose a documented CLI if supported: `python agent/main.py start --request-file <path>`, `python agent/main.py resume --task-id <id>`, `python agent/main.py status --task-id <id>`. Connect the controller to existing read/write tool bridge and resolve artifact revisions.  
**Proof:** Task ID survives restart; repeated start/resume does not duplicate completed effects; crash immediately after external action is reconciled; missing host/Scanner reports blocked rather than simulated success. `python agent/main.py --help` works after implementation.

### M3 — Real Research and artifact generation

**Files:** `agent/reference/research_guidance.md`, reconciled `agent/templates/{research_input,output_plan,output_fixture,output_success_criteria,output_validation}.md`, `agent/main.py`, tests.  
**Steps:** Implement template selection/population, evidence-grounded search using actual host, requirement IDs, sources, contradictions, independent oracles, candidate plan and review. Handoff uses M1 Research-only validation.  
**Proof:** Real context-counter objective generates `todo_search`, evidence, candidate `plans.md`, fixture and criterion artifacts whose refs resolve. Unsupported citations or missing required fields block handoff. No automatic questions for researchable facts; blocking user-owned choices return to Main Agent.

### M4 — Plan, Scanner and universal Gap Fix

**Files:** `agent/reference/plan_guidance.md`, `agent/templates/execplan.md`, `agent/main.py`, relevant existing Scanner bridge/tool, tests.  
**Steps:** Derive precise ExecPlan from Research, invoke actual System Scanner with current revision and scope, classify all actionable issues, correct root causes, persist decisions and recheck Scanner. Route gaps from later stages back to Research/Plan/fixtures/Build as appropriate.  
**Proof:** Deliberately introduce missing work, requirement drift, duplicate responsibility, conflicting requirements and stale Plan revisions. Scanner returns evidence or explicitly `not_checked`; the actual fix and recheck resolve supported defects. No false `complete` on only changing gap status.

### M5 — Fixture Validation + Chaos pre-Build

**Files:** `agent/reference/plan_guidance.md`, fixture/chaos artifacts, `agent/main.py`, tests.  
**Steps:** Validate oracle provenance *before* implementation, ensure normal/negative/boundary/error coverage and expected fault detection/recovery. Chaos must be defined under `fixture_validation_chaos` in `plan.yaml`, not an independent stage/controller.  
**Proof:** Wrong oracle, missing expected error, missing recovery assertion, fixture copied from implementation output and unjustified chaos exclusion all fail or become explicitly blocked. Passing preflight means fixtures are ready—not that the built product passed them.

### M6 — Build and implementation validation

**Files:** `agent/reference/build_guidance.md`, `agent/main.py`, verified host build/tool APIs, tests.  
**Steps:** Pin accepted Plan ID/revision, execute real host operations and commands, capture changed files, artifact hashes, milestone receipts, errors and validation. Persist checkpointer state at safe boundaries.  
**Proof:** A context-counter CLI is truly created and runnable; a failed command cannot be recorded as passed; editing a Plan invalidates Build readiness; interruption after side effect cannot silently duplicate it.

### M7 — Mandatory post-Build E2E + regression evaluation

**Files:** `tests/test_agent_e2e.py`, relevant real test harness/CLI, `agent/main.py`; existing YAML/README only if required.  
**Steps:** Start the actual built context-counter executable. Compare independent Unicode/byte/word/count expectations, invalid inputs, actual user result and applicable chaos recovery through the real entrypoint. Test missing Research evidence, Scanner tool failure, incorrect plan, corrupted receipt, stale plan revision, host interruption and restart. Run E2E again after affected fixes. Do **not** substitute static fixtures, mocks, structural contract tests or generic callback traces as real E2E.  
**Proof:** Genuine execution logs include exact CLI/tool identity, working directory, source hash, exit code, observed outputs, receipts and task IDs. Injected defects are detected. Full `validate_records()` passes only after actual E2E receipts and all required criteria are met. If the live host isn't available, mark live harness E2E `not_verified` and do not promote overall completion.

### M8 — Reconcile, document and clean up

**Files:** `agent/contracts/README.md`, `README.md`, `AGENTS.md` as actually present, current test docs, superseded files identified by audit.  
**Steps:** Remove active references to rejected numbered 00–11 instructions only after verified replacements. Never wholesale delete or use `git add -A` on an unknown dirty tree; inspect the diff and stage only authorized changes. Record commands, results, source revision, artifact manifests, remaining limitations and restart instructions. Commit coherent verified changes when authorized.  
**Proof:** No duplicate active guidance owners, no unintended file deletions, correct CLI instructions, auditable source revisions and one inspectable current task outcome. Run targeted suites, then applicable broader checks configured by the actual repository.

## Required automated evaluation matrix

| Case | Independent expected behavior | Verification layer |
| --- | --- | --- |
| Valid minimal request | Research artifacts → verified Plan → actual build → actual E2E | connected-host E2E |
| Source claim without evidence | Handoff fails or finding explicitly unresolved | Research/contract + connected-host |
| User choice missing | Main Agent requests one specific choice, preserves task and resumes | connected-host interaction |
| Research revised after Plan | Plan and downstream readiness invalidated | contract + resume |
| Scanner unavailable/denied | Block with real reason; no fake successful scan | connected-host negative |
| Drift/overlap/duplication | Grounded finding, correction and Scanner recheck | Scanner + plan E2E |
| Contradictory requirements | Both sides preserved; blocking conflict resolved or surfaced | Research + gap E2E |
| Incorrect fixture oracle | Rejected before Build, with independent evidence | fixture-chaos preflight |
| Chaos interruption | Task resumes without repeated side effects; verifies recovery | post-build E2E |
| Corrupt/stale artifact | Digest/reference mismatch detected; invalidated | contract + post-build E2E |
| Wrong built result | Actual requested result fails; Gap Fix and re-test | post-build E2E |
| Repeated no-progress fix | Stop blocked with root cause and receipt; no infinite loop | connected-host negative |
| Fixed Plan after failure | Revalidated fixture/Scanner/affected E2E evidence tied to current revision | connected-host E2E |

## Progress (initial planning checkpoint)

- [x] 2026-10-29 — Verified the public GitHub commit and existing contract file paths.
- [x] 2026-10-29 — Read the three YAML contracts, verifier, regression tests and representative historical modules.
- [x] 2026-10-29 — Mapped accepted workflow and documented the full proposed build plan.
- [ ] M0 — Reinspect actual Databricks working tree and the real host/Scanner interfaces.
- [ ] M1 — Add stage-specific handoff validation.
- [ ] M2 — Implement one controller with durable continuation.
- [ ] M3 — Implement evidence-backed Research output.
- [ ] M4 — Implement Plan, Scanner and Gap Fix integration.
- [ ] M5 — Prevalidate independent fixtures and chaos definitions.
- [ ] M6 — Execute Build and implementation validation through real tools.
- [ ] M7 — Verify genuine post-Build E2E and recovery.
- [ ] M8 — Reconcile and clean up superseded material after verification.

## Surprises and discoveries

- Committed GitHub still uses historical `src/`; previously supplied Databricks audit described uncommitted `tools/`. They are not interchangeable physical sources.
- The committed checker only offers one combined `validate_records()` entrypoint. This is insufficient for independent Research and Plan transitions before downstream records exist. It also requires a completed-stage validation receipt as input to the same completed-stage check, so the implementation must specify safe receipt-creation order.
- Historical `src/plan_review.py` uses shallow presence checks, while desired Gap Analysis requires real Scanner evidence for drift, overlap and duplication.
- Historical negative fixture logic can treat arbitrary exceptions or mismatched results as successful negative tests. Replace that behavior before relying on it for acceptance.
- Verified GitHub does not establish availability of the Databricks host hooks, connected Scanner or actual Task Management artifact resolver.

## Decision log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-10-29 | Keep one `agent/main.py` controller instead of three independent `*.ts` runtimes | Existing repo is Python; user supplied TS function names as shorthand; one controller was previously accepted. |
| 2026-10-29 | Use Research candidate `plans.md` and one accepted Plan `ExecPlan.md` | Prevent candidate research suggestions from becoming executable authority. |
| 2026-10-29 | Extend existing contract checker rather than add a contract service | Corrects stage transition defect without introducing a second owner. |
| 2026-10-29 | Invoke existing System Scanner, not `repo_summary.py` as a substitute | Scanner is accepted owner for evidence-grounded discovery of drift, duplication, overlap and other issues. |
| 2026-10-29 | Keep Chaos inside pre-Build fixture preparation and post-Build E2E execution | Avoids an unnecessary stage, tests both oracle readiness and actual recovery. |
| 2026-10-29 | Treat missing live host capability as `not_verified`/blocked | A simulation cannot establish live integration. |

## Recovery and restarting from this document

1. Inspect the active repository, current branch and `git status --short`; compare with this plan's verified public commit. Identify whether the active physical root is Databricks `tools/` or GitHub `src/` before touching any file.
2. Read `agent/contracts/README.md`, the three YAML templates and checker; identify current host tool bindings and existing Task Management API. Compare current revisions/hashes and previously recorded task checkpoints. Do not blindly copy from historical archives.
3. Locate the first incomplete milestone in **Progress** and check its actual files/receipts. If a milestone has side effects with uncertain completion, reconcile actual output before rerunning. Update Progress, Surprises and Decision Log whenever changing the plan.
4. Follow the verified toolchain of the physical repo. The known existing contract test command is `python -m unittest discover -s tests -p 'test_workflow_contracts.py' -v`. New CLI commands and E2E tests in milestones are design targets until implemented and executed.
5. At each stopping point record exact paths, command outputs, coverage/limitations, commit or artifact hashes and next milestone. Never mark blocked/unexecuted checks passed or claim the completed harness is live without its actual E2E receipt.

## External technical background (research only, not product authority)

- OpenAI Agents SDK and manager-style orchestration: https://developers.openai.com/api/docs/guides/agents/sdk and https://openai.github.io/openai-agents-python/agents/
- OpenAI ExecPlan guidance: https://developers.openai.com/cookbook/articles/codex_exec_plans
- Durable execution and idempotency design: https://github.com/langchain-ai/docs/blob/main/src/oss/langgraph/functional-api.mdx
- MCP elicitation and host capability negotiation: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/client/elicitation.mdx

**Status:** Build plan authored. Neither the workflow harness implementation nor live E2E has been performed by this planning exercise. No changes to the GitHub repository were made.
