# BUILD INSTRUCTION — Implement the OneShot Research → Plan → Build Harness

**Status: READY FOR IMPLEMENTATION (instruction quality only; the harness is not built).** This revised instruction resolves the review gaps in durable handoffs, host invocation, fixture oracles, adversarial checks and restart behavior.

## Purpose and outcome

Implement the accepted OneShot workflow end to end, using the actual active repository and the committed Research, Plan, and Build YAML contracts. A user must be able to submit one objective, obtain a stable task ID, have an agent investigate and save evidence-backed artifacts, turn those artifacts into a reviewed executable plan, correct Scanner and other detected gaps, prevalidate fixtures and chaos cases, execute that exact plan, and independently verify the built result through real post-Build E2E. A stopped task must resume without losing evidence or repeating confirmed side effects.

**This is an implementation assignment, not another proposal or re-design. Proceed through the milestones without asking me to choose generic “next steps.”** Do not claim completion until the actual host and built product have been tested. Deliver the implemented code, updated contracts/docs, tests, receipts and an honest completion report in the same execution when the environment permits.

## Source authority and scope

- **Primary implementation plan:** `OneShot_Workflow_Harness_ExecPlan.md` when physically available; inspect and maintain its M0–M8 milestones. **This instruction also states the complete required milestones and is sufficient to start when the separate plan file is unavailable.** In that case, create one self-contained living ExecPlan from this instruction, recording verified repository facts, assumptions, decisions, source evidence, commands, progress and restart instructions. Do not pretend a missing plan file was read. Later explicit user requirements override conflicting older material within their scope.
- **Authoritative Git source:** `itz1508/OneShot`, branch `main`, with the committed Research, Plan and Build contracts. Inspect current commits and physical source before editing; do not assume it is still the active revision. Treat the physical working tree, including staged/unstaged/untracked files, as the implementation target once its identity is verified; never overwrite local work based on an older remote snapshot.
- **Active working-tree warning:** The Databricks workspace was reported to have `tools/` as its active Python source directory, while committed GitHub historically contained `src/`. **Start from the physical active workspace. Never rebuild against `src/` or reverse the `tools/` migration simply because GitHub shows old files.** Use historical source as read-only evidence of useful behavior; do not promote superseded 00–11 assignments into authority.
- **Committed contract files:** `agent/contracts/research.yaml`, `plan.yaml`, `build.yaml`, `check_contracts.py`, `README.md`, plus `tests/test_workflow_contracts.py`. Preserve these as the accepted record family and extend them only when justified.
- **Limits:** This task implements the workflow harness only, not the unrelated OneShot System Summarizer, UI, deployment, provider downloads, plugin viewer or release process. Preserve unrelated local changes. No invented Quality Input Python subsystem, new independent Scanner, new Task Management database, generic permission service, unverified hook API, or separate Research/Plan/Build controllers. In a small directly verifiable task, the harness may select a compact path rather than fabricate unnecessary Research/Plan stages; **this harness acceptance build must exercise the entire workflow**.

## One required execution path

```text
Task / accepted objective
  → Research (inspect, search, challenge assumptions)
  → Research artifact output (evidence, plans.md candidate, independent fixtures, success criteria)
  → Plan (self-contained ExecPlan tied to Research ID/revision)
  → System Scanner Gap Analysis (missing, drift, overlap, duplication, contradictions,
       dependencies, feasibility, coverage, mismatch/leakage where supported)
  → Universal Gap Fix (correct every confirmed actionable in-scope issue at its true owner)
  → Scanner / affected-artifact recheck
  → Fixture Validation + Chaos (pre-Build oracle/coverage/recovery-case preparation)
  → Build the exact verified Plan ID/revision through real host tools
  → Implementation validation
  → Real post-Build E2E (normal/negative/boundary and applicable chaos/recovery)
  → Verified result + persisted receipts
```

A later failure returns to the responsible Research, Plan, fixture or Build responsibility through the **same Gap Fix**; revalidate every affected downstream artifact. **Build success is not task success.** No handoff, Scanner result, tool execution or E2E result may be synthesized by setting YAML flags. Review gaps include missing requirements, unsupported claims, drift, overlap, duplication, contradictions, dependencies, feasibility, coverage, regressions and applicable mismatch/leakage; preserve source locations and both sides of conflicts. A clean Scanner result is not proof of semantic correctness.

