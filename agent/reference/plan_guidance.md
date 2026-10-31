# Plan Guidance

## Steps
1. Read exact Research record ID, revision, and manifest; detect stale source.
2. Inspect actual target files, dirty state, runtime, dependencies, commands.
3. Promote candidate plans.md to self-contained ExecPlan.md with exact file destinations, milestones, rollback/resume strategy.
4. Invoke System Scanner with actual scope; analyze missing, drift, overlap, duplication, contradictions, dependencies, feasibility, coverage.
5. Gap Fix: correct all confirmed actionable in-scope issues at root cause. Every fix gets cause, action, evidence, recheck.
6. Rerun Scanner on changed Plan revision.
7. Independently prevalidate fixture inputs, expected outputs, errors, negative/boundary cases, and chaos fault/recovery cases before Build.

## Key rules
- Scanner returns evidence or explicitly not_checked; no shallow presence checks.
- Chaos defined under fixture_validation_chaos, not an independent stage.
- Validate Plan alone with check_contracts.validate_plan() before handoff.
