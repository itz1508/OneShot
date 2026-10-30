# OneShot — Agent Operating Instructions

## 1. Authority and overrides

- The user's latest applicable explicit instructions are the source of truth for the task's objective, scope, requirements, and deliverable, subject to host permissions and higher-priority safety requirements.
- **Override means replace**: a newer instruction supersedes conflicting older instructions within its scope. Do not merge rejected requirements back into the task.
- Treat memory, `README.md`, archived material, old 00–11 assignments, previous agent outputs, and other historical documentation as context or evidence, **not** current requirements.
- Existing code establishes what is implemented, not what the user wants. Inspect it where relevant; do not copy its architecture by default.
- Apply the user's requested deliverable directly. Do not turn template fields into new skills, hooks, services, schemas, gates, or tools without an actual need.

## 2. Shared bootstrap — System and Agent

- **Bootstrap is System-owned startup context**, not a workflow-selection stage. The agent only checks whether that context is available; it must not rerun, recreate, or assume the Bootstrap occurred.
- Discover the actual repository path and available files. Consult available, authorized memory/RAG and applicable `AGENTS.md` and reference sources. Do not claim any source was loaded before reading it.
- Record what was actually found; mark unavailable sources as unavailable. Do not claim a document was loaded without reading it.
- Do not promote stale material into authority. Do not change or archive files during discovery.
- Continue the operation already indicated by the user's request; do not ask the user to choose System or Research again.

Record the observed startup context in this compact form (not a new Bootstrap task):

```yaml
bootstrap:
  repo_path: <discovered path | unavailable>
  system_bootstrap: available | unavailable | not_confirmed
  memory: loaded | not_loaded | not_confirmed
  agents_md: loaded | unavailable | not_confirmed
  reference_sources: []
```

## 3. Research — two templates

**Research Input** is populated before Research from the request, accepted instructions, available context, and task-relevant evidence. Quality Content means accurate, complete input **content**; it is not a separate runtime component. `agent/contracts/research.yaml` is the durable Research stage record, not a replacement for the Research Input/Output distinction.

```text
create_task_id()
Input_contents_research()
Input_tasks_research()
input_files_research()
```

- Identify requirements, constraints, expected outcomes, and missing information in the input as applicable; represent structured content in YAML.
- Do not invent facts or ask for information already established. Keep researchable unknowns for Research; ask only when a genuinely blocking user-owned decision cannot be established.

**Research Output** is populated after investigation, using actual findings and evidence:

```text
create_output_id()
input_artifact_<template>
output_artifact_<template>
output_plan_task()
output_fixture_validation()
output_success_criteria()
output_validation()
```

- Report requirements, constraints, expected outcomes, missing information, dependencies, and supporting evidence where applicable.
- Keep expected fixture outcomes separate from observed validation. Mark untested work as untested.
- These names describe template operations and fields, not instructions to create Python functions or modules.
- Do not use Research Output as the Build Output template.

## 4. Source exploration and research

- **Think first.** Identify the task objective and the resources currently likely to matter before calling tools.
- Batch independent reads using host-supported parallel capabilities; read sequentially when earlier results determine later sources.
- Inspect actual relevant code before recommending source changes. Expand discovery when evidence justifies it; avoid rereading unchanged files.
- Research current official practices when external technical knowledge is necessary. Compare them with observed implementation; distinguish requirements, defects, options, and unknowns.
- Preserve source provenance and contradictions. Do not mistake examples or documentation for user-authorized architecture.

## 5. Plan and Build

For the current harness implementation, first read `agent/implementation/BUILD_INSTRUCTION.md`, continue the accepted M0–M8 `agent/implementation/ExecPlan.md`, and follow `agent/contracts/README.md`, `agent/contracts/research.yaml`, `agent/contracts/plan.yaml`, and `agent/contracts/build.yaml`. Do not create another implementation plan. This clone is a contracts-and-instructions baseline, not a working harness; the historical `src/` tree is archived and active Databricks `tools/` source is unverified here.

- **Plan:** Use accepted requirements and Research evidence to produce an actionable plan, real dependencies, expected outcomes, and verification criteria. Do not manufacture steps or insist on a plan for simple tasks.
- **Build:** Implement the requested outcome using supported tools and existing capabilities. Reuse code where appropriate; create or modify files only when needed for the outcome.
- Do not add new architectural boundaries, permission services, authorization gates, hooks, or parallel frameworks merely to enforce agent instructions. Respect actual host permissions.
- Do not delete, archive, overwrite, or revert unrelated existing work without user authorization. Never circumvent a denied operation with another tool.
- Test real behavior and independently inspect results. A written contract, self-reported pass flag, or successful file write is not proof that the product works.

## 6. System, notebooks, and tools

- **System Summarize:** Where the active product exposes **Generate**, it requires that explicit action; Agent generation requires explicit invocation. Do not infer execution authorization from ordinary chat, and verify the actual active UI/admission boundary. Neither path depends on a Quality Content subsystem.
- Databricks notebooks may bootstrap dependencies and dry-test Research, Plan, and Build; they are test/initialization workspaces, not replacements for OneShot project files.
- Reuse verified initialization and provider configuration. Inspect `agent.py` **if it exists** before notebook file writes; do not assume the file exists or overwrite it during setup.
- Use the smallest sufficient supported tool set. Do not expose internal functions as public MCP tools without a demonstrated user-facing need.
- Keep simulated dry tests, live model calls, and real integration tests clearly distinguished.

## 7. Reporting and completion

- For substantial work, state the objective and approach briefly. Give meaningful findings without repetitive status updates.
- Report implementation results as **Area → Exact Files/Folder → Verified Outcome**. Distinguish created, modified, unchanged, and unverified items.
- Document what ran, what passed, what failed, and what remains unknown. The current repository's established check is `python -m unittest discover -s tests -p 'test_workflow_contracts.py' -v` (contract tests only, not harness E2E). Do not invent traces, test receipts, artifact IDs, or completion claims.
- Finish the requested work rather than ending with a plan alone, unless the user requested planning only or a real blocker prevents execution.