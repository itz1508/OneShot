# Research Guidance

## Required action sequence
1. **PLAN:** Derive an operational research plan from the accepted request (objective, questions, evidence sources, acceptance checks). A small request still gets a one-line plan.
2. **CREATE TODO FIRST:** Persist ordered TODOs through the verified Research TODO interface before using any research/file/search tool. Include the evidence and validation steps. If the interface is unavailable, report BLOCKED; do not simulate it with narrative text.
3. Preserve original request and accepted revision; verify the workspace only under an authorized TODO.
4. Execute research TODOs: gather complete requirements, candidate dependencies, interfaces, official references, alternatives and contradictions. For planning_search delegate using task(); single_search may search directly.
5. Keep provenance, unsupported claims, uncertainty, and immediate-action recommendations explicit. Do not choose the final strategy, implementation files, or Planner actions.
6. Produce `_research.json` and the human-readable report using the active contract. Update each TODO with evidence references.
7. Validate the record and evidence; return for `review_result` and STOP. Never transition directly to Planning.

## Boundaries
- The operational plan/TODO is **not** the formal Planner output.
- Research inventories possibilities; Audit Discovery determines repository relevance; Planner chooses implementation.
- No implementation edits, Build admission, fixture pass claims, or self-approval.
