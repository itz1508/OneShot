# OneShot archive review and integration plan

Date: October 10, 2026. Status: proposal for review before extraction and implementation.

## Objective

Review both supplied packages independently, inspect every file and both patches, reconcile their behavior with the existing `D:\OneShot\ui`, and produce one compatible implementation with reproducible browser and service evidence. The outstanding market-gap fixes remain part of this work.

This planning preflight read ZIP contents directly in memory. It did not extract the packages, apply patches, install dependencies, execute their code, or change application source. The file inventory is [INTEGRATION-FILES-2026-10-10.csv](INTEGRATION-FILES-2026-10-10.csv). Full semantic review of every file is a planned execution stage, not a completed claim.

## Verified inputs

| Input | Observed contents | SHA-256 |
| --- | --- | --- |
| `OneShot_System_Working_Build_2026-10-10.zip` | 78 files; 77 manifest entries match; archive CRC check passed | `885a6ecc5ea22ec422b708c9e090c6e14036837f05b3556fea98c85543fbd935` |
| `OneShot_System_Generate_Stage_Corrected_2026-10-10.zip` | 69 files; 68 manifest entries match; archive CRC check passed | `a72eaa09f23c026d34da90abf3245146a218cb15a48638d5fde3d2aab630abf1` |
| `OneShot_System_Working_Build_2026-10-10.patch` | All 37 post-change hunks match its corresponding ZIP | `ea72a02f03126b207f12cebb20e6562e36c7218ffd2be9eda358659acb626182` |
| `OneShot_System_Generate_Stage_Correction_2026-10-10.patch` | All 10 post-change hunks match its corresponding ZIP | `7f0e832f017508a19db302093f646ccb5f156f2573f326503d3ce186a12b770a` |

Both ZIPs contain a top-level `OneShot/` directory. There are 79 unique relative file paths across them: 47 identical files, 21 shared paths with different bytes, 10 files unique to Working Build, and one file unique to Generate Stage (`BUILD_REPORT.md`). The manifest itself is the sole unlisted file in each archive. Integrity checks establish package consistency; they do not establish correct behavior or independently reproduce packaged test claims.

The Working Build's six generated frontend files match their source counterparts. Those outputs should be regenerated from accepted source during integration. The supplied patches are already represented in their corresponding ZIPs; they will serve as change evidence rather than being applied a second time.

## Current baseline and proposed direction

The current application is the native JavaScript UI under `ui/`, with IndexedDB persistence and a Node static server. The incoming packages contain a separate JavaScript frontend and a Python 3.11/FastAPI/Pydantic/SQLite System service. Their frontend is not a direct replacement for the current UI.

**Recommended direction:** retain the current four-zone UI and incorporate the reviewed System service behind it. Port useful incoming interaction logic into the existing UI. Use Working Build as the provisional backend candidate, with Generate Stage as an independent comparison and regression reference. Final file selection follows the complete review, not the archive names or timestamps.

The interrupted gap-fix work is present on disk but incomplete. For example, `ui/app.js` calls `fitPanels()` without a definition, and several new modules and controls are not fully wired. It must be reconciled and verified before it becomes the integration baseline. The prior source backup is `D:\OneShot\.rollback\market-gap-2026-10-09`; a new snapshot of the current partial work is required before implementation. No Git repository is currently present.

### Ownership to establish

| Responsibility | Proposed owner and compatibility requirement |
| --- | --- |
| Layout, panel state, review navigation | Existing `ui/`; preserve Agent, System, Sources, and Review, with temporary Process Display. |
| Persisted System messages, job admission, execution, artifacts | Reviewed Python service. Browser state must not report a server commit before the response and persisted state support it. |
| Working editor drafts and offline recovery | Browser may retain pending work; accepted server revisions require explicit identifiers and conflict handling. Define synchronization and recovery before enabling writes. |
| Original source bytes and prepared revision snapshots | Immutable originals plus explicit saved revisions. Every job must identify the version actually read. |
| Generation | Retain the explicit `PreparedInput → Systems.generate → validated artifact` boundary after verifying it. The Generate stage must consume already prepared input. |
| Background evaluation | Inspect terminal evidence and record its own evaluation. Confirm it cannot mutate the foreground job or launch a second generation workflow. |
| Packaging and serving | Build one selected UI asset directory and serve UI/API on the same origin through the reviewed service. Keep the existing static preview available during isolated development. |

