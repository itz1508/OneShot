# ADR 0005 — Next.js App Router for `frontend/web`

**Status:** NEW (this document). Binding.

The frontend is an **official Next.js (App Router) application** created with
`create-next-app`, using TypeScript, ESLint, Tailwind CSS, `src/` directory,
App Router, Turbopack, import alias `@/*`.

### Decision

```
pnpm create next-app@latest frontend/web \
  --ts --eslint --tailwind --src-dir --app --turbopack \
  --import-alias "@/*"
```

### Consequences

- Runtime floor: Node.js ≥ 20 (per upstream System Requirements).
- Dependency surface stays canonical Next.js + Tailwind — no AI SDKs.
- Reproducible scaffold command recorded here and in the project README.

### Status note

This repository was scaffolded in an environment where `create-next-app`
could not execute. The directory `frontend/web` contains hand-written
placeholders only. The implementation turn on a real development host MUST
re-run the command above and overwrite the placeholders.
