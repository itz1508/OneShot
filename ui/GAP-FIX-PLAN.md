# Apply the market review

Authorized by: user request to fix and apply all gaps, October 9, 2026.

## Orientation and diagnosis

Target: D:\OneShot\ui, native browser ES modules started by server.mjs. No Git metadata is present. The five audited implementation hashes still match MARKET-GAP-REVIEW.md; npm --prefix ui run check passed before mutation. Existing sources, diagrams, audit evidence and the separate temp folder are preserved. Rollback source copy: D:\OneShot\.rollback\market-gap-2026-10-09.

The prior review's browser measurements and source call paths are current diagnostic evidence. Main causes: whole-workspace writes from stale tabs; fixed panel dimensions with clipped overflow; source-tree DOM replacement; unowned draft attachments; missing source revision provenance and recovery actions. Atomic storage and a lack of document horizontal overflow were ruled out as sufficient protections by the recorded two-tab and geometry reproductions.

## Ordered work

1. Protect persistence with atomic revision conflict detection and recoverable conflict UI. Add a validated, complete workspace backup/restore format that preserves Blob bytes and working state.
2. Repair source scrolling, responsive actions, viewport-bound resizing, visibility state, focus preservation, contrast, named dialogs, filter/progress semantics. Retain the editorial visual direction and four independent zones; add an intentional focused work mode.
3. Retain saved source versions, expose originals and history, mark changed-source outputs, preserve attachment ownership, and provide clickable source evidence. Correct note/instruction affordances and pause guidance. Improve diff and command navigation.
4. Discover an actual configured service before connecting semantic/visual/research/agent behavior. Use its official API documentation and prove actual requests. Missing credentials or a usable service block only that integration, not independent local repairs; request the missing configuration while continuing.
5. Run focused module checks and real UI flows covering two-tab conflicts, backups including malformed input, revision/attachment ownership, source operations, keyboard interaction, short/narrow/resized layouts, failure and recovery. Re-run broader checks only for changed shared paths or observed failures. Inspect desktop and mobile screenshots.

## Primary gap check before mutation

Scope and authority: approved local fixes use the existing UI and existing database as their owner. No second application/runtime/state store is introduced. Cross-tab checks must occur in the same IndexedDB transaction as the write; locks around stale snapshots are insufficient. Backups must validate completely before applying and leave current data recoverable. Legacy workspaces need additive normalization without loss. Existing saved source snapshots remain historical evidence; freshness is presented separately from past run success.

Dependencies: HTML/CSS work can proceed separately from storage modules; app.js integration is owned by the primary agent. External service selection remains evidence-dependent. Provider credentials must stay outside client code and logs. Preview services must be verified by listener/process evidence before restarting only the owned service if needed.

Acceptance: every D/F item in MARKET-GAP-REVIEW.md maps to implementation and post-change evidence or an explicit unresolved prerequisite. No broad READY claim substitutes for provider proof. Safe retries use fresh isolated browser sessions and preserve failed attempt logs. Finish by recording changed files, before/after behavior, test outcomes, and any remaining integration blocker.
