# OneShot consolidated import prompt

## Goal

Safely extract the exact consolidated package and import its manifest-listed runtime files into the exact repository at `D:\OneShot`.

This is an additive package import. Preserve the existing repository, Git history, browser prototype, diagrams, planning files, review evidence, rollback material, and unrelated work.

This is not a repository structure migration, UI redesign, replacement build, cleanup task, or authorization to bypass release gates.

## Authoritative inputs

- Package: `D:\Temp\OneShot_Consolidated_Import_2026-10-11-final.zip`
- Checksum: `D:\Temp\OneShot_Consolidated_Import_2026-10-11-final.zip.sha256`
- Target: `D:\OneShot`
- Runtime source inside the package: `application/`
- Import tool: `tools/import_to_oneshot.ps1`
- Source manifest: `application/BUILD_MANIFEST.json`
- Acceptance state: `verification/acceptance.json` and `verification/ACCEPTANCE.md`
- Import contract: `IMPORT.md` and `provenance/IMPORT_PLAN.json`

Do not substitute another checkout, archive, extraction, or `.review` directory.

## Boundaries

- Copy only files listed in the application manifest and only through the supplied import tool.
- Do not copy the package root into `D:\OneShot`.
- Treat `docs/`, `provenance/`, `verification/`, `legacy/`, and `optional/` as support material, not runtime files.
- Do not install or activate `optional/winml-reference/`.
- Preserve `ui/`, `temp/`, `.review/`, `.rollback/`, existing diagrams, planning files, and unrelated modified or untracked files.
- Do not delete, move, reset, clean, stash, commit, push, deploy, or start external services unless separately approved.
- The only expected target overlap is `.gitignore`, whose imported version must preserve the reviewed union of existing and candidate rules.
- Treat any additional overlap as a conflict requiring review.
- Do not expose credentials in commands, logs, reports, browser output, or files.
- Do not claim live-model behavior, Docker runtime success, or production readiness without direct evidence from those paths.

## Phase 0: inspect and plan only

Before extracting or changing files:

1. Verify the package path, size, SHA-256, and checksum sidecar.
2. Inspect ZIP entries for absolute paths, parent traversal, links, duplicate destinations, device paths, and Windows case collisions.
3. Inspect the package manifest, import tool, import contract, and current acceptance state.
4. Inspect the exact target root, branch, HEAD, and modified or untracked paths without changing them.
5. Produce the complete manifest-controlled source-to-target file map.
6. Identify all overlaps, preserved paths, compatibility risks, acceptance gaps, and decisions requiring human input.
7. Define the rollback point and the verification attached to each implementation step.

Check the plan against:

- **Scope:** only the reviewed application import is included.
- **Project fit:** the supplied tool, manifest, contracts, and existing target are respected.
- **Decisions:** assumptions, conflicts, external dependencies, and unresolved choices are explicit.
- **Verification:** package identity, target preservation, compatibility, runtime behavior, and recovery are demonstrated at the appropriate evidence level.

End Phase 0 with:

`READY FOR IMPORT PLAN APPROVAL`

Wait for approval. Do not extract, copy, modify, delete, or run Apply during Phase 0.

## Decisions required before Apply

Request human direction when any of these is unresolved:

- Review-only extraction versus actual import into `D:\OneShot`.
- How the existing dirty worktree will be made clean. Do not alter it automatically.
- The exact reviewed target HEAD required by Apply.
- Any overlap beyond `.gitignore`.
- Approved System provider, model, credentials, data-transfer policy, and semantic acceptance evidence.
- Whether optional Agent-provider acceptance is required for the approved scope.
- Docker engine availability when Docker runtime evidence is required.
- Any incomplete C01-C15 journey or external acceptance gate.
- Any proposal to weaken or change the package's fail-closed import policy.

## Execution after approval

Perform each step independently. After each step, compare the result with the approved plan, correct safe in-scope gaps, rerun that step's verification, and continue only after it passes. Stop if a gap changes the approved file map, requires a product decision, weakens a safety gate, or risks existing work.

### Step 1: extract and verify in isolation

- Extract into a new uniquely named directory under `D:\Temp` only after every ZIP entry passes the safety review.
- Verify the ZIP checksum and every manifest-listed application's path, size, and hash.
- Confirm runtime, support, legacy, and optional material remain separated.

