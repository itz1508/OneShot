# RSM V1 — Architecture Overview

```
                       ┌──────────────────────────────────────┐
                       │  External Source                     │
                       │  (file, folder, PDF, markdown,       │
                       │   ChatGPT export, pasted, stdin)     │
                       └───────────────┬──────────────────────┘
                                       │
                                       ▼
                            ┌──────────────────────┐
                            │  Extraction          │
                            │  (deterministic)     │
                            └──────────┬───────────┘
                                       │
                                       ▼
                             ┌───────────────────┐
                             │  Bucket (canonical)│
                             │  schema_version=1  │
                             │  A1-frozen identity │
                             └─────────┬───────────┘
                                       │
      ┌────────────────────────────────┼─────────────────────────────────┐
      │                                │                                 │
      ▼                                ▼                                 ▼
┌──────────────┐              ┌──────────────────┐              ┌──────────────┐
│  Lifecycle   │              │  Classification  │              │  Execution   │
│  state       │              │  (STORE/REVIEW/  │              │  state       │
│  machine     │              │   REVIEW_TODO/   │              │  tasks       │
│  (7 states,  │              │   READY_EXECUTION│              │  (keyed by   │
│   8 legal    │              │   — independent) │              │   bucket_id) │
│   edges)     │              └──────────────────┘              └──────────────┘
└──────┬───────┘                        │                               │
       │                                └──────────┬────────────────────┘
       └───────────────────┬───────────────────────┘
                           │
                           ▼
                 ┌───────────────────┐
                 │ Replay Readiness  │
                 │ (DERIVED, not a   │
                 │  lifecycle state) │
                 └─────────┬─────────┘
                           │
                           ▼
                 ┌───────────────────┐
                 │  Replay Envelope  │
                 └─────────┬─────────┘
                           │
       ┌───────────────────┼─────────────────────┐
       │                   │                     │
       ▼                   ▼                     ▼
   ┌────────┐         ┌─────────┐          ┌─────────────┐
   │  HTTP  │         │   MCP   │          │ JSON export │   stdout
   │        │         │ resource│          │             │   (same canonical payload
   │        │         │  URIs   │          │             │    across all transports)
   └────────┘         └─────────┘          └─────────────┘
```

**Daemon is the sole authoritative state owner.** The UI is a view onto the
daemon via `http://127.0.0.1:…`. MCP is a transport, not a persistence layer.

**No AI/LLM/agent SDK, no provider registry, no vector DB** lives in RSM core.
