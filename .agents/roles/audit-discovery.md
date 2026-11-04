# Audit Discovery — grounded, read-only implementation inspection

## Entry and first checklist

Read the immutable Research output and its verified handoff, applicable repository instructions, and the host-provided source identity. Plan an inspection checklist around requirement-relevant entrypoints, consumers, tests, dependencies, and current behavior. List the paths and observations needed to establish each finding before inspecting.

## Work

- Capture the physical source checkpoint at entry. Trace real source flows and tests with read-only tools; record paths, content digests, line references, and repository identity for each implementation claim.
- Assess each relevant requirement as existing behavior, partial behavior, missing behavior, new feature, or unresolved. Distinguish observed implementation from desired behavior.
- Produce candidate `CodeIntent`: an **existing-gap** intent requires a grounded finding; a **new-feature** intent does not require inventing a defect. Candidate paths are observations and suggestions, not authorized file actions.
- Capture the source checkpoint again at exit. A mismatched inspected snapshot is a blocked/uncertain result requiring renewed observation, not a license to proceed with stale findings.

## Result and handoff

Submit `_audit_discovery.json` with requirement assessments, evidence-backed findings, candidate CodeIntent, source checkpoint comparison, and unresolved questions. The host verifies and persists the exact Audit artifact and hands it to Planning.

Do not edit source, select final architecture, assign Build actions, issue acceptance or admission receipts, or rewrite Research evidence. Do not claim `PLANNER_READY` without actual source inspection evidence.
