# Repository Instructions

## Phase Context Requirements

For each approved implementation phase, maintain one phase-specific context file:

`harness/context/phase-<NN>-<phase-slug>-context.md`

Create the context file only when the phase begins and after any required approval. Before recording new context, read the applicable repository instructions, goal, prompt, build file, prior context, and build-log evidence.

### Materiality Test

Record information only when omitting it could reasonably:

- Change the approved scope or implementation approach
- Cause a future phase to repeat discovery or make a different decision
- Affect an interface, dependency, invariant, or ownership boundary
- Change acceptance criteria or required verification
- Affect security, privacy, reliability, observability, rollback, or recovery
- Hide a blocker, unresolved assumption, accepted limitation, or required follow-up

If information would not affect future work, verification, operations, or decision-making, do not add it.

### Capture

Record material user decisions, scope changes, explicit non-goals, influential assumptions, architectural decisions and rationale, component and ownership boundaries, preserved invariants, operational constraints, unavailable evidence, blockers, unresolved questions, downstream findings, and superseded decisions. Include provenance by referencing the relevant file, command, test result, issue, review finding, or user decision.

### Exclude

Do not use context files as transcripts, scratchpads, or progress logs. Exclude routine output, step-by-step narration, immaterial dead ends, facts already owned by canonical files, copied plans or source, routine status, speculation presented as fact, and credentials or sensitive values. Link to canonical sources instead of duplicating them.

### Source-of-Truth Boundaries

- The phase build file owns approved scope, non-goals, acceptance criteria, and planned verification.
- The phase context file owns material discoveries, decisions, constraints, and unresolved matters needed by future work.
- `harness/build-log.md` owns implementation progress and observed verification evidence.
- Code-review artifacts own review findings and sign-off status.

Do not copy information between these files unless a short summary is necessary to explain a material decision.

### Update and Handoff

Update the context file when a material decision or discovery occurs and review it before closing the phase. Before handoff:

1. Remove non-material narration and duplicated information.
2. Confirm that material decisions include rationale and provenance.
3. Mark assumptions and unresolved questions explicitly.
4. Confirm that evidence is linked rather than claimed without support.
5. Record downstream implications for later phases.
6. Do not mark the phase complete solely because the context file is complete.
