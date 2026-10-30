# OneShot — AGENTS.md

Repository guidance for coding agents. This file explains **how to work** and where to find the accepted specification; it is not another Research, Plan, Build template or an agent runtime.

## Start here — existing authority

1. Confirm the actual checkout with `git status --short`, `git rev-parse HEAD`, and `git ls-files`. Inspect staged, unstaged, and untracked work before writing. A GitHub snapshot does not establish the state of a Databricks or other active workspace.
2. Read, in order, [README.md](README.md), [BUILD_INSTRUCTION.md](agent/implementation/BUILD_INSTRUCTION.md), [ExecPlan.md](agent/implementation/ExecPlan.md), and [the contracts guide](agent/contracts/README.md). Inspect `agent/contracts/research.yaml`, `plan.yaml`, `build.yaml`, and `check_contracts.py` for the particular stage being implemented. These are **real files in this repository**. This document points to them; it does not automatically load them.
3. **Continue the committed M0–M8 ExecPlan.** Update its Progress, Surprises & Discoveries, Decision Log, Outcomes, executed commands, and recovery notes. Do not invent a replacement plan, restart finished work, or ask the user to select generic next steps.
4. The current `main` is an **implementation baseline, not a running harness**. The proposed `agent/main.py` does not yet exist. `tools/README.md` is staging guidance, **not executable tool code**. At M0, identify the real tool interfaces and Task Management / artifact store in the physical workspace. The Databricks `tools/` content has not been verified in this clone.
5. Historical `src/`, obsolete 00–11 assignments, and their tests are preserved on `archive/legacy-src-pre-harness-2026-10-29`; they are **reference material, not current architecture**. Do not resurrect them, rename them into `tools/`, or import stale tests as acceptance proof.

The latest explicit user requirements override conflicting older decisions within their scope. Current source proves what exists; it does not override accepted requirements. Separate observed facts, accepted decisions, proposals, assumptions, and unknowns.

## One workflow, existing owners

For this implementation, follow the complete accepted path in the build instruction:

```text
Research → Research artifacts → Plan
  → System Scanner Gap Analysis → Gap Fix → recheck
  → Fixture Validation + Chaos (independent pre-Build expectations)
  → Build the verified Plan ID/revision → implementation checks
  → real post-Build E2E → verified result
```

- **One controller:** implement the proposed `agent/main.py` only after discovering supported host APIs. Research, Plan, and Build are responsibilities with Markdown guidance and the three YAML record contracts, not three independent controllers.
- **One Scanner:** Gap Analysis invokes the existing System Scanner through an actually available tool interface. Inspect missing, drift, overlap, duplication, contradiction, dependencies, feasibility, coverage, and applicable safety/mismatch issues. Preserve evidence, provenance, and uncertainty; do not manufacture a Scanner result.
- **One Gap Fix:** correct every confirmed actionable issue in the authorized scope at its responsible stage, then recheck. Apply the same correction responsibility to later Build/E2E failures; revalidate affected downstream artifacts.
- **One task/persistence owner:** use the verified Task Management and artifact resolver. Maintain stable `task_id`, stage records, revision-linked handoffs, decision history, checkpoints, and side-effect receipts. Do not create a competing store. A success flag or YAML syntax check is not proof of a successful stage.
- **No fabricated host behavior:** discover hooks, model/tool access, permissions, clarification, and execution interfaces before calling them. If a required capability is unavailable, report the exact blocker; never replace it with a stub or simulated receipt.
- **No redundant questions:** populate Research Input from the user's original request, accepted context, and available evidence. Route genuinely blocking user-owned unknowns through the supported host clarification path; leave researchable unknowns to Research.

## Work with evidence and minimal changes

- Identify the objective, scope, actual source root, expected outcome, and acceptance evidence before editing. Inspect the *physical* files; prefer indexed search and focused reads over repeated full-tree scans.
- Research consequential technical claims with applicable primary sources or the project's verified code. Challenge an incorrect proposal using evidence, impact, an alternative, and verification; do not manufacture objections.
- Keep edits scoped, preserve unrelated changes, and inspect the diff. Read a destination before overwriting it, including Databricks notebook writes. Retire outdated code or tests only after verifying replacement coverage and preserving necessary evidence.
- Prefer existing tools and configured practices over added frameworks. Do not create a standalone Quality Input subsystem, another Scanner/controller, a new permission service, unsupported hooks, or a separate Chaos stage.
- For multi-milestone work, the **existing ExecPlan** is the living record: keep precise file mappings, milestones, observed results, limitations, and a safe restart point. Only independently justified changes may alter its scope.

## Commands — verify before executing

From this repository root, the **currently checked-in contract baseline** is:

```sh
python -m unittest discover -s tests -p 'test_workflow_contracts.py' -v
```

It checks contract invariants only. It **does not** exercise an agent, Scanner, persistence, real tool execution, or post-Build E2E. Use Python 3.11+ for the existing checker.

```sh
git status --short
git ls-files
git diff --check
# If installed and useful:
rg --files
rg -n '<term>' '<actual_path>'
```

The current clone has **no** `pyproject.toml`, `uv.lock`, or `package.json`. Do not treat `uv sync`, `pip install`, `npm ci`, `pnpm`, or `ruff` as baseline commands. If real source and manifests later establish a Python or frontend toolchain, follow their lockfiles and configured test/lint/build scripts; explain environment changes before running them. For Pydantic, use the actual model validator; `python -m json.tool` checks JSON syntax only.

Choose test commands from verified configuration. Run relevant focused tests first, then applicable broader checks. Distinguish `passed`, `failed`, `skipped`, `blocked`, and `not_executed`; record exact commands, cwd, environment, receipts, and observed results.

## Handoffs, recovery, and finish line

- Research can hand off **before Plan exists**; Plan can hand off **before Build exists**. Reconcile and test stage-specific checks rather than filling downstream records with placeholders. A handoff is permitted only when evidence-backed invariants pass for the current revision.
- Fixture Validation + Chaos validates independently prepared expected outcomes **before Build**. After Build, execute applicable fixture, negative, boundary, corruption/recovery, and actual user-outcome checks **through the built entrypoint**. Build success alone never means task completion.
- On interruption or retry, inspect current source/revision, last checkpoint, action ID, receipts, and uncertain side effects. Reconcile before repeating a write. Upstream changes invalidate affected downstream verification.
- At each stopping point update the ExecPlan and durable stage records with what actually happened. Report **Area → Changed paths → Commands/results → Evidence → Remaining blockers**. Do not claim live E2E, host integration, or GitHub updates that were not observed.

For a small unrelated task, apply proportionate review and testing. For the **workflow-harness implementation**, execute and verify the entire M0–M8 acceptance path.
