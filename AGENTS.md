# OneShot — Repository Work Instructions

This file defines **standing work practices** for contributors and coding agents. It is not a task request, execution plan, runtime contract, permission grant, status report, or build log.

## Source of truth and workspace

- **`/OneShot`** is the clean rebuild target. Check `git status` and `git log` before making changes.
- Use Python **3.11+**, Pydantic **v2**, and **uv**. `pyproject.toml` declares dependencies; `uv.lock` records the resolution.
- `settings/config.yaml` is the runtime/provider configuration. Validate against implemented schemas; do not invent settings.
- Meta Muse Spark 1.3 is the configured **default** provider. Claude Agent SDK and Codex SDK are **optional** adapters.
- The `echo` provider is a test double only — never the runtime default.

## Commands and dependency conventions

| Task | Convention |
| --- | --- |
| Check Python | `uv run --no-sync python --version` |
| Check lock | `uv lock --check` |
| Sync baseline + Meta | `uv sync --locked --extra meta` |
| Run tests | `uv run --no-sync pytest -q` |
| Lint | `uv run --no-sync ruff check .` |
| Format check | `uv run --no-sync ruff format --check .` |
| Type check | `uv run --no-sync mypy agent` |
| Check environment | `uv run --no-sync python scripts/doctor.py` |
| CLI | `uv run --no-sync python -m agent doctor` |

## How to perform authorized work

1. **Establish scope** before modifying. Inspect `git status`, relevant code, and contracts.
2. **Research** establishes evidence, not implementation design.
3. **Audit Discovery** is read-only. Record grounded findings and candidate CodeIntent.
4. **Planning** owns architecture, design decisions, and BuildSpecification. No source writes.
5. **Validation and admission** are host-owned. The host, not the Planner, validates and freezes.
6. **Build** executes only admitted operations. Check preconditions at effect time.
7. **Independent verification** runs real E2E checks against accepted criteria.

## Responsibility boundaries

- **Researcher:** requirements, evidence, acceptance criteria. No final design.
- **Audit Discovery:** read-only findings, CodeIntent. No Build dispatch.
- **Planner:** design, BuildSpec, Scanner requests. No freeze or admission.
- **Fixture Validator:** independent observations. No frozen spec mutation.
- **Builder:** admitted operations only. No scope expansion.
- **Build Verifier:** independent E2E. No self-certification.
- **Host:** transitions, authorization, persistence, freeze, admission, effects, receipts.

Authorization is **default-deny and host-enforced**. Every effect requires a host gate.

## Security and completion

- Keep secrets in environment variables, never in Git. Commit only `.env.example` placeholders.
- Use minimal changes. Preserve working tests. Never weaken assertions to make checks pass.
- If a check is unavailable, mark it **not checked** or **blocked**, not passed.
