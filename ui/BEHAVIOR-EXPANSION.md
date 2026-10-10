# Source actions and requested tasks

Implemented October 9, 2026 in `D:\OneShot\ui`, following:

- `D:\OneShot\mermaid-diagram (2).png` — requested source action and applicable source state.
- `D:\OneShot\mermaid-diagram (3).png` — responsibility, operation acceptance, task output, coverage, trace, and return to review.

The original four product zones remain. Process Display uses the existing detail slot while actual work is active. The two new PNGs are also available in the source tree. Existing browser workspaces receive them once, without resetting source IDs, edits, chat drafts, or review selection.

## Source actions

| Diagram operation | UI | Implemented behavior |
| --- | --- | --- |
| `INPUT_SOURCE` | Add source → Input text | Creates a local text source and records its input origin. |
| `ADD_SOURCE` | Library / Add source → Existing → Include | Includes the retained source by ID, with the same original, saved revision, and working draft. |
| `IMPORT_SOURCE` | Add source → Import → Files / Folder, or file drop | Copies selected files into browser storage and preserves folder paths. |
| `REFERENCE_SOURCE` | Add source → Reference | Saves an HTTP/HTTPS address without copying, fetching, or verifying the linked content. Embedded credentials and other URL schemes are rejected. Opening the external website is a separate user action. |
| `REMOVE_SOURCE` | Remove selected from scope | Removes membership and processing selection. Source content and drafts remain in the library, including the currently open editor. |
| Underlying deletion | Other source request → Delete underlying content | Reports rejection in review because separate deletion authority is unavailable. It does not invoke scope removal. |
| Unknown request | Other source request → Other / unresolved action | Reports the unresolved request in review and records the rejection. |

Management operations record acceptance, real staging work, storage, and the committed outcome. Candidate source changes are applied to the visible workspace only after the IndexedDB transaction succeeds. Failed writes keep the preceding source membership and working drafts. Successful changes return to the previous review context.

## Requested tasks and coverage

The selected task specifies what coverage means. No natural-language intent classifier or model is claimed.

| Requested task | Responsibility and output | Outcome |
| --- | --- | --- |
| Inventory sources | Source inspection: file types, saved sizes, paths, reference addresses | Completed when metadata for all selected sources is available. No content reading is claimed. |
| Inspect local contents | Source inspection: readable text excerpts and decoded image dimensions; mixed sets are identified | Completed for fully supported local scope; partial when content is omitted or some sources cannot be inspected; failed when none yield usable output. |
| Extract text | Source inspection: UTF-8 text excerpts | Same coverage rules. Image OCR and PDF extraction are unavailable. |
| Understand and summarize | Semantic source inspection | Rejected before starting: processing service is unconnected. |
| Research with evidence | Research | Rejected before starting: browser research is unconnected. A stored reference alone is not evidence of fetched content. |

The processor freezes the saved source revisions and requested task at acceptance. Source controls and task selection are locked during a run. Real reads still support checkpoint pause, resume, and stop.

Completed tasks automatically restore review, with a persistent outcome notice and a link to the separate output. Partial and failed inspections retain findings until acknowledgment, then restore review. Rejected requests appear in review without opening Process Display or creating an output. Every outcome remains in Activity History under its actual action, task, and responsibility.

## Browser verification

Chromium, desktop 1536 × 960 and mobile 390 × 844, against the real local server.

- [Main expansion flow](output/playwright/verify-expansion.js): **27 assertions passed**, including all source-state behavior except the separate file chooser flow, all three coverage outcomes, unavailable/unknown/deletion rejection, zero automatic reference requests, saved-snapshot processing, editor selection recovery, failed-write rollback, persistence, and mobile overflow.
- [Import and active-operation flow](output/playwright/verify-expansion-import.js): **7 assertions passed**, including file chooser import origin, draft preservation, scope/task locking, real pause/resume, independent mobile navigation, explicit excerpt truncation, action/responsibility history, and unsafe URL rejection.
- [Existing-workspace upgrade](output/playwright/verify-expansion-upgrade.js): an existing seven-source workspace became nine sources. All seven existing IDs, paths, original/saved/draft text, the selected review, and both chat drafts were preserved. Exactly two new diagram references were present.
- `npm run check` passed. The expansion browser session reported zero console errors and warnings.

The first main-flow attempt stopped because its verification locator used the textbox role for a search input. The locator was corrected to searchbox and the complete flow passed in a fresh browser profile. The storage-failure test deliberately throws during the candidate membership write; it confirmed retained source state rather than treating that injected failure as a successful operation.

Replay the main flow in a fresh CLI browser profile, then the import flow in the same profile. The upgrade flow runs against an existing preview profile and refuses to reload an active operation. The older scripts in `VERIFICATION.md` describe the initial UI and are not current acceptance gates.

## Screenshots

- [Upgraded existing workspace](output/playwright/expansion-upgraded-preview.png)
- [Desktop with requested tasks](output/playwright/expansion-desktop.png)
- [Mobile source scope and task selection](output/playwright/expansion-mobile.png)
- [Reference action dialog](output/playwright/expansion-reference-dialog.png)
- [Actual partial inspection and findings](output/playwright/expansion-partial.png)

## Technical references and limits

- [W3C File API](https://www.w3.org/TR/FileAPI/): selected files and immutable source Blobs underpin local import and retention.
- [IndexedDB specification](https://www.w3.org/TR/IndexedDB/): source state is committed in a local storage transaction; success is shown after transaction completion.
- [WHATWG URL Standard](https://url.spec.whatwg.org/): reference addresses are parsed with the browser URL implementation and constrained to HTTP/HTTPS.
- [W3C dialog guidance](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/): source management uses a named native dialog with keyboard dismissal and separate action choices.

These are local browser operations. Model replies, semantic understanding, remote research, external deletion, shared multiuser state, and production deployment remain unimplemented. Coverage is limited to the chosen task. No backend or AI end-to-end readiness is inferred from the browser checks.
