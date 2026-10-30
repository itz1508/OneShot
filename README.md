# OneShot — workflow harness implementation baseline

**Current state: READY TO CONTINUE IMPLEMENTATION; NOT A WORKING HARNESS.** This clone contains the accepted Research/Plan/Build contracts, a read-only invariant checker, a complete implementation instruction and a self-contained M0–M8 ExecPlan. No connected System Scanner, `agent/main.py` controller, live tool runtime or post-build E2E is claimed.

## Start here

1. Clone: `git clone https://github.com/itz1508/OneShot.git` and `cd OneShot`.
2. Read [AGENTS.md](AGENTS.md), the [build instruction](agent/implementation/BUILD_INSTRUCTION.md) and [living ExecPlan](agent/implementation/ExecPlan.md).
3. Read the [committed contract rules](agent/contracts/README.md) and inspect the three YAML templates.
4. **M0 first:** inspect the actual active workspace, dirty changes, configuration and host tool interfaces. The Databricks `tools/` implementation is **not included or verified** in GitHub. Bring its verified authoritative files into this checkout only after comparing both sources; do not restore historical `src/` automatically.
5. Continue M1–M8, committing source and evidence as each milestone is genuinely verified.

## File ownership

- `agent/contracts/{research,plan,build}.yaml` — durable stage record templates.
- `agent/contracts/check_contracts.py` — existing read-only contract checker (not a controller).
- `tests/test_workflow_contracts.py` — **contract invariants only**, not a live E2E suite.
- `agent/implementation/BUILD_INSTRUCTION.md` — current complete implementation assignment.
- `agent/implementation/ExecPlan.md` — milestones, evidence, decisions, recovery and known gaps.
- `tools/README.md` — staging guidance, **not a substitute for actual host tools**.

## Baseline contract verification

Use Python 3.11 or later. With the repository as the current directory:

```shell
python -m unittest discover -s tests -p 'test_workflow_contracts.py' -v
```

This test is intentionally limited to structural and evidence-reference logic. A passing result does not prove Research execution, Scanner calls, persistent task state, Build or E2E. The executable stage flow remains to be implemented.

## Historical sources (preserved)

The prior `src/` modules, legacy tests, obsolete 00–11 instructions, and `TRACEABILITY.md` have been **retired from active `main`**, not lost. Their precise pre-cleanup state is in the read-only reference branch [`archive/legacy-src-pre-harness-2026-10-29`](https://github.com/itz1508/OneShot/tree/archive/legacy-src-pre-harness-2026-10-29). Only reuse independently verified behavior that serves the current requirements. Git history remains intact.

**No code from the unavailable Databricks working tree was copied, restored, deleted or modified by this repository cleanup.**
