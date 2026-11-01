# OneShot Research, Plan and Build records

**Purpose.** One task must remain understandable and resumable without chat history. The three YAML templates record accepted requirements, investigation, decisions, corrections and verified outcomes. They do **not** provide an agent runtime, a Scanner, a hook system, or a new database.

## Files and ownership

- `agent/contracts/research.yaml`: Research input, inspected evidence, requirement trace, candidate plan, independent fixture references and Review.
- `agent/contracts/plan.yaml`: executable Plan reference, Scanner Gap Analysis (missing, drift, overlap, duplication, contradiction, dependency, feasibility, coverage), Gap Fix and **Fixture Validation + Chaos**.
- `agent/contracts/build.yaml`: execution receipts, implementation checks, actual **post-Build E2E**, recovery and final result.

The legacy `src/` source and the retired 00–11 numbered-prompt set are preserved under [`archive/legacy-src-pre-harness-2026-10-29`](https://github.com/itz1508/OneShot/tree/archive/legacy-src-pre-harness-2026-10-29), not active on `main`. This checkout contains the live OneShotController harness, its Pydantic validators, and the three contract YAMLs. Do not restore archived modules or invent System Scanner bindings.

## Lifecycle and persistence

1. Research stage entry: instantiate only the Research record in the **existing Task Management store**. Use a stable `task_id`, a new `record_id`, and immutable artifact references. Populate it from the original request, authorized context and actually inspected sources. A template is not a completed record.
2. Research handoff: inspect independent source evidence, address blocking issues, record Research artifacts, and validate. Only after successful checks may the host transition to Plan and create its record, recording the exact Research `revision` and artifact manifest ref.
3. Plan: produce the self-contained ExecPlan; call existing System Scanner with a scope covering the active repository, accepted requirements and the Plan; resolve actionable gaps (including drift, overlapping responsibilities and duplication). After each material Plan change increment its revision, rerun Scanner and record the recheck. Independently prevalidate fixture expectations and applicable chaos cases **before Build**.
4. Build: create its record on stage entry, recording the exact Plan revision and manifest. Perform actual work via the existing host and tools, record changes and command receipts, run implementation checks, then run **real post-Build E2E through the built entry point** including applicable chaos cases. Verify the actual requested result, not merely fixture examples.
5. Failures from any stage: classify origin, return to the responsible stage through the **existing Gap Fix responsibility**, correct, preserve old decisions and receipts, and revalidate all impacted downstream artifacts. Do not silently mark a failed or unexecuted check passed.
6. Completion: only after verified actual output and E2E acceptance may Build become `complete` with `outcome.status: verified` and `handoff.ready: true`. No unsupported partial completion flag is success.

**State semantics:** `draft` = template/record not executed; `in_progress` = work underway; `blocked` = cannot proceed pending an external dependency/user-owned decision; `failed` = performed and failed, correctable; `complete` = stage's handoff conditions verified. `handoff.ready` is a **derived assertion**, not independent authority. Set it only after checks pass, and persist the checker/host validation receipt. A `passed` field alone is never an execution receipt.

**Scope of fixes:** Fix every actionable, confirmed **in-scope** issue, regardless of its origin. `false_positive` requires supporting evidence, `deferred` requires explicit approval and can **never** cover a confirmed critical finding. An out-of-scope issue remains visible; it is not falsely described as corrected. When Scanner or E2E cannot run, the stage is `blocked`/`not_checked`, never `complete`. No mandatory chaos cases for truly inapplicable tasks, but the exclusion must be explained and recorded.

## Evidence and revision safety

- Persist with the existing store's atomic/compare-and-swap revision semantics. Update `revision` and UTC `updated_at` with every material mutation; **append** progress and decision entries instead of rewriting history. Store substantive logs and fixtures as referenced artifacts, not repeated YAML text.
- Maintain stable identifiers. Reference actual source revisions or SHA-256 artifacts. References must resolve to real content-addressed evidence. An **evidence index** or host artifact resolver verifies these before claiming readiness; merely setting `receipt_ref` is insufficient.
- When Research revision/manifest changes, invalidate Plan and Build handoff readiness until revalidated. When Plan or fixture manifest changes, invalidate Build readiness and rerun affected checks and E2E. A current Scanner check must cover the **current Plan revision**.
- Before retrying an action, inspect `checkpoint.action_id`, `action_state`, `action_receipt_ref`, `retry_disposition` and `source_snapshot_ref`. An uncertain action must be reconciled with actual side effects before retrying; don't automatically rerun writes or submissions. Completed steps require receipts; progress must be independently observable. The state machine and retries remain owned by existing Task Management / host.
- If a record changes during validation or commit, repeat against the new revision; do not write readiness decisions to a stale revision. The verifier is read-only; the host must perform a revision-guarded update.
- Do not infer live tool/provider executions from YAML/Markdown fields. A host must verify tool identity, executed command, real entrypoint, receipt integrity and observed result. Pure contract validation does **not** establish semantic Research quality, actual Scanner invocation, actual E2E, or production readiness.

## Run validation

Validation uses Pydantic models and the workflow controller. Readiness validation **fails closed** without actual evidence resolution:

```shell
python -m pytest tests/test_workflow_contracts.py -v
```

These are **contract tests**, not proof of the actual connected host harness. For true E2E, run the configured host against the real built system and independently check requested outputs and chaos/recovery results.

