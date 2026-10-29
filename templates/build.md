# Build — reusable workflow template

**Applicability:** Use only for an explicitly approved Plan whose authorized execution scope and target environment have already been established. Build may start from an accepted Plan without requiring a new Research run. This template does not operate tools or provide permission by itself.

**Existing authority:** Output schema is `output/schema/build.json`; actual Build(id) execution, verification, cleanup evidence and persisted observations are owned by the existing Build/Task implementation. Never create a manual parallel build log, alternative executor or result store.

**Quality Input:** Use the shared strict contract `templates/schema/input.json`, with `template_id` set to `build`. The selected template is explicit; this does not select a workflow, infer missing fields, ask questions, or grant host permissions. `readiness: blocked` must disclose blocking unknowns. The host decides how to resolve them before execution.

## Required inputs and admission

- An existing task-scoped Plan(id), verified source identity/revision and the precise requested changes; accepted evidence and validation values where available.
- An independent **trusted host/operator grant** for that exact task/plan and target; mere Plan existence, schema validation, conversational text and requested filenames are not grants.
- For the provided 0.5.0 candidate, the existing Builder is **not a general code executor**: it creates at most eight new UTF-8 artifacts (up to 128,000 bytes each) with safe names appearing in approved Plan targets, never overwrites, does not execute shell commands or modify repository source. Reinspect the actual installed runtime before applying these bounds elsewhere.

## Work specification (expected, not observed)

- Name the selected Plan actions and bounded changes, with explicit non-goals and prerequisites. Require safe source inspection before any authorized write; reread selected targets if source freshness is material.
- State independent expectations for execution, result bytes/artifact identity, source-of-truth validation and failure/negative/recovery cases. Do not derive the expected oracle solely from generated output.
- Require verified readback/content hash where applicable; capture the **actual** execution outcome, evidence/artifact references, verification outcome and owned temporary-resource cleanup status in one Build(id). Failed execution and failed cleanup are separate facts.

## Completion and stop

- Record observed results only in existing Build(id)/Task-owned persistence, validated against `output/schema/build.json`; the template remains an instruction, not a mutable execution receipt.
- Report failed, cancelled, timed-out, interrupted and not-verified cases accurately. Preserve permanent artifacts, task events and evidence; remove only Build-owned temporary resources after durable observation.
- Do not claim MCP stdio, live ChatGPT invocation, browser end-to-end or deployment merely from local JSON or Python tests.
- Stop after the selected approved phase; commits, pushes, deployments, credentials and external writes require separate host authorization. **No automatic next stage.**
