# OneShot UI acceptance map

The additional source-action and responsibility requirements from `mermaid-diagram (2).png` and `mermaid-diagram (3).png` are mapped and verified in [BEHAVIOR-EXPANSION.md](BEHAVIOR-EXPANSION.md). They refine coverage to the requested task and distinguish input, import, retained-source inclusion, linking, scope removal, deletion authority, and unresolved requests.

This document maps the new UI to the supplied references. It records required behavior, not a claim that the behavior has passed verification. The current workspace was inspected on 2026-10-08 and contained the three design files listed below before implementation.

## Source precedence

| Source | Responsibility in this UI |
| --- | --- |
| [Architecture.md](../Architecture.md) | Intake routes and sufficient / incomplete / unusable outcomes. |
| [workflow-diagram.png](../workflow-diagram.png) | Visual confirmation of the same behavior, including the separate system activity record. |
| [state-driven-transition.png](../state-driven-transition.png) | Source management, editor, starting, processing, pausing, paused, and return transitions. |
| User attachment `79bcf5af-9f84-4443-a636-516de27c2165/Pasted text.txt` | Four distinct product zones; temporary fifth view; file tree, import, Start/Pause, counts, Save and Diff Review. |
| User attachment `ea5411a7-3b3e-41c3-a1ef-cdd7f9b36cad/Pasted text.txt` | Latest interaction corrections G01–G14; selected scope; editor recovery; actual events; responsive behavior and accessibility. |
| Earlier attachments `b6970017-1e3e-4b2e-996c-ef5f0e207e29` and `d23e2a11-7ff9-4163-94a4-33f8eb51b7c3` | Historical deleted rebuild context. Carry forward source preservation, honest capability reporting, safe previews and evidence expectations. Their old three-pane arrangement is superseded by the later four-zone design. |

The request is to produce a new UI. The earlier backend, HTTP routes, provider adapters, container setup and six Job actions do not establish current capabilities. Their readiness gates cannot be claimed by browser-only checks. The current UI must identify unavailable AI, visual understanding, PDF text extraction and browser research wherever those capabilities would otherwise be implied.

## Required interactions

| ID | Acceptance behavior | Reference |
| --- | --- | --- |
| UI01 | Agent Chat, System Chat, Attachments, and Editor/Review retain independent state and ownership. | Layout; G01, G07 |
| UI02 | Process Display temporarily occupies the Editor/Review slot only after Start is accepted. It does not become a permanent fifth column. | Transition PNG; G01 |
| UI03 | Import adds actual sources to a searchable, expandable tree. Opening or closing a source review does not alter either chat. | Layout; G08 |
| UI04 | Start shows and freezes the selected source scope. The interface explicitly states whether it uses originals, saved revisions, or current working text. | G02; §6 |
| UI05 | Opening Process Display preserves the selected file, unsaved text, editor cursor and review position. Terminal return restores that context. | G03, G06 |
| UI06 | Pause has pending and confirmed states. Confirmation occurs only when actual work is held at a safe checkpoint. Resume continues from that checkpoint. | Transition PNG; G04 |
| UI07 | Source counts, operations and timestamps originate from actual local reads and processing events. Animation does not create events or imply AI activity. | G05; §5 |
| UI08 | Agent Chat receives no automatic message or execution when local preparation finishes. System Chat may retain a minimal status and a result link. | G07 |
| UI09 | Save creates a separate working revision; original source bytes remain available. Diff Review compares original and working text clearly. | G10; earlier source preservation rule |
| UI10 | Completion restores review. Partial, failed, interrupted and stopped results remain inspectable; partial/failed process closure requires acknowledgment. | G11; transition table |
| UI11 | Prepared output is a distinct artifact with source references, counts and known limitations. Raw extracted content must not be called an AI summary. | Workflow PNG; G06 |
| UI12 | Known input size, inspected file count, extracted character count and any token estimate are distinguished. A token estimate states its method. | G09 |
| UI13 | Text, images, folders and mixed sets follow the appropriate inspection behavior. Unsupported extraction and unavailable semantic inspection produce explicit gaps. | Architecture.md |
| UI14 | Source and detail regions can collapse independently. Narrow screens switch between zones without discarding work or causing horizontal overflow. | G12 |
| UI15 | Controls have accessible names, keyboard activation and visible focus. Expanded controls expose state; live status is announced without moving focus. | G13 |
| UI16 | Reduced-motion preferences suppress decorative transitions. File completion counts are not labeled as total AI progress. | G13; §5 |
| UI17 | Retained local sources, working revisions, notes and operation records recover after reload. Interrupted work is reported accurately. Storage failure is visible. | G14; earlier recoverability requirement |
| UI18 | Untrusted file text is rendered as data. Importing a file cannot execute its markup or issue instructions to Agent Chat. | Earlier market gap §4 |

## Useful additions grounded in the references

- A source search and selected-file count make the folder tree practical for larger collections.
- Keyboard shortcuts and a command menu can expose import, source search, zone visibility and review actions without adding permanent controls to every panel.
- Image zoom and fit controls make the supplied diagrams reviewable in the same detail slot.
- Local draft recovery and a visible saved revision state support the required editor/process transition.
- Downloadable prepared context and operation history keep completed evidence available after the transient process view closes.
- A capability explanation near Start makes the difference between real local extraction and unavailable model analysis clear before execution.

## Technical references used for the local UI

- [W3C File API](https://www.w3.org/TR/FileAPI/): selected files, immutable Blob data, asynchronous reading, read/error events, and blob URLs support actual local intake and image preview. File selection does not authorize arbitrary filesystem access.
- [W3C Indexed Database API](https://www.w3.org/TR/IndexedDB/): browser storage uses transactions. Saved status must follow transaction completion; failed commits must remain visible. This stores browser-local work, not a server backup.
- [W3C disclosure pattern](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/): show/hide controls expose their expanded state and support keyboard activation.
- [W3C window splitter pattern](https://www.w3.org/WAI/ARIA/apg/patterns/windowsplitter/): any interactive panel divider needs an accessible name, current value and keyboard behavior. The page notes that its example review is incomplete, so this is guidance rather than proof of accessibility conformance.
- [W3C status message technique](https://www.w3.org/WAI/WCAG22/Techniques/aria/ARIA22.html): a status region can announce changes while preserving the user's focus.

## Verification boundary

Verify the complete browser path after implementation: import actual text and images, select scope, edit, compare, save, start, inspect real events, pause/resume if the workload allows it, acknowledge partial results, restore the editor, download output, and reload retained work. Inspect desktop and mobile renderings. Record failures and remaining limitations with the evidence. Do not report model, backend, Docker or full application readiness from this UI verification.