## Architecture and exact proposed file actions

Use **one Python controller** because that is the previously accepted design for this Python repository; `research.ts`, `plan.ts`, `build.ts` were shorthand for responsibilities, not an instruction to introduce TypeScript. Markdown guidance and templates specify the work. An *existing and verified* host performs model/tool calls and supported question/continuation interactions. Do not equate a named Markdown step, Python function, or tool-registry entry with an installed hook or an executed operation. Confirm actual host APIs and record their identities before claiming connected execution.

| Path | Action / owner |
| --- | --- |
| `agent/main.py` | **CREATE** single thin controller for start/resume/status, stage selection, actual host invocations, checkpointed handoffs, and stop/blocked behavior. It must not replace the host's inference loop. |
| `agent/reference/research_guidance.md` | **CREATE** how to scope searches, inspect sources, question proposals, classify uncertainties, and produce Research artifacts. |
| `agent/reference/plan_guidance.md` | **CREATE** exact ExecPlan composition, Scanner invocation, universal Gap Fix, recheck, Fixture Validation + Chaos. |
| `agent/reference/build_guidance.md` | **CREATE** plan-pinned execution, real receipts, implementation checks, post-Build E2E and recovery. |
| `agent/templates/research_input.md`, `output_plan.md`, `output_fixture.md`, `output_success_criteria.md`, `output_validation.md`, `execplan.md` | **CREATE / ADAPT ONLY AFTER INVENTORY.** Reuse an existing accepted template catalog; do not introduce parallel versions or treat Markdown files as Python imports. |
| `agent/contracts/{research,plan,build}.yaml` | **KEEP and extend narrowly** only if an actual cross-stage contract gap requires a field or contract change. |
| `agent/contracts/check_contracts.py` | **EXTEND** with Research-only, Research+Plan, and final three-stage invariant checks. Retain existing `validate_records()` compatibility. |
| `agent/contracts/README.md` | **UPDATE** with validated stage-by-stage usage, receipt creation, revision and recovery rules. |
| Existing Task Management and artifact storage under the *verified active source root* | **REUSE**; inspect current implementation and correct atomicity, concurrency or retry issues only when reproduced and required. Do not add a competing store. |
| Existing System Scanner host bridge | **REUSE**; discover actual callable interface. Do not substitute the old `repo_summary.py` or locally simulate Scanner and call it real. |
| `tests/test_workflow_contracts.py` | **EXTEND** stage handoffs, malformed states, forged/stale receipts, revision races and compatibility. |
| `tests/test_agent_workflow.py` | **CREATE** controller state and failure/recovery tests, with explicit distinctions between fake-host unit tests and connected-host execution. |
| `tests/test_agent_e2e.py` | **CREATE** actual connected-host → built entrypoint E2E tests; must invoke real runtime and verify independent user outputs. |
| `AGENTS.md`, `README.md`, `TRACEABILITY.md` and superseded numbered `agent/` prompts | **RECONCILE after implementation** against actual behavior; retire stale active instructions only after replacements are verified. |

Logical persisted artifacts (map to the existing Task Management artifact store; **do not create a second filesystem store**):

```text
<task_id>/research/todo_search.md
<task_id>/research/evidence.md
<task_id>/research/plans.md
<task_id>/research/fixture_<case>.md
<task_id>/research/success_criteria_<case>.md
<task_id>/research/validation.md
<task_id>/plan/ExecPlan.md
<task_id>/build/<actual_execution_and_e2e_receipts>
```

## Stage operations and contract boundaries

Implement logical operations under the **single controller**. These names describe expected behavior; use actual verified host API bindings, and consolidate functions if that better matches the host. Do not create an artificial SDK around unknown calls.

