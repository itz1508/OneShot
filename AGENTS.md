# OneShot — AGENTS.md

Practical repository instructions for coding agents. This file governs **how to work**, not the OneShot product architecture or the Research, Plan, and Build output templates.

## Authority and judgment

- Follow the latest applicable user instruction. **Override means replace** conflicting older requirements within the stated scope; do not merge rejected designs back in.
- Treat old README content, the retired 00–11 numbered-prompt set, archived files, and retrieved memory as context, **not requirement authority**. Current source code is evidence of what exists, not proof of what should exist.
- Check whether System startup context is loaded; Bootstrap is System-owned. Do not rerun or implement it.
- Research material technical claims before answering or editing. **Challenge proposals, including the user's, when evidence identifies a meaningful flaw**: state the issue, evidence, consequence, better option, and expected improvement. Do not manufacture objections.
- Adapt official patterns and reference examples to the actual repository; **never transplant sample architecture or code uncritically**. Use `<descriptive_variable>` in reusable templates; use verified values in completed artifacts.
- Ask only for genuinely blocking user-owned decisions. Do not ask for the next step when executing an accepted specification.

## Repository reference map — quick search

**Scope:** paths below are relative to the verified physical repository root, not to a remembered ZIP or GitHub history. This index maps the **files currently checked in**, not the future runtime. Check `git ls-files` and `git status --short` first; if the checkout differs, refresh this map from the actual tree before relying on it.

### Read-first path and authority

1. [`AGENTS.md`](AGENTS.md) — **this file**: operating rules, evidence, editing, commands, completion; it does not define workflow output schemas.
2. [`README.md`](README.md) — current checkout status, clone/start instructions, milestone verification.
3. [`pyproject.toml`](pyproject.toml) — project metadata, dependencies, pytest/ruff/mypy configuration.
4. [`agent/contracts/README.md`](agent/contracts/README.md) — **contract semantics**: one Task Management owner, revisioned stage handoffs, evidence identity, validation, failures, and status meanings.
5. [`tools/README.md`](tools/README.md) — tool inventory and design principles.

### All tracked files — responsibility and next hop

| Verified path | Use for | Next reference |
| --- | --- | --- |
| [`AGENTS.md`](AGENTS.md) | Agent conduct, investigation, tool/command selection, and reporting | [README.md](README.md) for status, [contracts README](agent/contracts/README.md) for validation |
| [`README.md`](README.md) | Repository baseline, milestone status, key files | [pyproject.toml](pyproject.toml) for deps and config |
| [`pyproject.toml`](pyproject.toml) | Project metadata, dependencies, pytest/ruff/mypy config | [conftest.py](conftest.py) for path resolution |
| [`.gitignore`](.gitignore) | Excluded credentials, runtime state, artifacts, caches | Inspect before adding/generated files; does not configure a runtime |
| [`agent/contracts/README.md`](agent/contracts/README.md) | Lifecycle/ownership and evidence-reference rules | [Research](agent/contracts/research.yaml) → [Plan](agent/contracts/plan.yaml) → [Build](agent/contracts/build.yaml) |
| [`agent/contracts/research.yaml`](agent/contracts/research.yaml) | Research stage record: `purpose`, `workspace`, `search`, `outputs`, `review`, `checkpoint`, `handoff` | [Plan record](agent/contracts/plan.yaml) after verified Research handoff |
| [`agent/contracts/plan.yaml`](agent/contracts/plan.yaml) | Plan: `research_input`, `implementation`, `gap_analysis`, `fixture_validation_chaos`, `handoff` | [Build record](agent/contracts/build.yaml) after Scanner/recheck and pre-Build validation |
| [`agent/contracts/build.yaml`](agent/contracts/build.yaml) | Build: `plan_input`, `execution`, `implementation_validation`, `post_build_e2e`, `outcome` | Actual host receipts |
| [`tests/test_workflow_contracts.py`](tests/test_workflow_contracts.py) | Contract identity, stale revision, Scanner/Gap Fix, fixture, E2E and evidence-reference **unit** tests | **not** connected-host E2E |
| [`tools/README.md`](tools/README.md) | Tool inventory and design principles | [agent/main.py](agent/main.py) for controller integration |

### Route the question to the owning source