These responsibilities follow the existing implementation boundaries. HTTP contracts will be checked against [OpenAPI](https://spec.openapis.org/oas/v3.1.1.html), backend validation against [Pydantic JSON Schema documentation](https://pydantic.dev/docs/validation/latest/concepts/json_schema/), and serving against [FastAPI static-file documentation](https://fastapi.tiangolo.com/tutorial/static-files/). Exact dependency versions and supported APIs must be resolved from the staged environment before locking them.

## Conflicts already identified

| Issue | Current build / incoming behavior | Reconciliation required |
| --- | --- | --- |
| IDs | Browser uses UUID strings with hyphens; incoming contracts require 32 lowercase hex characters. | Maintain an explicit local-to-server identity map; do not reinterpret existing IDs or silently lose associations. |
| Storage | Browser whole-workspace record versus server conversations, sources, drafts, jobs and artifacts. | Define authoritative fields and a restartable migration with counts and hashes, including unsaved drafts, notes, history and attachments. |
| Saved revision semantics | Current preparation uses saved working text. Incoming draft endpoints save separate draft rows; the Worker reads source bytes by source hash. | Add and prove the path from the user's selected saved revision to the admitted job. A successful draft save must not lead to processing an older original unintentionally. |
| Input limits | Current import accepts 10 MiB; incoming scanner allows 1,000,000 bytes, with narrower text extension support. | Establish one visible supported-capability contract. Existing larger/local sources must remain recoverable and receive an explicit admission result. |
| Instructions | Current System field stores notes. Incoming jobs require a persisted System objective message. | Distinguish notes from the submitted objective; retain the exact approved message and freeze its identity on admission. |
| Pre-send review | Incoming frontend extracts explicit headings and allows user review. | Port as an explicit optional review step; preserve original text, keyboard behavior, idempotency and uncertain-send recovery. Check parser parity between frontend and backend. |
| Run lifecycle | Local processing supports pause/resume/stop and partial results. Incoming frontend projects queued/running/completed/blocked/failed; no job pause/resume/cancel route was found in API inspection. | Reconcile actual state transitions and worker control. Preserve real control semantics; UI labels alone cannot supply missing server operations. |
| Database migration | Incoming `systems/store.py:31–62` performs DDL and `user_version` changes on an autocommit connection; it uses `executescript()` during setup/upgrades. | Repair migration atomicity and startup concurrency, then inject failures into initial setup and every supported upgrade. Prove rollback and retry before using retained data. |
| Final output | Incoming Generate documentation explicitly leaves physical `output.json` unresolved; it stores an artifact with kind/content/provider/limitations. | Trace the original output requirement and its consumer. Define and test the export mapping before changing artifact shape or adding an endpoint. |
| Capability coverage | Incoming default is an evidence packet. Image/PDF interpretation, retrieved web research and Agent replies remain unavailable. Model mode requires an explicitly configured HTTPS endpoint, model and token. | Report capabilities accurately and connect only an identified service with documented protocol and proven capability. Installing this archive alone does not close these market gaps. |

SQLite transaction behavior will be checked against the [Python 3.11 sqlite3 documentation](https://docs.python.org/3.11/library/sqlite3.html). The migration issue above is a source finding; failure-injection reproduction is part of the execution plan.

## Execution plan

### 1. Preserve and extract into isolated directories

- Snapshot the current `ui/`, including the partial fixes, and record hashes. Preserve the diagrams, `temp/`, existing audit artifacts, and the older rollback copy.
- Extract each ZIP into its own new directory below `D:\OneShot\.review\2026-10-10\`: `working-build/` and `generate-stage/`.
- Validate every member path before writing: resolved destination stays under its chosen directory; reject absolute/parent paths, duplicate or Windows-case-colliding names, links, and unexpected device paths.
- Recheck CRC and SHA-256 against the manifest after extraction. Keep the extracted inputs intact; use `candidate/` for reconciled work.

**Gate:** extraction identity proven, current baseline recoverable, no incoming package overlaid on `D:\OneShot\ui`.

### 2. Independent file-by-file review

For every path in the inventory, record its responsibility, actual callers/imports, state it owns, contract assumptions, limitations, defects, verification needs, and disposition: retain, adapt, rewrite, regenerate, or reference only.

Review all source files individually, including the 47 identical files. Verify both versions of changed files. Review generated files against their source/build path rather than maintaining duplicate code. Inspect tests for what they actually exercise, including mocks and skipped paths; treat reports as claims to reproduce.

Review order:

1. Runtime/package/dependency files, entrypoints, configuration, build/serve paths.
2. Contracts, file storage, database schema/migrations and authentication.
3. Source actions, revisions, job admission, idempotency, worker recovery and apply authorization.
4. Scanner/read/view, Advisor/readiness, context preparation, Generate/provider output, research tools.
5. Background evaluation and trace/event ordering, reconnection and ownership.
6. Both frontends, API client, pre-send review, editor, layout, persistence and accessibility.
7. Tests, backup/restore, smoke/E2E scripts, manifests and documentation.

**Deliverables:** complete review ledger, severity-ranked findings, accepted file map, and a contract/state compatibility map. Any unresolved material product choice is made explicit before its dependent rewrite.

### 3. Reconcile and rewrite the candidate

- Complete or correct the partial local gap fixes; preserve recoverable user work and verify a stable UI baseline.
- Repair accepted service defects first, including atomic migrations and revision/job ownership.
- Port reviewed message, source, draft, event and artifact interactions into the current UI through one API client.
- Implement identity mapping and a previewable, restartable migration. Preserve original hashes and retain an export of the browser workspace until restore is proven.
- Integrate authentic process events, independent Agent/System state, review restoration, stale-result indicators, attachment ownership, original access, backup/restore, readable source status, precise diff and keyboard controls.
- Resolve pause/resume/cancel and `output.json` at their real owning layer. Keep generation and background evaluation responsibilities distinct.
- Rebuild generated assets from accepted source and update the single run/install path and documentation.

**Gate:** each review finding and prior market gap has an implementation and a named verification case, or an explicit external prerequisite.

### 4. Verify through the real application

Use an isolated data directory and unused listener established from the current machine; isolate any Compose project and volumes from existing containers.

Required evidence:

- Fresh setup, upgrade, interrupted migration rollback/retry, and restart recovery.
- Login, session expiry, CSRF rejection and sanitized failures.
- All five source operations; removal/deletion authority; immutable originals; saved revisions and stale-version rejection.
- Message/job idempotency after uncertain responses and repeated clicks.
- Selected sources plus approved objective → actual Scan/Read/Prepare/Generate → validated artifact → review → explicit handoff/export.
- Pause/resume/cancel, partial/blocked/failed paths, reconnect/event replay and preserved editor state.
- Two-tab writes, draft/attachment ownership, stale-result indicators, complete backup/restore and malformed-backup rejection.
- Post-change desktop, narrow, short and resized layouts; keyboard focus, dialogs and progress state. Capture screenshots.
- Model execution only against a configured real provider. Evidence-mode tests and mocked provider tests are reported separately.
- Fresh installation from the final archive and byte-for-byte manifest verification. Container runtime proof is required if Compose is included in delivery.

### 5. Apply the verified candidate

Promote the reviewed files to the active build using an explicit changed-file manifest and a rollback checkpoint. Preserve original packages and review evidence. Deliver the file-by-file ledger, compatibility decisions, final verification report, and reproducible package/checksum.

## Planning checkpoint

The user's instruction is to provide planning before execution. This turn therefore ends with this plan and the preliminary inventory. Extraction, full semantic file review, rewriting, migration and application begin after the plan is accepted. Provider configuration and any genuinely unresolved output-contract decision remain explicit prerequisites for their respective verification gates.