- `start_task(request_ref) -> task_id`: bind original request, accepted requirements and active source identity; reuse existing task creation and persistence.
- `research_plan(task_id) -> research_record_id`: perform Research with actual search/repository tools; produce and persist evidence-located findings, contradictions, candidate plan, fixture/oracle examples and criteria. Validate the *instantiated Research record alone* before opening Plan.
- `review_research_plan(task_id, research_id) -> plan_record_id`: read the exact accepted Research revision/manifest, inspect files/config, produce a self-contained ExecPlan, execute a real Scanner call, fix gaps, recheck and prevalidate fixture/chaos expectations.
- `gap_analysis_and_fix(task_id, plan_id) -> verified_plan_revision`: normalize Scanner and stage findings, locate root cause, correct at the rightful owner, retain receipts, and re-run affected checks until resolved or genuinely blocked. Handle missing, drift, overlap, duplication, contradictions, coverage, dependencies, feasibility, regressions and applicable leakage/mismatch signals. Distinguish genuine shared functionality from harmful duplication.
- `fixture_validation_chaos(task_id, plan_id) -> validated_manifest`: prove independent fixture oracles, expected error/negative/boundary behavior and applicable fault/recovery cases **before** Build; do not claim those cases have been executed against the product yet.
- `build_plan(task_id, plan_id) -> build_record_id`: pin accepted Plan ID/revision/manifest, invoke real host tools, capture changed paths and command results, validate implementation milestones and checkpoint after side effects.
- `validate_build_and_e2e(task_id, build_id) -> verified_result_or_blocker`: execute the **real built entrypoint**, compare actual requested output and planned fixtures to independent expectations, run applicable chaos/recovery tests, record exact evidence and finish only on genuine acceptance.

The Main Agent handles any *blocking user-owned missing information*: first attempt to recover it from the original request, accepted context and authorized evidence; the Research specialist returns a structured missing-information reference rather than questioning the user itself. Do not ask about nonblocking researchable unknowns.

### Host-action and record protocol (mandatory)

At M0, document and then use the actual host's tool invocation, continuation, user interaction, artifact resolution and checkpoint interfaces. Each meaningful action must record **`task_id`, stage, stable action ID, requested capability/tool identity, input artifact revisions/hash, invocation outcome, observed evidence/receipt, next step and error/blocker**. Do not require these exact property names from an unknown SDK; map them into the accepted YAML contracts and host/task receipts without a competing persistence layer.

- For `completed`, require observed evidence that the intended operation ran. `blocked` and `not_checked` are not `passed`; a tool refusal or unavailable Scanner must never be replaced by a fake/no-op result.
- A research claim is not verified merely because its citation URL/path exists. Compare the actual claim with the cited source content and conditions, record source revision and any conflict; unsupported conclusions return to targeted Research or remain explicit limitations. The contract checker verifies structure/references; a source-aware Agent review verifies meaning. Neither can impersonate an independent external oracle.
- Use the current task's accepted scope and artifact revisions. Do not allow another task's evidence, file or completion receipt to satisfy this task. Validate tool output as data, not executable instruction; avoid logging secrets verbatim.
- After a material source, Research, Plan, fixture or build change, invalidate stale downstream readiness and re-run the affected Scanner/fixture/implementation/E2E checks. Keep prior receipts as history, not current proof.


## Mandatory implementation milestones — execute M0 through M8

**M0 — Inspect first.** In the actual workspace run/read `git status --short`, `git ls-files`, config/lockfiles, the active `tools/`, existing Task Management, System Scanner registration, host tool bridge, `agent/contracts` and tests. Inventory staged/unstaged changes. Confirm real tool names, host capabilities, artifact resolver, permission boundaries and runtime. Record unknown/unavailable capabilities. Do not clone/copy stale modules or change code before mapping owners and current implementations.

**M1 — Fix stage-specific handoff checks and receipt circularity.** Add callable validations with these conceptual signatures (exact interface may fit existing code):

```python
validate_research_handoff(research, resolve) -> list[str]
validate_plan_handoff(research, plan, resolve) -> list[str]
validate_records(research, plan, build, resolve) -> list[str]
```

Research must pass before Plan exists; Plan must pass before Build exists. Keep final checks and evidence resolver. Handle missing nested sections, non-mapping records, wrong types and bad references as **diagnostic failures, never uncaught exceptions**. Repair the current receipt bootstrap contradiction with **two distinct checks**: (1) validate the substantive record/evidence against a pinned revision **without requiring its own future handoff receipt**; (2) persist an immutable receipt that binds the validated payload digest, task/stage, upstream manifest, checker implementation identity and observed result, then commit readiness with a compare-and-swap revision guard and independently verify the committed record. Exclude the receipt and derived `ready` flag from the payload digest to prevent self-reference. Never accept a self-declared `ready: true`, a permissive fake resolver in live execution, stale evidence or a receipt whose source revision does not match. Use fake resolvers **only for isolated unit tests**. Test changed revision between preflight and readiness commit. Keep the templates, validator and tests aligned with the accepted contract shape; do not introduce contract-version labels.