| Agent needs to know | Start reading | Then inspect |
| --- | --- | --- |
| Accepted assignment, milestone, or desired user result | [README.md](README.md) | [agent/main.py](agent/main.py) and current user instruction |
| Current source root, dirty worktree, host tool / Scanner availability | `git status --short` | [Tools README](tools/README.md) and physically discovered source |
| Research fields, required information, evidence and handoff | [Research YAML](agent/contracts/research.yaml) | [Contract guide](agent/contracts/README.md) |
| Plan revision, Scanner findings, universal Gap Fix, pre-Build fixtures/chaos | [Plan YAML](agent/contracts/plan.yaml) | [agent/main.py](agent/main.py) and actual Scanner receipts |
| Build plan-pinning, command receipts, real E2E, recovery, outcome | [Build YAML](agent/contracts/build.yaml) | [agent/main.py](agent/main.py) and actual host evidence |
| Schema/invariant bug or stage-specific handoff validation | [Pydantic models](agent/contracts/models.py) | [Contract tests](tests/test_workflow_contracts.py) |
| Security or ignored local outputs | [`.gitignore`](.gitignore) | Physical worktree, host permissions; never commit credentials |

### Implemented paths — verified in this checkout

All M0–M8 milestones are implemented and verified; eleven G01–G11 gap closures and five S1–S5 connected E2E scenarios sit on top of them. On the current HEAD: **374 passed, 55 skipped** (429 collected). See `README.md` for the scenario and gap-closure matrix.

- `agent/main.py` — OneShotController with stage routing, Scanner invocation, fixture validation, checkpoint/resume.
- `agent/adapters/` — Scanner adapters: `repository_inventory.py`, `source_comparison.py`, `content_integrity.py`, `evidence_locator.py`, `trace_projection.py`.
- `agent/reference/` — Stage-specific guidance: `research_guidance.md`, `plan_guidance.md`, `build_guidance.md`.
- `agent/contracts/` — Contract YAMLs, Pydantic validators (`models.py`), `README.md`.
- `tools/` — 8 active tool implementations (see [tools/README.md](tools/README.md)).
- `tests/` — 19 baseline test modules plus 25 scenario modules in [`tests/scenarios/`](tests/scenarios/) covering contracts, workflow, the five S1–S5 connected E2E scenarios, and the G01–G11 gap closures.
- `pyproject.toml`, `conftest.py`, `requirements.txt` — project configuration. Install dev extras via `python -m pip install --editable ".[dev]"`.
- `.github/workflows/ci.yml` — CI pipeline (ruff + pytest across Python 3.10/3.11/3.12).
- `bin/context_counter.py` — demo build target for E2E.
- No active `src/` directory; historical `src/` is preserved only in git history.

### Fast discovery commands (from verified repository root)

