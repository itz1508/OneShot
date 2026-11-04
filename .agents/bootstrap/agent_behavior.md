# Global agent behavior

## Rule — plan and task checklist first

Read the assigned role, applicable repository instructions, exact input references, and host permissions. **Before acting**, state a short role-specific plan and create a task checklist. Keep the checklist in the host task state or current response; do not create Markdown logs or planning files automatically.

A plan means different things for different roles: Research plans investigations; Audit Discovery plans read-only inspection; Planning makes implementation decisions; Fixture Validation plans independent checks; Build creates only an **execution checklist derived from the admitted specification**; Build Verification plans independent E2E checks. The Builder does not design or revise the plan.

## Execution discipline

- Consume the exact approved input revisions. Preserve upstream artifacts and evidence without rewriting them.
- Separate observed facts, proposed decisions, assumptions, uncertainties, and actual verification results.
- Use only registered role-visible tools. The host alone owns authorization, source effects, immutable persistence, checkpoints, receipt issuance, stage transitions, and cleanup.
- Work through the checklist within the existing authorization. Stop only for a material blocker, contradiction, unavailable required tool, or missing host gate; do not add approval loops.
- Report completed checklist items with observed evidence and name blocked or unexecuted checks explicitly. Never interpret model output, an advisory hook, or an unverified digest as a trusted host receipt.
- Return the role's output to the host. A role never self-certifies or advances itself to another stage.
