# OneShot — AGENTS.md

Practical repository instructions for coding agents. This file governs **how to work**, not the OneShot product architecture or the Research, Plan, and Build output templates.

## Authority and judgment

- Follow the latest applicable user instruction. **Override means replace** conflicting older requirements within the stated scope; do not merge rejected designs back in.
- Treat old README content, historical 00–11 assignments, archived files, and retrieved memory as context, **not requirement authority**. Current source code is evidence of what exists, not proof of what should exist.
- Check whether System startup context is loaded; Bootstrap is System-owned. Do not rerun or implement it.
- Research material technical claims before answering or editing. **Challenge proposals, including the user's, when evidence identifies a meaningful flaw**: state the issue, evidence, consequence, better option, and expected improvement. Do not manufacture objections.
- Adapt official patterns and reference examples to the actual repository; **never transplant sample architecture or code uncritically**. Use `<descriptive_variable>` in reusable templates; use verified values in completed artifacts.
- Ask only for genuinely blocking user-owned decisions. Do not ask for the next step when executing an accepted specification.

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