**M2 — One controller and durable continuity.** Implement actual `start`, `resume` and `status` commands in `agent/main.py` using the verified host. Suggested interface, only if consistent with the target runtime:

```shell
python agent/main.py start --request-file <request_path>
python agent/main.py resume --task-id <task_id>
python agent/main.py status --task-id <task_id>
```

Persist action identity, source snapshot, stage state, record revision and side-effect receipts in existing Task Management. **Verify that its actual persistence supports atomic record writes, revision-guarded updates and safe single-owner claiming or equivalent serialization for each task.** If the current implementation merely overwrites a shared JSON file, repair the existing owner when necessary to meet this requirement; do not add a second store. Define the crash boundary: record action `pending` with stable identity before invoking a side-effecting tool; after invocation persist real receipt and mark `completed`. On an uncertain crash state, reconcile the external effect before retry and never blindly replay. Resume from the first unfinished stage; repeated/concurrent starts or resumes may not silently duplicate confirmed work. Test concurrent update/restart and unrelated-task isolation. A missing real host/Scanner blocks its dependent functionality; it does not trigger simulated completion.

**M3 — Real Research and artifact output.** Implement actual guidance-driven investigation and template population. Trace every in-scope requirement to inspected evidence, applicable fixtures and measurable acceptance criteria. Keep `plans.md` as *Research candidate*, not executable authority. **Check representative consequential claims against their cited source passages and preserve qualifiers, negation, uncertainty and version information.** Require meaningful claims and source identity, not heading existence or mere artifact presence. Store actual provenance and limitations. An evidence-free assertion or irrelevant citation must not receive `supported` just because the referenced file exists. Verify Research-only handoff with trusted evidence before Plan creation.

**M4 — Plan + real Scanner + universal Gap Fix.** Build precise ExecPlan from accepted Research artifacts, with exact paths, steps, commands, expected observations, rollback/resume and decision log. Call System Scanner through its **verified tool interface** with active repo + accepted requirements + Research artifacts + current Plan scope. Record actual input revisions, findings/evidence and receipts. Correct all confirmed actionable in-scope gaps at their responsible stage, including drift, overlap, duplication and contradictions. Rerun Scanner and impacted validations after changes; no changing a `status` flag to fabricate resolution. Block real critical unresolved findings. Unsupported Scanner capability is `not_checked`, never passed.

**M5 — Fixture Validation + Chaos BEFORE Build.** Validate fixture independence and provenance, positive/negative/boundary/error expectations, fault injection and recovery assertions. Detect wrong expectations, oracle copied from implementation, weak negative tests that accept **any** exception, missing recovery assertions and cases that could pass without invoking the target. **Define each fixture's expected output or precisely expected error class/shape, observable detection condition, evidence-backed oracle method, and actual post-Build entrypoint.** Disagreeing oracle evidence must be corrected before Build, not made to match implementation output. Record justified `not_applicable` only for genuinely irrelevant chaos conditions. Preserve these cases as the post-Build E2E specification.

**M6 — Build verified Plan.** Use only the exact current Plan ID/revision/manifest, execute its milestones via authorized host tools, record command/exit/output, artifacts, hashes, changes and implementation checks. After every meaningful side effect checkpoint; reconcile uncertain effects. If current source/Plan/fixture revisions drift, suspend execution and return to Gap Fix/Plan. Do not count a callable stub or mock trace as an actual build.

**M7 — REAL post-Build E2E.** For the acceptance demonstration build a small context-counting CLI *through the connected harness*, not by directly pre-generating the final source outside the flow. **Research must settle its independent behavioral specification before implementation**: report Unicode **code points** (not grapheme clusters), UTF-8 bytes, and words using a stated segmentation rule (for the baseline PoC, Unicode whitespace separation equivalent to Python `text.split()`). Test ASCII, empty input, embedded newlines, combining sequences and emoji. If any token figure is provided, label it **an estimate with an explicitly defined formula** unless a verified model-specific tokenizer/API was actually used; never imply estimated tokens equal true model context usage. Define invalid-input and boundary handling from accepted requirements rather than inferring it from the implementation. Fixtures establish independent examples **before** Build. E2E must call the built CLI through its genuine entrypoint and compare independent expected results, including the actual requested input, normal/negative/boundary cases, corrupted/stale receipts, invalid inputs and relevant interruption/restart/chaos scenarios. Inject known wrong results and prove the harness detects them. Rerun affected E2E after corrections. Capture actual tool and executable identity, cwd, environment, exit code, observations, artifact IDs and receipts. Do not label a fake-host/controller unit test as connected-host E2E.

