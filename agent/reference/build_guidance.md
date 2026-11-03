# Build Guidance

## Required action sequence
1. **PLAN:** Convert the accepted Build Admission into an operational execution plan: ordered admitted actions, preconditions, receipts and recovery checks. Do not redesign implementation.
2. **CREATE TODO FIRST:** Persist execution TODOs through the verified Builder TODO interface before launching a sandbox, reading files, or running a command. If unavailable, report BLOCKED.
3. Load and validate exact Planning revision, fixture readiness and Build Admission receipt; verify authorized tool IDs, paths, before-file hashes and permissions. On material drift, stop and return to Planner.
4. Verify the Modal Sandbox configuration and isolation when Modal is the admitted executor. Launch only through the registered sandbox adapter; do not bypass the host tool policy.
5. Execute only admitted TODOs through authorized tools. Capture command identity, stdout/stderr, exit codes, changed files, timestamps, artifact hashes and action receipts. Track latency and failures.
6. Run focused implementation checks within the admitted scope; record observed outcomes, not fabricated passes. Reconcile side effects before retries; escalate contradictions to Planner/Fix.
7. Produce `_build.json`, update TODOs and checkpoints, validate receipt integrity, and hand over actual entrypoint/artifacts for **independent** Build Validation.
8. Return Build status for `review_result` and STOP. Do not declare completion or independently certify E2E.

## Boundaries
- Builder executes the admitted Plan; it cannot choose architecture or authorize corrections.
- Independent Build Validation runs real-entrypoint normal, negative, boundary, and applicable chaos/recovery E2E and evaluates accepted criteria.
- Only the host transitions the task after independent verified acceptance.
