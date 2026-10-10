# OneShot — market design and functional gap review

Reviewed October 9, 2026 (America/Los_Angeles).

## Assessment

The current UI provides real local source intake, revision editing, and bounded extraction. It still falls short of the full behavior in the supplied diagrams and has three urgent defects: saved work can be overwritten by another tab, primary source actions disappear on shorter screens, and panel resizing can push Review offscreen.

The visual direction is coherent. The main design problem is how space and attention are allocated: the disconnected Agent welcome occupies a large area while the functioning source workflow is squeezed into a narrow column. More decorative features would not resolve these gaps.

This review covers `D:\OneShot\ui`, served at `http://127.0.0.1:4173`, and the original `mermaid-diagram (2).png` and `mermaid-diagram (3).png`. Evidence combines source inspection, fresh Chromium interactions, computed styles, and current product/specification references. The older deleted backend and separate `temp` material do not establish capabilities in this app. Application source files were not changed during this audit.

Priority: **P1** = fix before relying on the workspace for daily work; **P2** = functional/accessibility gap to address next; **P3** = productivity improvement. “Browser” means reproduced in this review; “source” means confirmed by code inspection without a dedicated browser reproduction.

## Market comparison

These references establish relevant interaction patterns; they do not require copying another product's layout or replacing the user's four independent zones.

