# OneShot Prompt Correction Traceability

## Summary

12/12 prompts semantically corrected and written as real files in the OneShot repository (github.com/itz1508/OneShot, main branch).

All prompts are corrected against:
- Market-practice gap matrix (00-11)
- OpenAI Agents SDK, Google ADK, Anthropic, LangGraph, Databricks MLflow practices
- Accepted OneShot requirements from the repository README
- No stale references (no HANDOFF.md, REBUILD_PLAN.md, EXECUTION_PLAN.md, confirmed repository metadata, or confirmed rebuild scope)

## Gap Resolution Per Prompt

| # | File | Gap Area | What Was Wrong | What Was Corrected | Evidence |
|---|---|---|---|---|---|
| 00 | research/00-repo-summary.md | Authority | Referenced stale 'confirmed repository metadata' and 'confirmed rebuild scope'. Asked to reconstruct 'twelve historical failures'. Placeholder verified_start. | Replaced with actual repo (github.com/itz1508/OneShot, main). Gap matrix (00-11) replaces historical failures. Concrete verified_start with actual repo. Host tools identified for reuse. Color Eval baseline added. | README confirms clean start; archive branch is read-only historical context |
| 01 | research/00-memory-retrieve.md | Task Management | Said 'verify' Task Management as if it existed. No persistence mechanism specified. No restart/resume/retry criteria. | Changed to 'implement'. Added Unity Catalog/MLflow for persistence. Added restart, resume, retry, no-duplicate tests. LangGraph thread state vs long-term memory distinction. Color Eval added. | All four acceptance tests defined with concrete E2E criteria |
| 02 | research/01-quality-input.md | Quality Input | Said 'verify' Quality Input as if it existed. No STOP/resume behavior. No ambiguity detection. | Changed to 'implement'. Added missing-input STOP, host clarification, resume with context preservation, ambiguity detection. Color Eval added. | Four tests: complete proceeds, incomplete stops, resume preserves, ambiguity detected |
| 03 | research/02-search-sources.md | Research startup | Referenced 'actual Scanner' as existing component. No host tool reuse. | Replaced with Databricks SDK (WorkspaceClient) and Git integration. No custom scanner. Grounded file inventory with actual paths, types, sizes. Color Eval added. | Four tests: file listing, pattern search, archive search, empty repo handling |
| 04 | research/03-research-output-package.md | Research output | No provenance tracking. No independent validation values. Self-validating assertions possible. | Added provenance (file path, line range, commit SHA). Added independent validation values. Contradictions and open questions explicitly recorded. Color Eval added. | Five tests: findings with sources, provenance, independent validation, contradictions, plan candidate |
| 05 | research/04-research-review-confirmation.md | Research review | No evidence-based quality checks. No Color Eval. No critical override rule. | Added groundedness, completeness, contradiction checks. Color Eval GREEN/YELLOW/RED with critical override (one RED = entire Research RED). Binding confirmation with digest. | Four tests: GREEN, RED detection, YELLOW detection, confirmation locks |
| 06 | plan/00-phase-1-research-grounding.md | Plan | Gap passes not defined against actual code or market practices. No Call for Help protocol. | Gap Pass 1: verify against actual code. Gap Pass 2: verify against OpenAI, Google, Anthropic, LangGraph. Call for Help requests evidence, doesn't infer. Color Eval added. | Four tests: Pass 1 grounding, Pass 2 best practice, gap flagging, Call for Help |
| 07 | plan/01-fixture-readiness.md | Fixtures | Self-validating fixtures possible. No independent expected results. No realistic data requirement. | Added independent expected results (not self-validating). Realistic data from actual repository. Positive and negative cases. Executor verification. Color Eval added. | Four tests: positive pass, negative fail, independent results, grounded data |
| 08 | plan/02-ready-to-build-approval.md | Approval | Authorization by text convention, not host enforcement. Model text could authorize. | Added host-enforced authorization (Databricks workspace, UC access control). Model text explicitly rejected. Unauthorized build physically blocked. Color Eval added. | Four tests: unauthorized blocked, authorized proceeds, model text rejected, bindings verified |
| 09 | build/00-todo-list.md | Build | No host tool reuse. No Agent→Tool→Result→Agent pattern. Silent cleanup of partial failures. | Added Databricks Jobs, MLflow, OpenAI Agents SDK. Agent→Tool→Result→Agent continuation traced. Partial failures preserved. Artifact hashing. Color Eval added. | Four tests: artifacts hashed, schema valid, fixtures pass, continuation traced |
| 10 | build/01-mcp-integrations.md | MCP / tools | No UC function or AI Gateway usage. No least privilege. No error handling criteria. | Added Unity Catalog functions and AI Gateway. Least privilege via UC permissions. Error handling with no side effects. No core logic in MCP. Color Eval added. | Four tests: results correct, permissions enforced, errors handled, no core logic |
| 11 | build/02-e2e-clean-delivery.md | E2E | No real E2E test criteria. No restart/recovery test. No invalid input test. SQL keyword scans accepted as E2E. | Added real E2E with actual tool calls. Restart recovery test. Invalid input test. Persisted results test. Explicit: SQL scans insufficient. Color Eval with critical override. | Four tests: complete task, restart recovery, invalid input, persisted results |

## Cross-Cutting Corrections Applied to All 12 Prompts

1. **Removed all stale references**: No HANDOFF.md, REBUILD_PLAN.md, EXECUTION_PLAN.md, 'confirmed repository metadata', 'confirmed rebuild scope', or 'shared handoff'.
2. **Added Color Eval**: Every prompt has a `color_eval` block with GREEN/YELLOW/RED definitions and criteria.
3. **Added verifiable E2E acceptance criteria**: Every prompt has 4-5 concrete tests with expected behavior.
4. **Added host tool reuse**: Databricks SDK, MLflow, Unity Catalog, AI Gateway, OpenAI Agents SDK, Git integration.
5. **Added market-practice references**: OpenAI Agents SDK, Google ADK, Anthropic, LangGraph.
6. **Changed from verify to implement**: Prompts 01-05 changed from 'verify existing component' to 'implement component'.
7. **Concrete repository target**: All prompts reference github.com/itz1508/OneShot, main branch.
8. **Implementation-focused**: Each prompt creates actual source files (e.g., task_management.py, quality_input.py) with tests.
9. **One-time assignments**: Each prompt is explicitly a one-time build assignment, not a permanent workflow stage.
10. **Research starts with repo-summary and memory-retrieve**: Prompts 00 and 01 run first, in parallel.

## Remaining Gaps (Not Addressed by Prompts Alone)

These require actual implementation and execution:
- Semantic correctness of the implementation code (not just prompts)
- Instruction-level contradiction analysis across implementations
- Agent runtime tool binding and real invocation
- Complete E2E behavior with observed results
- These are the 'Final deliverable' — working OneShot functionality verified through contracts, workflow, and E2E execution.

## Repository State

- Repository: github.com/itz1508/OneShot
- Branch: main
- Files added: 12 prompt files + this traceability document
- Directory structure: research/ (6), plan/ (3), build/ (3)
- No existing source code modified (main branch was source-free)