If identity or integrity fails, stop with `INTEGRITY FAILURE`. Do not repair or repackage the source silently.

### Step 2: preview the import

- Reconfirm the target resolves exactly to `D:\OneShot`.
- Reconfirm branch, HEAD, and worktree state.
- Run the supplied import tool without Apply.
- Compare the preview with the approved file map and manifest.
- Confirm preserved paths are not scheduled for deletion, movement, or overwrite.

If the worktree is dirty, HEAD differs, or the preview exceeds the approved map, stop with `NOT READY FOR IMPORT`. Do not clean the repository or bypass the check.

### Step 3: verify required acceptance gates

- Read the current acceptance manifest rather than relying on an earlier report.
- Run each required gate in its supported locked environment.
- Include applicable tests for invalid parameters, empty results, and compatibility with existing clients.
- Keep source checks, unit tests, HTTP integration, authenticated browser journeys, live-provider evaluation, and Docker runtime evidence separate.
- Record unavailable or skipped gates as incomplete.

A protocol responder, mock, evidence mode, static build, checksum, or hardware enumeration does not prove live-model semantics or deployment runtime.

Continue only when every gate required by the import policy is `OK` and the fail-closed release verifier agrees. Otherwise stop with `NOT READY FOR IMPORT` and name the exact missing evidence or decision.

### Step 4: apply the import

Run Apply only when:

- the target is exactly `D:\OneShot`;
- the worktree is clean;
- the operator-supplied expected HEAD matches;
- every required acceptance entry is `OK`;
- the manifest verifies completely; and
- the preview matches the approved import map.

Use the supplied import tool, not a broad recursive copy. It must create a rollback directory under `D:\Temp`, copy only manifest-listed application files, verify target hashes, preserve declared target content, and avoid commits, pushes, deployments, and deletions.

### Step 5: verify the imported target

- Confirm every imported target file matches its manifest hash.
- Confirm every preserved path still exists and was not changed by the import.
- Compare `git status` with the approved changed-file inventory.
- Run the required locked backend, frontend, contract, authenticated browser, persistence, Apply/readback, and backup/restore checks.
- Verify invalid requests, empty collection responses, authentication failures, source/version validation, and existing bearer-token clients where covered by the current contracts.
- Confirm the integrated service owns new runtime state and the preserved browser prototype is not an active fallback.
- Run the fail-closed release verifier and report its actual verdict.

If verification fails, stop further mutation. Report whether automatic rollback occurred. If recovery is needed, identify the exact rollback source and affected files; do not improvise destructive recovery.

## Compatibility requirements

- Keep the packaged frontend and FastAPI service as one release unit.
- Preserve protected routes, methods, status codes, validation behavior, and empty response shapes used by existing clients.
- Preserve explicit bearer-token behavior for non-browser clients and cookie/CSRF behavior for the browser client.
- Do not fabricate server provenance from legacy browser history.
- Do not introduce implicit provider fallback.
- Do not present an evidence packet as a semantic answer.

## Required report

Return:

- exact package, checksum, target root, branch, and HEAD;
- extraction and manifest verification results;
- complete source-to-target import map;
- preserved, added, updated, conflicted, and untouched paths;
- rollback location and coverage;
- exact verification commands, exit codes, and the evidence level each establishes;
- incomplete checks and the exact reason;
- the final release-verifier result.

Use one final verdict:

- `READY FOR IMPORT PLAN APPROVAL`
- `INTEGRITY FAILURE`
- `NOT READY FOR IMPORT`
- `IMPORTED — VERIFICATION INCOMPLETE`
- `IMPORTED — VERIFIED FOR THE APPROVED SCOPE`

Never report production readiness unless the full production acceptance contract, required live-provider evidence, and required deployment runtime evidence have passed.

## Success condition

Success means the exact reviewed package was safely extracted, only its manifest-listed runtime was imported into the exact `D:\OneShot` repository through the supplied tool, existing repository material was preserved, compatibility and recovery were verified, and the reported verdict matches the evidence.

Opening the ZIP, copying files, passing unit tests, or completing a build is not sufficient by itself.