| Responsibility | Market evidence | OneShot gap / action |
| --- | --- | --- |
| Sources → answer → evidence | Google's [chat documentation](https://support.google.com/gemininotebook/answer/16179559?hl=en) describes selected source scope and citations that navigate to supporting content. The inspected [Gemini Notebook screen](https://mobbin.com/screens/05def46a-970f-46b2-8bf0-e0e83c7dd49e) presents sources, cited chat, and a note together. | Selection exists. There is no connected answer workflow or clickable passage provenance. Make a prepared output traceable to the exact source version and passage. |
| Conversation beside a focused work product | The inspected [Claude screen](https://mobbin.com/screens/885e249d-6fe3-4461-9e87-7f743f6fbd36) gives the artifact most of the working area while keeping chat visible. [Claude's artifact documentation](https://support.claude.com/en/articles/17153992-what-are-artifacts-and-how-do-i-use-them) describes editing, version access, and export. | OneShot has review/edit/download, but the default source tree is tiny and the editor has a coarse diff. Offer a focused working layout while retaining independent zone state. |
| Research evidence review | The inspected [ChatGPT sources screen](https://mobbin.com/screens/88d5e839-cf2b-447b-887c-a4beeead8040) gives research sources a dedicated review surface beside the answer. Google's [source documentation](https://support.google.com/gemininotebook/answer/16215270?hl=en) describes web discovery and importing selected results. | References are bookmarks only; research is explicitly unavailable. A future research action needs reviewed sources, supporting passages, and visible coverage limits. |
| Adaptable workbench | [VS Code's layout documentation](https://code.visualstudio.com/docs/configure/custom-layout) describes visibility controls, focus/maximize modes, editor groups, and resizing. | OneShot already has collapse/resize controls, but resizing clips Review and desktop button state contradicts visibility. Make the existing controls dependable first. |
| Accessible everyday use | [W3C reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html), [contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html), and [modal dialog guidance](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/) supply concrete criteria. The [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md) were fetched for this review. | Clipped actions, focus loss, unnamed dialogs, and insufficient light-theme contrast are present. This is a targeted audit, not a complete WCAG certification. |

Mobbin observations above are limited to the returned screenshots, which were visually inspected. Product behavior claims use the linked official documentation.

## P1 — reproduced defects

### F1. Another tab silently removes saved work

**Location:** `ui/lib/storage.js:49`, `ui/lib/storage.js:56`, `ui/app.js:447`. **Evidence: browser + source.**

Opened two tabs sharing the same browser workspace. Tab A created `market-audit-saved.txt`; the database contained 10 sources and the UI reported saved. Typing an unrelated agent draft in Tab B replaced storage with its older 9-source workspace. Reloading Tab A lost the new source. Both tabs had reported successful saves.

The queue is local to each tab and each write stores the entire in-memory workspace under the same key. Atomic transactions do not reconcile stale snapshots. Coordinate ownership or reject conflicting writes before replacing persisted work. A lock around the existing stale write alone would not fix the lost update. The relevant responsibilities are documented in [IndexedDB](https://www.w3.org/TR/IndexedDB/) and the [Web Locks editor coordination example](https://www.w3.org/TR/web-locks/#motivating-use-cases).

**Acceptance:** edits from two tabs survive reload, or the later writer receives a clear conflict/recovery choice before any saved work is replaced.

### D1. Start and Add source are clipped on shorter screens

**Location:** `ui/styles.css:6`, `ui/styles.css:9`, `ui/styles.css:16`, `ui/styles.css:22`. **Evidence: browser + screenshots.**

| Viewport | Observed source actions |
| --- | --- |
| 1440 × 900 | Visible at the default layout. |
| 390 × 844 | Start and Add source visible. |
| 1280 × 600 | Start begins at y=761.7; Add source at y=815.7, below the 600px viewport. |
| 320 × 640 | Start begins at y=614 behind the footer; Add source at y=691 outside the viewport. |
| 800 × 450 | Start begins at y=593; Add source at y=652.5 outside the viewport. |

The body/workbench clip overflow while Sources retains fixed controls and a minimum tree height. A follow-up wheel attempt at 320 × 640 left the page, workbench, and source-panel scroll positions at zero. Checking only document horizontal overflow had missed this defect.

**Acceptance:** all source controls remain reachable at narrow and short viewports; the source area scrolls appropriately while its primary action remains discoverable. Check equivalent zoomed layouts against [W3C reflow guidance](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html).

Evidence: [320 × 640](output/playwright/gap-320x640.png), [1280 × 600](output/playwright/gap-1280x600.png), [800 × 450](output/playwright/gap-800x450.png).

### D2. Resizing pushes Review beyond the window

**Location:** `ui/app.js:439`, `ui/styles.css:9`. **Evidence: browser + screenshot.**

At 1440px wide, keyboard resizing allowed Agent=600px and Sources=450px. Review started at x=1326 and ended at x=1646; 206px were clipped. Its right-side actions were outside the visible workbench. The document still reported a width of 1440, so a simple horizontal-overflow assertion passed.

**Acceptance:** resize limits account for the space needed by every visible panel. Review and its toolbar remain reachable throughout supported resize combinations. [Screenshot](output/playwright/gap-resize.png).

## P2 — interaction and functional gaps

| ID | Location / evidence | Finding | Required outcome |
| --- | --- | --- | --- |
| D3 | `ui/app.js:81`, `ui/app.js:382` — browser | Pressing Space on a source checkbox removed its focused DOM node. Focus became BODY; the next Tab returned to the earlier Design folder checkbox. | Keep focus on the affected control after selection and folder updates. |
| D4 | `ui/app.js:55`, `ui/app.js:60` — browser | Clicking Agent on desktop hid the panel while its button remained `aria-pressed=true` and highlighted. | Desktop visibility controls reflect visible panels; mobile navigation reflects the active view. |
| F2 | `ui/app.js:181`, `ui/app.js:326`; `ui/lib/processing.js:164` — browser | After extracting “delivery date is Monday,” saving “delivery date is Friday” left the source marked completed and the old output available without a changed-source indicator. Historical snapshots are valid, but their relation to current revisions is unclear. | Retain historical output, identify its source version, and mark when current sources have changed. Re-preparation should be a direct action. |
| F3 | `ui/app.js:375`, `ui/app.js:413` — browser | Attaching an output then saving a draft stored only text/time on the saved note. The attachment stayed as one workspace-level ID and its banner remained on the emptied composer. | Each saved draft retains its own attachment association; the composer can detach/replace it explicitly. |
| D5 | `ui/styles.css:4`, `ui/styles.css:6`, `ui/styles.css:12` — computed browser styles | Light-theme status text is 10px with 4.44:1 contrast; 12px composer placeholder text at opacity .85 is 3.58:1. Both are below the normal-text 4.5:1 threshold. | Adjust actual foreground/background/opacity combinations and verify both themes. See [W3C contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html). |
| D6 | `ui/index.html:69` — history reproduced, other dialogs source; `ui/app.js:360`; `ui/index.html:57` | History, command, help and image dialogs lack accessible names. Source filters expose no pressed/selected state. Running progress lacks useful progress/log semantics; only terminal outcomes receive announcements. | Name dialogs, expose filter state, and announce meaningful run-state changes without reading every chunk event. Follow [dialog guidance](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/) and [Web Interface Guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md). |
| F4 | `ui/app.js:188`, `ui/app.js:392` — source | Original text bytes remain stored, but the only download action exports the working draft. There is no original download/restore action. UI09 requires originals to remain available. | Give users explicit access to original bytes and a recoverable revision history. |
| F5 | `ui/lib/storage.js:40`, `ui/app.js:392`, `ui/app.js:423` — source | There is no complete workspace export/import. File download and activity JSON cannot restore notes, sources, revisions and scope together. | Provide a verified backup/restore flow. The existing browser-storage warning is accurate; browser persistence is subject to [storage and eviction behavior](https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria). |
| F6 | `ui/index.html:34`, `ui/app.js:414`, `ui/app.js:332` — source | The field named “Preparation instruction” only saves a note. Its content is not passed into preparation. | Clearly identify notes as notes, or show which instruction is applied to a run and retain it with the result. |
| D7 | `ui/app.js:176`, `ui/app.js:417` — source | The message says to pause or finish before opening a source, but the same guard also blocks opening while paused. | Align the message and allowed transition with the intended pause behavior. |

F2/F3 evidence: [result and attachment screenshot](output/playwright/gap-stale-output.png), [follow-up measurements](output/playwright/gap-followup-evidence.json).

## Product capabilities missing from the intended behavior

These are capability gaps against the diagrams and comparison products. The current app discloses its local limits; this audit found no reason to label its unavailable-service rejection as fabricated execution.

| Diagram responsibility | Current implementation | Remaining product work |
| --- | --- | --- |
| Source management: input/include/import/reference/remove | All five have local handlers. New text creation was exercised in this audit. Remove retains the source; references retain a URL without fetching it. | Fix saved-work reliability and complete recovery. External content ingestion beyond selected local files is absent. |
| Separate deletion authority; unknown action | Explicit rejection paths exist. | Preserve this authority boundary; deletion is not a prerequisite for completing scope removal. |
| Text understanding | UTF-8 reading and excerpts, up to 4,000 characters per source. Summarization is unavailable. | Semantic output that uses the requested instructions and links its claims to source passages. |
| Visual inspection | Image display and dimensions. | Interpretation of image content and traceable findings when that capability is connected. |
| Files/folders and mixed inspection | Metadata inventory, text excerpts, image dimensions, and unsupported-format findings. PDF extraction is unavailable. | Supported document extraction and a coherent result across content types, with source-specific failure/retry handling. |
| Research when needed | URL references and an unavailable research task; rejection behavior confirmed in source. | Research execution, source review, evidence links, and freshness information. |
| Quality/coverage → sufficient / incomplete / unusable | Coverage is assessed against bounded local reading. It does not assess semantic sufficiency for the user's requested work. | Quality checks appropriate to the requested task; source reading alone cannot establish understanding. |
| Prepared context → independent Agent | Local text drafts and one attachment pointer; no agent reply path. | Repair draft ownership, then prove a connected handoff while preserving the user-controlled separation. |
| Process Display → terminal outcome → Review/Trace | Real local lifecycle and event history are present. A short extraction completed and returned to Review in this audit. | Accessible ongoing state, useful recovery/retry, and equivalent evidence for connected processing once added. |

The missing service is a major product gap. Selecting a framework or provider is a separate decision requiring an explicit contract and authoritative provider documentation; this review does not invent that choice.

## Design improvements after the urgent defects

1. **Give source work more usable space.** At 1440 × 900 the default tree is a small scrolling strip between management controls, outputs and task configuration. Reduce persistent secondary controls, enlarge working text, and provide a focused Sources/Review mode while keeping all four zones available. [Current desktop](output/playwright/gap-desktop.png).
2. **Use one consistent panel visibility model.** Top views, the rail, collapse icons and source-open behavior currently overlap. Clarify which control opens, focuses or hides a panel.
3. **Make status readable without hovering.** The source state is a small dot with a title; the file button's accessible name only says “Open filename.” Display a meaningful label and include status in its accessible description.
4. **Make Diff review precise (P3).** `ui/app.js:130` treats the entire middle between first/last changed lines as one replacement block, capped at 1,000 lines per side. Add individual change groups, line positions and change navigation before presenting it as a substantial review tool.
5. **Finish command-menu behavior (P3).** `ui/app.js:431` supports Tab and Enter but has no arrow-key result selection. Match the interaction expectations created by the command-palette presentation.

## Recommended order and acceptance gates

1. **Protect saved work:** F1 first, followed by original access and complete workspace recovery. Prove two-tab edits and recovery from an exported workspace.
2. **Make controls reachable:** D1–D4, then contrast and accessible state. Verify short/narrow screens, maximum panel widths, keyboard focus and actual hit targets; checking `scrollWidth` alone is insufficient.
3. **Make context ownership explicit:** F2/F3/F6. Save two distinct drafts with different outputs, revise a source, and prove each retained association and revision status after reload.
4. **Complete one connected user task:** start with a selected source plus instruction, perform actual processing, review evidence and limitations, and explicitly attach the result. Then expand content types/research. Success should be demonstrated through the actual UI and service, including failure and cancellation.
5. **Improve density and productivity:** focus mode, precise diff and richer commands after the above gates pass.

## Evidence and limits

- Fresh Chromium sessions: `oneshot-gap-v3` and `oneshot-gap-followup`; isolated audit data shared only between the two tabs used for the overwrite reproduction.
- Reproduction scripts: [layout/storage/keyboard](output/playwright/audit-market.js), [revision/attachment/accessibility](output/playwright/audit-market-followup.js).
- Captured results: [runtime JSON](output/playwright/gap-runtime-evidence.json), [follow-up JSON](output/playwright/gap-followup-evidence.json). Raw CLI records are beside these files. UTC timestamps fall on October 10; the local review date is October 9.
- Initial harness attempts needed a corrected source-field locator and explicit clearing of the indeterminate source selection. The linked final runs completed successfully as audit scripts and reproduced the defects; they are not passing product acceptance tests.
- This review exercised input creation, extraction, revision save, draft attachment, summary rejection, reload, two-tab writes, keyboard selection, dialogs and responsive/resized layouts. It did not rerun every earlier import/pause/stop scenario or test Firefox, Safari, real mobile devices, a screen reader, large collections, or any connected provider. Screenshot comparison is not proof of those capabilities.
- Source hashes below identify the reviewed implementation. No application code was repaired in this audit.

| File | SHA-256 |
| --- | --- |
| `app.js` | `E00E76EC089AE5AA6E3D002979FDB347210157EDDBA134F86A28DC3324CC8166` |
| `index.html` | `36C5E697036265FB61D53854D61FD1115DC1155B942C3C194B160B4997319B1E` |
| `styles.css` | `62AC6BC144D31236DE764509518EB6258249EDDEA0C4274C011FD82B677EB3A9` |
| `lib/storage.js` | `65F740131BEFDA37081DD4E0F4358477D9F1B2AB016CFF51BA08306FD39B8DDB` |
| `lib/processing.js` | `DDF2D624D092290EF6A885B3D1931F549E3029419691BA38D2AF84D8D643AD50` |
