# OneShot Audit — Capability Guidance

**Purpose:** Audit is a selectable capability inside the existing Research entry point. It is **not** a second workflow system and does **not** rename or replace `research` / `oneshot_research`.

## Intake

User selects **Research → Audit** and provides a question or audit scope. Preserve exact accepted intent, source identities, permitted roots, acceptance criteria, and limitations. The host must authorize repository access. Do not treat user-supplied paths as granted permissions.

## Discovery responsibilities

Inspect source and contracts, implementation completeness, imports and paths, API/tool/event wiring, safety boundaries, dependencies, persistence, concurrency and recovery, verification fixtures, and actual E2E outcomes. Distinguish verified observations from candidate vulnerabilities and missing runtime evidence. Reconcile against existing findings before opening new ones.

## Capability modules

- `paths.py`: symlink containment and broken paths.
- `wiring.py`: literal API route cross-checks; dynamic routes are not proof of failure.
- `security.py`: security-sensitive command invocation candidates; not vulnerability certification.
- `contracts.py`: local Python module reference checks.
- `completeness.py`: explicit incomplete-source comment markers.
- `verification.py`: test-surface discovery; test presence does not demonstrate execution.
- `frontend.py`: source-backed Research endpoint, artifact viewer, and status wiring gaps.
- `state.py`: host stage receipt identity binding inspection.
- `dependencies.py`: dependency lockfile reproducibility checks.
- `integration.py`: Audit-mode selection and Research-host invocation boundary.
- `recovery.py`: process-local admission and explicit recovery requirements.

`__main__.py` dispatches the read-only capability checks and emits JSON. `core.py` normalizes immutable source observations, evidence digests, and scope limitations. New checks belong in separate named capability files, not in the CLI.

## Workflow boundary

Audit returns findings to the **existing** Host workflow. Research establishes evidence; Audit Discovery inspects implementation; Planner selects any repair; Scanner/Fixture Validation and Build Admission gate it; Builder performs admitted changes; independent E2E verifies acceptance. Auditor never issues host receipts, advances stages, writes code, or claims acceptance from its own static observations.

## Finding semantics

Every observation must bind capability, code, severity, relative path/line, source digest where available, and a clear limitation. `candidate` is not `verified_observation`; neither is an E2E pass. A skipped scanner is `blocked`. No findings means `not_e2e_verified`, **never READY**. The Host owns TODO mapping, deduplication, corrections, receipts, and termination of retry loops.

## Example

```bash
python -m agent.audit --root /absolute/authorized/repo --scope . --request "Inspect integration completeness"
```

The CLI intentionally performs no shell commands, network calls, or source writes. Connected E2E requires separately authorized host execution and independent evidence.

## Integration limitations

The Research UI selects Audit and dispatches through the host, which persists findings with work records. Connected browser tests are defined in the workflow but are not evidence of success until their CI run passes; remote deployment remains unverified. The static CLI performs read-only observations only. Audit checks cover recognized source patterns, not all languages, dynamic call graphs, or complete vulnerability assessment. Its `audit-report.json` output from the repository audit workflow is evidence for review, not an acceptance receipt.
