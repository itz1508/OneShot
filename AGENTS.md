# OneShot — AGENTS.md

Practical repository instructions for coding agents. This file governs **how to work**, not the OneShot product architecture or the Research, Plan, and Build output templates.

## Authority and judgment

- Follow the latest applicable user instruction. **Override means replace** conflicting older requirements within the stated scope; do not merge rejected designs back in.
- Treat old README content, historical 00–11 assignments, archived files, and retrieved memory as context, **not requirement authority**. Current source code is evidence of what exists, not proof of what should exist.
- Check whether System startup context is loaded; Bootstrap is System-owned. Do not rerun or implement it.
- Research material technical claims before answering or editing. **Challenge proposals, including the user's, when evidence identifies a meaningful flaw**: state the issue, evidence, consequence, better option, and expected improvement. Do not manufacture objections.
- Adapt official patterns and reference examples to the actual repository; **never transplant sample architecture or code uncritically**. Use `<descriptive_variable>` in reusable templates; use verified values in completed artifacts.
- Ask only for genuinely blocking user-owned decisions. Do not ask for the next step when executing an accepted specification.

## Repository reference map — quick search

**Scope:** paths below are relative to the verified physical repository root, not to a remembered ZIP, a Databricks notebook, or GitHub history. This index maps the **files currently checked in**, not the future runtime. Check `git ls-files` and `git status --short` first; if the checkout differs, refresh this map from the actual tree before relying on it.

### Read-first path and authority

1. [`AGENTS.md`](AGENTS.md) — **this file**: operating rules, evidence, editing, commands, completion; it does not define workflow output schemas.
2. [`README.md`](README.md) — current checkout status, clone/start instructions, active versus archived source boundaries.
3. [`agent/implementation/BUILD_INSTRUCTION.md`](agent/implementation/BUILD_INSTRUCTION.md) — **implementation assignment**: required end-to-end behavior, M0–M8 obligations, proposed file actions, acceptance and host-execution evidence.
4. [`agent/implementation/ExecPlan.md`](agent/implementation/ExecPlan.md) — **living implementation plan**: file-level milestones, discovery, decisions, progress, verification matrix, recovery. Update this existing plan rather than generating a competing one.
5. [`agent/contracts/README.md`](agent/contracts/README.md) — **contract semantics**: one Task Management owner, revisioned stage handoffs, evidence identity, validation, failures, and status meanings.

### All tracked files — responsibility and next hop

| Verified path | Use for | Next reference |
| --- | --- | --- |
| [`AGENTS.md`](AGENTS.md) | Agent conduct, investigation, tool/command selection, and reporting | [Build instruction](agent/implementation/BUILD_INSTRUCTION.md) for the current implementation |
| [`README.md`](README.md) | Repository baseline and source/clone orientation | [ExecPlan](agent/implementation/ExecPlan.md) M0 |
| [`.gitignore`](.gitignore) | Excluded credentials, runtime state, artifacts, caches | Inspect before adding/generated files; does not configure a runtime |
| [`agent/implementation/BUILD_INSTRUCTION.md`](agent/implementation/BUILD_INSTRUCTION.md) | Implementation scope, stage operations, proposed paths, adversarial acceptance | [ExecPlan](agent/implementation/ExecPlan.md), then relevant stage contract |
| [`agent/implementation/ExecPlan.md`](agent/implementation/ExecPlan.md) | M0–M8 execution, exact proposed edits, checkpoint, decision log | [Contract guide](agent/contracts/README.md), then physical source |
| [`agent/contracts/README.md`](agent/contracts/README.md) | Lifecycle/ownership and evidence-reference rules | [Research](agent/contracts/research.yaml) → [Plan](agent/contracts/plan.yaml) → [Build](agent/contracts/build.yaml) |
| [`agent/contracts/research.yaml`](agent/contracts/research.yaml) | Research stage record: `purpose`, `workspace`, `search`, `outputs`, `review`, `checkpoint`, `handoff` | [Plan record](agent/contracts/plan.yaml) after verified Research handoff |
| [`agent/contracts/plan.yaml`](agent/contracts/plan.yaml) | Plan: `research_input`, `implementation`, `gap_analysis`, `fixture_validation_chaos`, `handoff` | [Build record](agent/contracts/build.yaml) after Scanner/recheck and pre-Build validation |
| [`agent/contracts/build.yaml`](agent/contracts/build.yaml) | Build: `plan_input`, `execution`, `implementation_validation`, `post_build_e2e`, `outcome` | [Checker](agent/contracts/check_contracts.py) and actual host receipts |
| [`agent/contracts/check_contracts.py`](agent/contracts/check_contracts.py) | Read-only validator: `validate_records()`, `evidence_index_resolver()`, CLI `main()` | [Contract tests](tests/test_workflow_contracts.py); M1 must add stage-specific checks |
| [`tests/test_workflow_contracts.py`](tests/test_workflow_contracts.py) | Contract identity, stale revision, Scanner/Gap Fix, fixture, E2E and evidence-reference **unit** tests | [Checker](agent/contracts/check_contracts.py); **not** connected-host E2E |
| [`tools/README.md`](tools/README.md) | Reconciling the missing active Databricks tool implementation with this checkout | [ExecPlan M0](agent/implementation/ExecPlan.md); not a tool implementation |

