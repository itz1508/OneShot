# Inline-stub unit tests for `features/chat`

These tests are plain TypeScript files that assert with `console.log` and set
`process.exit(1)` on failure. **No vitest, no jest, no new dev dependency.**

To run on a dev host:

```bash
# with Bun
cd frontend/web && bun src/features/chat/__tests__/pack.test.ts

# or with Node + tsx
cd frontend/web && npx tsx src/features/chat/__tests__/pack.test.ts
```

The sandbox cannot run these (no Node runtime available for frontend);
run them on a dev host as part of the frontend verification sweep.
