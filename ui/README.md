# OneShot context workspace

Run from this directory with Node.js 22 or later:

```powershell
npm start
```

Open **http://127.0.0.1:4173**. No package installation or build step is required. The server listens on this computer only. To use another port, set `PORT` before starting.

## Working features

- Four independent zones: Agent Chat, System Context, Sources, and Editor/Review.
- Temporary Process Display replaces the editor when preparation is accepted. It retains draft text, cursor, and scroll position. Partial or failed results stay visible until acknowledged.
- File, folder, and pasted-text import; nested folders; selection by file/folder; search and type filters; drag and drop for files.
- All four supplied PNGs, the architecture source, and all four pasted references are included. Earlier rebuild documents are marked historical.
- Distinct source actions: input text, import files/folders, include an existing library source, retain a web reference, and remove from current scope. Removed sources keep their identity, original bytes, and drafts in the library.
- Requested tasks: inventory, local content inspection, and text extraction. Requests for semantic understanding or research are rejected in review until a service is connected. Underlying deletion has separate authority and is unavailable.
- Text and simple Markdown preview, text editing, local saved revisions, original-to-working diff, revision downloads, image zoom, and expanded diagram viewing.
- Genuine local file reading, source inventory, text excerpts, image dimensions, coverage counts, checkpoint pause/resume, and stop.
- Separate prepared reports and recorded operation history with JSON download.
- Browser workspace recovery, saved chat drafts and context notes, command search (`Ctrl/Cmd K`), save (`Ctrl/Cmd S`), source search (`/`), collapsible panels, panel resizing, mobile view switching, dark/light themes, and reduced motion.

## How to use it

1. Open a supplied source, or choose **Add source**. Choose **Input text**, **Import**, **Existing**, or **Reference**. **Remove selected from scope** retains sources in the library; **Existing → Include** brings them back without duplication.
2. Select the files and the **Requested task**. The Start banner shows known text characters and an approximate token count. Web references store only their HTTP/HTTPS address; content is never fetched automatically.
3. Edit if needed. **Save revision** saves the working revision in this browser. The original file on disk is unchanged.
4. **Start preparation** uses the saved revisions. Unsaved edits are explicitly excluded.
5. Inspect the actual events. Pause is acknowledged at a reading boundary. Resume continues reading. Stop retains the completed work and findings.
6. A completed task automatically restores the previous review. For partial or failed output, review the findings and choose **Return to review**. Open the generated report under **Prepared context**, or reopen its history later. Rejected requests stay visible in review and create no prepared output.

## Current scope

This is a functional local UI and source-preparation workspace. Agent replies, semantic summarization, visual understanding/OCR, PDF extraction, browser research, and remote services are **not connected**. The Agent area keeps local drafts; it does not generate responses. System notes are retained context notes, not executed model instructions.

The local processor reports **completed** when the requested local task is covered. Omitted content or a mix of usable and unsupported sources produces **partial** output. Unsupported-only inspection reports **failed**. Inventory can complete for a retained reference without reading its target. Coverage always names the requested task; it does not imply semantic understanding.

Limits: 10 MiB per imported file, 2 MiB per decoded text file, UTF-8 text, 4,000 Unicode-character excerpts per source. Token counts estimate characters divided by four and are not model-tokenizer measurements. Preview and diff views limit very large content while retaining the full working text for export.

Workspace data is stored in this browser's IndexedDB. Save confirmation follows transaction completion. Download important work: clearing browser storage removes the local workspace. Runs interrupted by reload are recorded as interrupted; they are not resumed automatically. During operation, recovery snapshots are saved at acceptance, control acknowledgments, periodically during events, and at completion. A sudden browser crash can lose events after the last committed checkpoint.

The server serves files from this UI directory. It is a local preview server, not a deployment or authentication service. No AI/backend/container readiness is implied.

## Sources and verification

- [Requirements and source precedence](REQUIREMENTS.md)
- [Behavior expansion from the two new diagrams](BEHAVIOR-EXPANSION.md)
- [Browser verification and screenshots](VERIFICATION.md)
- [File API](https://www.w3.org/TR/FileAPI/) and [browser file usage](https://developer.mozilla.org/en-US/docs/Web/API/File_API/Using_files_from_web_applications): selected-file intake and object-URL previews.
- [IndexedDB](https://www.w3.org/TR/IndexedDB/): local transactional storage of files and revisions.
- [Node HTTP](https://nodejs.org/api/http.html): local static server.
- [Playwright](https://playwright.dev/docs/intro): browser interaction verification.

`npm run check` performs JavaScript syntax checks. Runtime/browser evidence is documented separately.