```sh
git status --short
git ls-files
git grep -n 'gap_analysis\|fixture_validation_chaos\|post_build_e2e' -- agent/contracts
python -m pytest tests/ -q
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

## Project baseline rules — apply when the project adopts the pattern

This OneShot checkout is a Python workflow harness; the Research/Plan/Build harness **does not** currently ship a web stack, SQL route handlers, or a migration tool. The four rules below are general-authority project baseline rules recorded here so they apply **automatically** when the project adopts any of those patterns. Each rule carries its scope and the exact action a coding agent must take.

### 1. `.env.example` is the single source of configuration shape

- **Rule.** Copy `.env.example` to `.env` before running anything that reads environment configuration. Tests, the dev server, and any environment-driven controller invocation fail without it.
- **Scope.** Applies whenever `.env.example` is present at the repository root. OneShot itself does not yet ship one — add `.env.example` the moment any configuration key graduates from a code-local default to an environment variable.
- **Agent action.** If `.env` is missing and `.env.example` exists, copy `.env.example` to `.env` with the shipped defaults before invoking tests, the dev server, or the controller. **Do not** commit a populated `.env` — `.gitignore` already excludes `.env` and `.env.*` with a `!.env.example` exception.

### 2. No raw SQL in route handlers

- **Rule.** Never put raw SQL strings inside route handlers. Route handlers call into a repository / query layer that owns parameterized SQL.
- **Scope.** Applies whenever this project adopts HTTP route handlers backed by SQL (Flask / FastAPI / Django endpoints invoking a database). Currently OneShot has no route handlers — this rule binds forward.
- **Agent action.** Reject any handler diff that embeds `conn.execute("SELECT …")` / `cur.execute("INSERT …")` directly. Add the query to a sibling repository / data-access module and have the handler call that module.
- **In-scope today.** The one place SQL exists in this repo is `bin/sqlite_effect_runner.py` — a deterministic effect runner, not a route handler. Its `conn.execute(...)` calls use parameter binding and are not covered by this rule.

### 3. Migrations are append-only once merged

- **Rule.** Never edit a database migration after it has been merged to `main`. Add a new migration instead.
- **Scope.** Applies whenever this project adopts a migration tool (Alembic, Django migrations, etc.). Currently OneShot has no migrations directory — this rule binds forward.
- **Agent action.** If a merged migration contains a mistake, reject any diff that rewrites it in place. Author a **new, forward-only migration** that undoes or corrects the mistake, and reference the original migration by filename / revision id in the new migration's docstring. Mergeable code review on migrations therefore reads: file created, file never modified.

### 4. Lock reads of generated and vendored code

- **Rule.** Agents must not read generated or vendored artifacts: `**/dist/**`, `**/build/**`, `**/*.generated.*`, `**/vendor/**`.
- **Why double-locked.** The repo's `.gitignore` already excludes `node_modules/`, `dist/`, and `build/` from search by default (git-grep / rg respect `.gitignore`). The policy below locks **agent reads** on top of that so even a direct-path open is refused.
- **Enforcement.** [`.agents/settings.json`](.agents/settings.json) carries the deny list:

  ```json
  {
    "permissions": {
      "deny": [
        "Read(./**/dist/**/*)",
        "Read(./**/build/**/*)",
        "Read(./**/*.generated.*)",
        "Read(./**/vendor/**/*)"
      ]
    }
  }
  ```

- **Agent action.** Treat a read against any of those globs as refused. If a legitimate task requires looking at a generated artifact, re-run the generator from source and reason about the source instead; if a vendored dependency really needs inspection, treat it as a dependency version question and consult the lockfile / package manifest, not the vendored tree.

## Provider abstraction — one unified client, many adapters

OneShot MUST drive every model call through the provider abstraction. Do not hard-code `anthropic.Anthropic()`, `OpenAI()`, or any specific vendor across Research / Discovery / Planner / Build. The architecture is:

```
ProviderConfig → ProviderRegistry → ProviderAdapter → OneShotController → Research / Plan / Build
```

Three configuration axes stay separate (one model can run through several endpoints with different capabilities):

- `provider` — adapter key (`openai`, `anthropic`, `openai_compatible`, `echo`, …)
- `model`   — vendor model identifier
- `endpoint` — optional base URL for `openai_compatible` / custom hosting
- `credential_ref` — environment variable the adapter reads at `.generate()` time (never embedded in config)

### Ownership rule

OneShot owns the unified request / response / handoff / validation contract. Each adapter owns provider-specific API translation, authentication, caching, streaming, batch execution, and error normalisation.

### Explicit capabilities — never silent downgrades

Every adapter returns a `ProviderCapabilities` matrix: `structured_outputs`, `streaming`, `batch`, `prompt_caching`, `strict_tool_schemas`. A caller that requests a capability the matrix does not advertise MUST get `UnsupportedCapabilityError` — the workflow fails loudly rather than silently calling a different code path. An unknown provider key is `UnsupportedProviderError`.

### Default and extras

- `echo` adapter ships in-tree, is deterministic, requires no SDK, and is the default used by tests and CI. Request content maps to `sha256(canonical_request)` so two identical requests produce byte-identical responses.
- `pip install 'oneshot[openai]'` or `pip install 'oneshot[anthropic]'` installs the vendor SDK; the matching adapter stub registers itself at import time.
- Meta Llama runs through the `openai_compatible` adapter (vLLM, Together, Fireworks, Groq, Ollama's OpenAI shim, …): pick the endpoint; the capabilities are the least-common-denominator stub, and a concrete subclass may override them.

### Python usage

```python
from agent.providers import ProviderConfig, ProviderRegistry, UnifiedRequest
from agent.providers.types import Message

cfg = ProviderConfig(
    provider="openai_compatible",
    model="meta-llama/Meta-Llama-3-70B-Instruct",
    endpoint="https://api.together.xyz/v1",
    credential_ref="TOGETHER_API_KEY",
)
client = ProviderRegistry.create(cfg)

response = client.generate(
    UnifiedRequest(messages=[Message(role="user", content="hello")])
)
```

Or on the controller:

```python
from main import OneShotController
from agent.providers import ProviderConfig

ctrl = OneShotController(
    storage_path="/tmp/tasks.json",
    provider_config=ProviderConfig(provider="echo", model="echo-1"),
)
response = ctrl.model_call(request)   # routes through self.client
```

The default `OneShotController()` still works — `self.client` is `None` until a `provider_config` is supplied; `model_call(...)` raises `RuntimeError` instead of silently calling a default provider.

## Validation and completion

- Run focused tests and then applicable project-defined lint, type-check, test, and build commands. Validate user-visible results against **independently established expectations**, including negative or recovery cases when relevant.
- Record exact commands, files, outputs, errors, and limitations. Mark checks `verified`, `failed`, `not_run`, or `not_available`. Never claim a command ran, a trace exists, a model responded, or a deployment succeeded without evidence.
- Reconcile all ExecPlan milestones as **done**, **blocked** (reason), or **cancelled** (reason); leave no ambiguous in-progress claims at handoff.
- Report substantial changes concisely: **Area → Exact Files/Folder → Commands Run → Verified Outcome → Remaining Issues**.
