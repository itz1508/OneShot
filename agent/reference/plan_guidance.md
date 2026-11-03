# Planning Guidance

## Required action sequence
1. **PLAN:** From the accepted handoff, define the operational planning approach, required inspection, Scanner checks, and completion conditions.
2. **CREATE TODO FIRST:** Persist ordered TODOs with the verified Planner TODO interface before repository inspection or tool use. If unavailable, return BLOCKED; update the list on revision.
3. Read exact accepted Research and Audit Discovery record IDs, revisions, manifests and repository snapshot; reject stale or contradictory inputs.
4. Inspect relevant target files and dependencies. Select architecture, exact file actions, milestones, recovery, and acceptance criteria; these decisions belong to Planner alone.
5. Invoke the existing System Scanner over the real planning scope. Classify missing, drift, overlap, duplication, contradictions, dependency, feasibility, and coverage findings.
6. Choose dispositions and authorize in-scope corrections; the separate authorized Fix execution applies changes and returns receipts. Recheck every affected Planning revision. Do not have the Planner silently edit implementation code.
7. Define fixtures, expected outputs, error/boundary/chaos cases and independent oracles. Independent Fixture Validation must execute and produce a receipt before Build Admission.
8. Produce `_planning.json`, bind accepted criteria and exact revisions, and record Scanner/fixture/admission evidence. Verify Build Admission requirements; an unchecked gate stays blocked.
9. Update TODO status, validate the Planning output and handoff, then return for `review_result` and STOP. Never execute the admitted Build.

## Boundaries
- Operational PLAN/TODO does not itself authorize Build.
- Planner selects strategy and corrections; Fix executes authorized corrections; Validator independently checks fixture readiness.
- Only the host enforces stage transitions and admission on validated receipts.
