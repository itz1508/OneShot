# ADR 0013 — Right rail is a context control surface; ReplayStreaming surface is ephemeral

**Status:** V3. Binding.

## Decision

The RSM UI has exactly two surfaces:

1. **Right rail** (persistent, non-modal): a context control surface
   showing Sources count, Snapshot readiness, Representation (preserved
   or reduced), Context budget usage, ON/OFF switch, and a manual
   `[Replay]` button. It is NOT a workspace, dashboard, file manager,
   task panel, or second chat.
2. **Ephemeral ReplayStreaming surface** (transient): appears while
   RSM is delivering a Snapshot (either on interaction start or on
   manual `[Replay]`), disappears on completion/failure/cancel.
   Implemented as a `role="status" aria-live="polite"` region with an
   indeterminate stage-based indicator ("Preparing" / "Streaming" /
   "Complete"). It does NOT display fake numeric progress. Honours
   `prefers-reduced-motion`. Dismissible by `Escape`.

Both surfaces consume the real daemon API — no mock data.

## Non-goals

- The ephemeral surface is **not persisted** as conversation history.
- Completion does NOT render a Main Chat message; whether to represent
  the delivery in Main Chat is a decision for the consuming runtime,
  not for RSM.
- The right rail does NOT contain Main Chat.
- There is no "RSM Workspace" / "RSM Chat" screen.

## Accessibility

- Switch uses `role="switch"` + `aria-checked` per W3C ARIA Authoring
  Practices (`https://www.w3.org/WAI/ARIA/apg/patterns/switch/`).
- Open/close chevron uses `aria-expanded` + `aria-controls`.
- Ephemeral surface uses `role="status" aria-live="polite"` so it is
  announced without stealing focus.
- `Escape` closes the ephemeral surface and the right rail; focus
  returns to the invoking button.
- `prefers-reduced-motion` suppresses the pulse animation.

## Rationale

The user's mission text makes the "right rail as control surface" +
"ephemeral streaming surface" distinction explicit; the ADR fixes it so
the implementation cannot drift into a second workspace.