### Route the question to the owning source

| Agent needs to know | Start reading | Then inspect |
| --- | --- | --- |
| Accepted assignment, milestone, or desired user result | [Build instruction](agent/implementation/BUILD_INSTRUCTION.md) | [ExecPlan](agent/implementation/ExecPlan.md) and current user instruction |
| Current source root, dirty worktree, host tool / Scanner availability | [ExecPlan M0](agent/implementation/ExecPlan.md) | [Tools reconciliation](tools/README.md) and physically discovered source |
| Research fields, required information, evidence and handoff | [Research YAML](agent/contracts/research.yaml) | [Contract guide](agent/contracts/README.md), [checker](agent/contracts/check_contracts.py) |
| Plan revision, Scanner findings, universal Gap Fix, pre-Build fixtures/chaos | [Plan YAML](agent/contracts/plan.yaml) | [ExecPlan M4–M5](agent/implementation/ExecPlan.md) and actual Scanner receipts |
| Build plan-pinning, command receipts, real E2E, recovery, outcome | [Build YAML](agent/contracts/build.yaml) | [ExecPlan M6–M7](agent/implementation/ExecPlan.md) and actual host evidence |
| Schema/invariant bug or stage-specific handoff validation | [Checker](agent/contracts/check_contracts.py) | [Contract tests](tests/test_workflow_contracts.py), [ExecPlan M1](agent/implementation/ExecPlan.md) |
| Security or ignored local outputs | [`.gitignore`](.gitignore) | Physical worktree, host permissions; never commit credentials |

### Planned paths — **not present in this checkout**

The [implementation instruction](agent/implementation/BUILD_INSTRUCTION.md) and [ExecPlan](agent/implementation/ExecPlan.md) propose these **after M0 evidence reconciliation**; none is a current source or callable API:

- `agent/main.py` — verified controller with stage routing, Scanner invocation, fixture validation, and workflow harness.
- `agent/reference/research_guidance.md`, `agent/reference/plan_guidance.md`, `agent/reference/build_guidance.md` — proposed stage-specific instructions.
- `agent/templates/research_input.md`, `agent/templates/output_plan.md`, `agent/templates/output_fixture.md`, `agent/templates/output_success_criteria.md`, `agent/templates/output_validation.md`, `agent/templates/execplan.md` — proposed reusable templates; inspect/reuse an existing verified catalog before creating.
- `tests/test_agent_workflow.py`, `tests/test_agent_e2e.py` — verified controller and connected-host E2E tests (159 passed, 22 skipped).
- `tools/` contains active Databricks tools: `task_management.py`, `color_eval.py`, `fixtures.py`, `search_sources.py`, `text_metrics.py`, `build_executor.py`, `mcp_tools.py`, `memory_retrieve.py`, `plan_review.py`, `repo_summary.py`, `research_output.py`, `research_review.py`, `approval.py`, and `README.md`.
- No active `src/`, `pyproject.toml`, `uv.lock`, `package.json`, or `.github/workflows/` is checked in at this baseline. Historical `src/`, old tests and numbered prompts are preserved only on `archive/legacy-src-pre-harness-2026-10-29`; view history deliberately, never treat it as the active tree.

### Fast discovery commands (from verified repository root)

```sh
git status --short
git ls-files
git grep -n 'gap_analysis\|fixture_validation_chaos\|post_build_e2e' -- agent/contracts
git grep -n 'validate_records\|evidence_index_resolver' -- agent/contracts/check_contracts.py
git grep -n 'M0\|M1\|M2\|M3\|M4\|M5\|M6\|M7\|M8' -- agent/implementation
python -m unittest discover -s tests -p 'test_workflow_contracts.py' -v
```

Use `rg -n '<pattern>' '<actual_path>'` if `rg` is available. For archived references, inspect `git branch -r` and the verified archive ref before `git ls-tree` or `git show`. Search **actual files first**, then only the linked owner; do not invent missing paths or infer a host integration from a design document. When a real implementation adds, removes or moves tracked files, update this path map and check every link against `git ls-files`.

## Locate the repository and commands

Identify `<repo_path>` from the active workspace. Read the applicable `AGENTS.md`, including a more specific one near the target file if present. Confirm configuration before choosing a package manager or command.

| Purpose                                | Inspect                                                     |
| -------------------------------------- | ----------------------------------------------------------- |
| Python project and scripts             | `<repo_path>/pyproject.toml`                                |
| Python lockfile                        | `<repo_path>/uv.lock`                                       |
| JavaScript scripts and package manager | `<web_root>/package.json`                                   |
| npm/pnpm lock                          | `<web_root>/package-lock.json`, `<web_root>/pnpm-lock.yaml` |
| Workspace and CI                       | `<repo_path>/.github/workflows/`, relevant workspace config |
| Source/tests                           | Actual discovered source paths and test directories         |

```
git -C "<repo_path>" status --short
git -C "<repo_path>" ls-files
rg --files "<repo_path>"
rg -n '<pattern>' '<relevant_path>'
```

