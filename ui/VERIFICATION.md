# OneShot UI verification

> **Current behavior update:** [Behavior expansion and verification](BEHAVIOR-EXPANSION.md) covers the October 9 source-action and requested-task changes from `mermaid-diagram (2).png` and `mermaid-diagram (3).png`. The evidence below describes the initial UI. Its seven-source seed and always-partial local outcome have been superseded by nine references and task-specific coverage. Original browser scripts below are historical; use the expansion scripts for the current behavior.

Final review: October 9, 2026. Target: `D:\OneShot\ui`.

## Verified scope

The local UI is implemented and was exercised in Chromium through Playwright CLI against the running Node server at `http://127.0.0.1:4173`.

This evidence covers browser source handling and local preparation. It does not establish connected-agent behavior, semantic summarization, production deployment, backend integration, or container readiness.

## Screenshots inspected

| View | Evidence |
| --- | --- |
| Desktop, all four zones, supplied workflow diagram | [Desktop](output/playwright/desktop-final.png) |
| Dark theme, four zones | [Dark desktop](output/playwright/dark-final.png) |
| Mobile source selection | [Mobile sources](output/playwright/mobile-sources-final.png) |
| Mobile review of the supplied transition diagram | [Mobile review](output/playwright/mobile-review-final.png) |
| Real preparation of architecture text and both PNGs | [Mobile result and findings](output/playwright/mobile-processing-final.png) |
| Original versus working revision | [Diff review](output/playwright/diff-review.png) |

Final screenshots use reduced motion to avoid capturing intermediate color transitions. All final images listed above were generated from the running application. The first five contain the supplied reference sources rather than invented conversation or processing data.

## Browser flows

### Desktop editing and preparation — passed

Playback: [verify-desktop.js](output/playwright/verify-desktop.js). Nineteen assertions completed.

- Four visible product zones at 1536 × 960; seven supplied reference files loaded.
- The workflow PNG decoded at its original width of 3,112 pixels; expanded image view opened and closed.
- A new text source was created through the Add Source form and selected as the processing scope.
- An unsaved revision was made. Cursor selection and editor scroll were recorded before Start.
- Start replaced the detail slot with real local processing. Agent and System draft text survived.
- Local processing reported partial coverage, and another Start remained disabled until acknowledgment.
- Return to Review restored the exact working text, cursor selection, and scroll.
- Diff Review displayed the actual changed text. Save persisted the revision across reload.
- The prepared report excluded the unsaved sentinel, proving use of the saved snapshot.
- History retained the operation, and command search opened the second supplied PNG.
- Desktop document width did not overflow its viewport.

### Mobile processing controls — passed

Playback: [verify-mobile-processing.js](output/playwright/verify-mobile-processing.js). Twelve assertions completed.

- Eight actual text files were imported for a workload long enough to exercise controls.
- Pause reached an acknowledged checkpoint and no further reads occurred while paused.
- Agent Chat remained usable while paused and after Resume. Incoming events did not override mobile navigation.
- The chat draft survived completion. Stop finalized a second paused operation.
- A PDF-only scope reported failed, with the unavailable extractor identified before acknowledgment.
- Source search filtered the real tree. A single product zone was visible at 390 × 844 without document overflow.
- Theme switching worked, and reduced motion suppressed process animation.

### Folder import and failure recovery — passed

Playback: [verify-recovery.js](output/playwright/verify-recovery.js). Ten assertions were reached through the final mobile screenshot.

- Directory selection preserved `fixtures/nested/folder-note.md`.
- Download used the source name. The downloaded bytes matched the fixture by SHA-256: `20958983EF44E28B63491AF4472C6C1038298D688496A65AF6CA333C7C78AAF4`.
- Reload during a confirmed pause recorded an interrupted run. It did not fabricate completion.
- A browser-side injected IndexedDB read failure caused zero default-data writes and disabled mutation controls.
- Retry recovered the existing 18-source verification workspace. The stored state contained one interrupted run and no active run.
- Dark foreground color was verified from computed style.
- At 1180 × 850, the auxiliary System panel collapsed and could be reopened.
- Mobile source navigation remained available after desktop panel changes.

The CLI returned early when the browser displayed its before-unload dialog; execution continued after acknowledgment. Final screenshot creation and an independent read of stored state confirmed the recovery flow reached its last assertions. An earlier attempt began on `about:blank`, timed out before interacting with the app, and was rerun after navigating to the local URL.

### Fresh reference workspace — passed

Playback: [capture-preview.js](output/playwright/capture-preview.js), in a separate browser session.

- Seven reference sources loaded.
- The default selection processed Architecture.md and both actual PNGs.
- Three sources were inspected; the text yielded 892 characters, and image dimensions were decoded.
- The result correctly identified unavailable semantic summary, visual interpretation, and research.
- Findings and Return to Review were visible before the detailed event history.
- The browser console reported zero errors and zero warnings.

## Source and syntax checks

- `npm run check` passed for the application, processor, storage module, and server.
- SHA-256 comparisons confirmed that all seven bundled references match the supplied files byte for byte.
- Original `Architecture.md` and both PNGs remain in the workspace root; new implementation files are under `ui/`.
- No frontend bundling step is necessary: the browser loads the native JavaScript modules and CSS directly.

## Known boundaries

- Model-dependent capabilities remain disconnected and are identified in the UI and prepared reports.
- Browser storage is local to its browser profile and origin. It is not a server backup or shared multiuser workspace.
- Recovery records the last committed checkpoint; a sudden crash may lose later events.
- PNGs are viewed as supplied images. DOT/Mermaid text can be inspected and edited; arbitrary diagram source is not compiled into a new diagram.
- Simple Markdown preview and bounded changed-block diffs are implemented. Full document-format rendering and PDF extraction are not implemented.
- Verification was performed in Chromium. Other browsers and assistive technologies were not separately certified.

To replay the CLI scripts, use a fresh verification browser profile and run the desktop, mobile-processing, and recovery scripts in that order. The later scripts intentionally reuse sources created by the earlier flows. Verification fixture sources live in that automation profile; the shipped initial workspace contains only the seven supplied references.