**M8 — Reconcile/cleanup and report.** Install the already accepted `AGENTS.md` in the active repository if absent (after verifying its actual source); do not author a competing instruction set. Confirm no duplicate responsibility owners, stale active instructions, broken paths or unintended file deletions. Update docs to observed working commands and evidence. Replace or retire superseded 00–11 guidance only after confirming accepted replacements, and do not delete unrelated files or run `git add -A` on an unknown dirty tree. Inspect diff, selectively stage authorized files and make coherent commits where permitted. Do not release/deploy unless separately requested.

## Required adversarial and E2E matrix

Test the following independently, with correct classification of offline contract/unit tests vs *real* host E2E:

1. Valid objective → Research evidence/artifacts → verified Plan → Scanner/Gaps → prevalidated fixtures+chaos → real Build → actual post-Build E2E → verified result.
2. Research missing evidence / unsupported claim → targeted re-search or block; no premature Plan handoff.
3. Essential user-owned decision missing → one Main Agent question; checkpoint/resume; no fabricated value.
4. Modified Research manifest/revision after Plan → downstream readiness invalidated.
5. Scanner absent, denied or failed → real blocker and receipt, not a fake clean scan.
6. Real drift, overlapping owner, duplicate file/tool/instructions and contradictory requirement → evidence-grounded finding, root-cause correction and recheck.
7. Incorrect fixture oracle or chaos recovery expectation → reject before Build.
8. Build command failure or wrong output → not complete; trace root cause, Gap Fix, revalidate.
9. Tampered artifact, stale evidence or incorrect receipt hash → invalidated, not reused as verified.
10. Interrupted action at a side-effect boundary → replay/reconciliation does not duplicate work.
11. Actual requested result differs from independent expected result, even while static fixtures pass → E2E fails.
12. Repeated no-progress correction → bounded blocked state with cause; never an infinite loop.
13. After successful correction, all affected Scanner, Plan, fixture and E2E receipts are bound to current revisions.

For chaos, inject controlled failures only in disposable test scope, never against unrelated user data or a production environment.

## Commands, evidence and completion

Derive the actual Python runner, dependencies and test commands from real configuration. Do **not** introduce npm/pnpm, Python 3.12, PyYAML, a new lockfile, an external model or a Databricks installation solely because examples mention them. The prior contract revision reported 22 focused tests; rerun to establish the actual baseline before edits and preserve all legitimate coverage. Existing contract-suite candidate:

```shell
python -m unittest discover -s tests -p 'test_workflow_contracts.py' -v
```

After implementation, run applicable focused workflow and E2E tests through the configured runtime, then broader checks if supported. Preserve baseline failures separately from introduced regressions. A passing contract YAML parse, mock host or fixture-only test is **not** post-Build E2E. In the test report distinguish **structural contract validation**, **deterministic controller tests**, **live host/Scanner integration**, **built CLI E2E** and **full connected-harness E2E**; success at one layer never proves the next. Capture at least one failing end-to-end case and successful corrective re-run, not just a clean happy path.

Maintain the living ExecPlan throughout execution: **Purpose, Context/Assumptions, Progress, Surprises & Discoveries, Decision Log, Outcomes & Retrospective, exact executed commands, source/revision identity and next milestone**. Record observable evidence at every stopping point. The next executing agent must be able to restart from that file without prior chat messages or uncommitted assistant state. No generic “shall we continue?” requests; proceed unless a genuinely blocking authorization/user choice is needed. If unavailable host capabilities prevent live E2E, implement and verify independent portions, mark live integration `BLOCKED/NOT_VERIFIED` and report exactly what remains. Do not claim the workflow is complete.

**Final deliverable:** The changed file/path list, current task IDs and artifact references, successful/failed/not-run checks with exact commands and receipts, demonstrated context-counter build and post-Build E2E evidence if available, gap/chaos/recovery results, validated final contracts, a coherent commit when authorized, and a concise outstanding-blocker list. **Do not substitute another plan for this implementation.**