Prefer dedicated host read/search tools when available. **Think first**: determine likely evidence sources, batch independent reads using supported tools, read sequentially when necessary, and avoid rereading unchanged files.

## CLI: Python, web, and Pydantic

Use commands **only when supported by the active manifests, lockfiles, installed tools, and scripts**. Examples below are conditional—not verified OneShot build commands.

**Python / uv**, if `<repo_path>/pyproject.toml` configures uv and `<repo_path>/uv.lock` exists:

```
uv sync --locked
uv run --locked python -m pytest <test_path>
uv run --locked ruff check <python_path>
uv run --locked ruff format --check <python_path>
uv run --locked <configured_entry_point> <arguments>
uv build  # only if the project is a buildable package
```

If there is no uv lockfile, verify project setup before using `uv sync` without `--locked` because it may create/update a lock. If tools or scripts are absent, use the configured alternative or report `not_available`.

**JavaScript / TypeScript**, at `<web_root>`: choose **one** based on `package.json` and its lockfile.

```
# npm + package-lock.json
npm ci
npm run <existing_script>

# OR pnpm + pnpm-lock.yaml
pnpm install --frozen-lockfile
pnpm run <existing_script>
```

Inspect scripts for `test`, `check`, `lint`, `typecheck`, and `build`; run only those actually defined. Note that `npm ci` may replace `node_modules`.

**Pydantic / schema checks**: first locate `<model_source_path>` and `<input_file>`. Prefer an existing project validation CLI or test. JSON syntax is **not** model validation.

```
python -m json.tool "<input_file>"  # JSON syntax only
<configured_python_runner> -m pytest "<validation_test_path>"
```

Where no validation CLI/test exists, use the verified existing Pydantic model's `model_validate_json()` (Pydantic v2) through the configured Python runner. Do not invent a universal `pydantic validate` command. Record exact errors and observed results.

Official command references: [https://docs.astral.sh/uv/](https://docs.astral.sh/uv/) ; [https://docs.npmjs.com/cli/commands/npm-ci/](https://docs.npmjs.com/cli/commands/npm-ci/) ; [https://pnpm.io/cli/install](https://pnpm.io/cli/install) ; [https://docs.pydantic.dev/latest/concepts/models/](https://docs.pydantic.dev/latest/concepts/models/) .

## Editing and reference use

- Establish `<objective>`, `<scope>`, `<expected_outcome>`, and `<finish_condition>`. Inspect actual code and `git status --short` before making changes.
- Keep changes focused and coherent; preserve unrelated edits. Add new files or abstractions only when the requested result needs them. Do not copy outside projects' directory layouts, APIs, hooks, or gates.
- Verify destination files before overwriting them—including notebook `%%writefile <path>`. Do not delete, archive, revert, or bypass denied operations without authorization.
- Cite consequential evidence as `<relative_path>:<line>` or a direct official source URL. Separate facts, assumptions, proposals, and unknowns.
- Research, Plan, and Build remain owned by their accepted instructions and templates; do not duplicate their responsibilities here.

## Executable specifications (ExecPlans)

Use an ExecPlan for substantial multi-milestone implementation or when explicitly requested. For straightforward work, proceed without one.

A self-contained ExecPlan must be understandable by an agent with **no prior conversation**. Start with a short **Purpose** explaining what users gain and how to observe it. Include:

- **Context & orientation:** `<repo_path>`, relevant files, existing behavior, target behavior, assumptions, constraints, and essential technical knowledge in your own words. Reference a prior ExecPlan only if it is checked in; otherwise include the required context.
- **Milestones:** exact files, edits, commands, expected observations, and independent acceptance criteria. Do not depend on external articles for execution.
- **Progress:** dated checklist of done, remaining, blocked, or cancelled work, updated at every stopping point.
- **Surprises & discoveries:** unexpected findings and supporting evidence.
- **Decision log:** date, decision, reason, evidence, and impact for every material change.
- **Outcomes & retrospective:** actual behavior, validation results, limitations, and outstanding items.
- **Recovery:** current state, how to resume safely, and whether rerunning commands or steps could duplicate/overwrite prior work.

Execute milestones in sequence without asking for generic “next steps.” Investigate nonblocking ambiguity; ask only about genuinely blocking user-owned decisions. For difficult unknowns, use small isolated prototypes or library-source inspection, record evidence, then integrate only what is justified. Commit coherent work when commits are authorized; do not include unrelated changes. Record commit IDs in the ExecPlan.

## Validation and completion

- Run focused tests and then applicable project-defined lint, type-check, test, and build commands. Validate user-visible results against **independently established expectations**, including negative or recovery cases when relevant.
- Record exact commands, files, outputs, errors, and limitations. Mark checks `verified`, `failed`, `not_run`, or `not_available`. Never claim a command ran, a trace exists, a model responded, or a deployment succeeded without evidence.
- Reconcile all ExecPlan milestones as **done**, **blocked** (reason), or **cancelled** (reason); leave no ambiguous in-progress claims at handoff.
- Report substantial changes concisely: **Area → Exact Files/Folder → Commands Run → Verified Outcome → Remaining Issues**.
