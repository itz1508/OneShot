# Market-practice alignment

OpenAI: host-owned SDK runtime, blocking tool guardrails before risky execution, handoffs with explicit ownership, and traces spanning agent, generation, tool, guardrail, and handoff events.

Claude: minimal tool configuration, PreToolUse denial, PostToolUse and failure receipts, lifecycle hooks, provider session continuity, and host filesystem enforcement beyond hooks.

LangGraph: separate thread-scoped checkpoints from cross-thread stores, use durable persistence rather than in-memory state for restart recovery, and wrap non-deterministic or side-effecting work so replay does not repeat effects.
