# OneShot video demonstration fixtures

**Summary:** Six synthetic, repeatable UI action sequences support video capture without impersonating real OneShot execution.

Open `/demo.html` through the web server, or use `?scenario=happy&autoplay=1&speed=2`.

- `happy`: full workflow to synthetic E2E verification receipt.
- `gap`: scanner rejection, Planner correction, revalidation.
- `blocked`: unsupported source; run blocked before Build Admission.
- `recovery`: interrupted Build, checkpoint reconciliation, resume.
- `mcp`: frontend API/MCP configuration and synthetic tool discovery (never connects).
- `audit`: multi-step repository audit and findings handoff.
- `all`: sequential playlist for long-form recordings.

Controls: **Play/Pause**, **Next scene**, **Restart**, **Speed**, and **Export action log**. `?step=N` renders a deterministic scene snapshot. `window.__oneshotDemo.getState()` exposes the in-browser capture state to E2E tests. Exported JSONL includes scenario, scene, elapsed time, status, and artifact references.

Run a static local preview from repository root:

```bash
python3 -m http.server 5174 --directory web/public
# visit http://127.0.0.1:5174/demo.html
```

Run the isolated browser test (only this config; production E2E suite remains separate):

```bash
cd web
npx playwright test -c playwright.demo.config.js
```

**Isolation contract:** Demo scripts do not call any OneShot API, MCP endpoint, or secret store. Every screen and exported artifact is marked synthetic. This verifies interactive playback and capture only—not backend E2E or real Build Admission. Do not promote synthetic event logs or demo receipts as evidence of production execution.