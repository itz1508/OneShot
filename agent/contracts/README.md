# OneShot Research, Plan and Build records — contract v1.1

**Purpose.** One task must remain understandable and resumable without chat history. The three YAML templates record accepted requirements, investigation, decisions, corrections and verified outcomes. They do **not** provide an agent runtime, a Scanner, a hook system, or a new database. `check_contracts.py` is a read-only contract invariant checker, not an execution controller.

## Files and ownership

- `agent/contracts/research.yaml`: Research input, inspected evidence, requirement trace, candidate plan, independent fixture references and Review.
- `agent/contracts/plan.yaml`: executable Plan reference, Scanner Gap Analysis (missing, drift, overlap, duplication, contradiction, dependency, feasibility, coverage), Gap Fix and **Fixture Validation + Chaos**.
- `agent/contracts/build.yaml`: execution receipts, implementation checks, actual **post-Build E2E**, recovery and final result.
- `agent/contracts/check_contracts.py`: independently check record readiness and cross-record references; call from the **existing** host controller at handoff. Does not invoke tools, write state, or judge prose quality.

The current public GitHub `main` was verified as `itz1508/OneShot` at `b1224bb` before installing these files; it has historical `src/` and does **not** have a checked-in `agent/main.py`. The active Databricks workspace reportedly has `tools/`; verify it before integration. These contracts must not cause an automatic migration, restore old 00–11 architecture, or introduce another Task Management owner.

## Lifecycle and persistence

1. Research stage entry: instantiate only the Research record in the **existing Task Management store**. Use a stable `task_id`, a new `record_id`, and versioned artifact references. Populate it from the original request, authorized context and actually inspected sources. A template is not a completed record.
2. Research handoff: inspect independent source evidence, address blocking issues, record Research artifacts, and validate. Only after successful checks may the host transition to Plan and create its record, recording the exact Research `revision` and artifact manifest ref.
3. Plan: produce the self-contained ExecPlan; call existing System Scanner with a scope covering the active repository, accepted requirements and the Plan; resolve actionable gaps (including drift, overlapping responsibilities and duplication). After each material Plan change increment its revision, rerun Scanner and record the recheck. Independently prevalidate fixture expectations and applicable chaos cases **before Build**.
4. Build: create its record on stage entry, recording the exact Plan revision and manifest. Perform actual work via the existing host and tools, record changes and command receipts, run implementation checks, then run **real post-Build E2E through the built entry point** including applicable chaos cases. Verify the actual requested result, not merely fixture examples.
5. Failures from any stage: classify origin, return to the responsible stage through the **existing Gap Fix responsibility**, correct, preserve old decisions and receipts, and revalidate all impacted downstream artifacts. Do not silently mark a failed or unexecuted check passed.
6. Completion: only after verified actual output and E2E acceptance may Build become `complete` with `outcome.status: verified` and `handoff.ready: true`. No unsupported partial completion flag is success.

**State semantics:** `draft` = template/record not executed; `in_progress` = work underway; `blocked` = cannot proceed pending an external dependency/user-owned decision; `failed` = performed and failed, correctable; `complete` = stage's handoff conditions verified. `handoff.ready` is a **derived assertion**, not independent authority. Set it only after checks pass, and persist the checker/host validation receipt. A `passed` field alone is never an execution receipt.

**Scope of fixes:** Fix every actionable, confirmed **in-scope** issue, regardless of its origin. `false_positive` requires supporting evidence, `deferred` requires explicit approval and can **never** cover a confirmed critical finding. An out-of-scope issue remains visible; it is not falsely described as corrected. When Scanner or E2E cannot run, the stage is `blocked`/`not_checked`, never `complete`. No mandatory chaos cases for truly inapplicable tasks, but the exclusion must be explained and recorded.

## Evidence and version safety

- Persist with the existing store's atomic/compare-and-swap revision semantics. Update `revision` and UTC `updated_at` with every material mutation; **append** progress and decision entries instead of rewriting history. Store substantive logs and fixtures as referenced artifacts, not repeated YAML text.
- Maintain stable identifiers. Reference actual source revisions or SHA-256 artifacts. References must resolve to real versioned content. An **evidence index** or host artifact resolver verifies these before claiming readiness; merely setting `receipt_ref` is insufficient.
- When Research revision/manifest changes, invalidate Plan and Build handoff readiness until revalidated. When Plan or fixture manifest changes, invalidate Build readiness and rerun affected checks and E2E. A current Scanner check must cover the **current Plan revision**.
- Before retrying an action, inspect `checkpoint.action_id`, `action_state`, `action_receipt_ref`, `retry_disposition` and `source_snapshot_ref`. An uncertain action must be reconciled with actual side effects before retrying; don't automatically rerun writes or submissions. Completed steps require receipts; progress must be independently observable. The state machine and retries remain owned by existing Task Management / host.
- If a record changes during validation or commit, repeat against the new revision; do not write readiness decisions to a stale revision. The verifier is read-only; the host must perform a revision-guarded update.
- Do not infer live tool/provider executions from YAML/Markdown fields. A host must verify tool identity, executed command, real entrypoint, receipt integrity and observed result. Pure contract validation does **not** establish semantic Research quality, actual Scanner invocation, actual E2E, or production readiness.

## Run the independent checker

The verifier accepts three **instantiated** `.json` records with Python standard library only; `.yaml` requires an already-installed `PyYAML` (no implicit package installation). Readiness validation **fails closed** without actual evidence resolution:

```shell
python agent/contracts/check_contracts.py <research.json> <plan.json> <build.json> \
  --evidence-index <verified_evidence_index.json> --evidence-root <task_artifact_root>
```

`verified_evidence_index.json` maps each reference to `{ "path": "relative/path", "sha256": "<64-lowercase-hex>" }`. The checker refuses missing, changed, symlinked or outside-root files. For native Task Management artifact IDs, provide the actual store-backed resolver when calling `validate_records(research, plan, build, resolve=...)`; do not fabricate a filesystem index. The host owns access control and obtaining trusted receipts.

Check that the **templates** parse as YAML (draft records must not be mistaken for completed work), if PyYAML is installed:

```shell
python -c "import pathlib,yaml; [yaml.safe_load(p.read_text(encoding='utf-8')) for p in pathlib.Path('agent/contracts').glob('*.yaml')]; print('YAML templates parsed')"
```

For contract logic tests (standard-library `unittest`, no pytest required):

```shell
python -m unittest discover -s tests -p 'test_workflow_contracts.py' -v
```

These are **contract tests**, not proof of the actual connected host harness. For true E2E, run the configured host against the real built system and independently check requested outputs and chaos/recovery results.

## Record changes made for v1.1

- Instantiation changed from **all stages at task start** to **on stage entry**; downstream records preserve the accepted upstream revision and manifest.
- Standardized lifecycle statuses and UTC timestamps. Defined real `complete` and `ready` semantics, not merely YAML validity.
- Required Scanner scope/call receipts with current Plan revision, finding dispositions, root-cause fixes, and independent rechecks.
- Required fixture/oracle and chaos applicability evidence before Build; actual E2E and independent user-result checks after Build.
- Added source snapshots, stable action IDs, retry/reconciliation status, downstream invalidation rules, evidence hashes, and a small read-only verifier with negative regression tests.