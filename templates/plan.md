# Plan — reusable workflow template

**Applicability:** Use for an explicitly requested, reviewable specification of intended work. Plan may consume an existing Research result, or sufficient accepted evidence without a new Research stage. A finished Plan does not automatically begin Build.

**Existing authority:** The host provides the current request and accepted decisions. `output/schema/plan.json` is the canonical shape of `Plan(id)`. The active Task store validates any `research_id` link within the task. Do not invent a selector, a validation authority, or a new record store.

**Quality Input:** Use the shared strict contract `templates/schema/input.json`, with `template_id` set to `plan`. The selected template is explicit; this does not select a workflow, infer missing fields, ask questions, or grant host permissions. `readiness: blocked` must disclose blocking unknowns. The host decides how to resolve them before execution.

## Inputs / read-only review

- Read the original request, authorized source state, any applicable repository instructions, accepted requirements and decisions, and Research(id) when required and available.
- Survey actual source identity, relevant dependencies, completeness, contradicting evidence, scope, constraints and task-specific expected behavior. Report missing evidence separately from proposed resolution.
- Preserve the Research-established validation facts and provenance **without rewriting them as independent truth**. If a blocking input is unknown, explicitly mark the plan as blocked for implementation and request that the existing host clarify when supported. Do not guess.

## Proposed work

- Describe why the proposed behavior meets the accepted objective and which files/capabilities are within and outside scope. Only include implementation phases as justified by the approved objective; no fixed mandatory phase hierarchy.
- For each intended action, state prerequisites, intended outcome, compatible target when needed, independent red/green/refactor/verification expectations where applicable, negative cases and rollback/recovery constraints. Reference existing evidence instead of copying it into another authority.
- Host authors a `Plan(id)` under `output/schema/plan.json`; represent proposed actions in the schema's supported structure. A Plan may reference an existing Research result using `research_id` when linked within the same task. The Task store retains the actual record.
- **Contract:** Optional `validation_value_refs` identify Research-owned validation IDs when `research_id` is present. They do not redefine their expected values, prove that a value exists, or authorize Build. The schema still has no typed phase acceptance arrays or permissions. Do not claim JSON validation proves semantic continuity.

## Boundaries, completion, handoff

- Plan is **read-only**: no repository mutations, source repairs, artifact writes, tests with side effects or Build execution by the Planner.
- Plan does not establish replacement Research validation values. No Plan ID, JSON validity, target name or handoff grants permission to Build.
- A plan is review-ready only with clear scope/non-goals, supported prerequisites and actionable acceptance evidence, or explicitly unresolved blocking items. Report source identity and limits.
- On completion, retain one Plan(id) with task identity; a separately approved and independently admitted Build may reference it. **No automatic next stage.**
