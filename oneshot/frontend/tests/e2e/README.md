# Playwright specs — RSM UI

Specs run on a dev host; the sandbox cannot execute them (overlayfs blocks
`next build`; see `frontend/web/HAND_AUTHORED.md`).

## Chat intake (`chat/intake.spec.ts`)

Covers Tests A–I from `CHAT_INTAKE_PLAN.md`:

| ID | Scenario |
|---|---|
| A | text / paste |
| B | single file |
| C | multiple attachments |
| D | invalid archive (zip-slip) |
| E | wrong supplied hash |
| F | accepted source replays |
| G | folder selection (Chromium only) |
| H | ZIP via multipart upload |
| I | duplicate attach |

## Running

```bash
# Terminal 1
uvicorn rsm.api.app:create_app --factory --host 127.0.0.1 --port 8787

# Terminal 2
cd frontend/web && pnpm dev

# Terminal 3
cd tests/frontend/e2e
pnpm add -D @playwright/test
pnpm exec playwright install chromium
pnpm exec playwright test
```

The ZIP fixtures are built from `chat/fixtures/README.md` before the first run.
