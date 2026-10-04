# Data Boundary

The frontend MUST NOT persist bucket state. Reads go through
`packages/rsm-client/src/rsm-client.ts`, writes go through the same path. Local caches may
exist for session-level UX only and are considered volatile.
