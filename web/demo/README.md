# OneShot — work-screen video demo

**Status:** synthetic video visualization; no production execution, MCP requests, or host authorization.

**Visual source:** user-provided `OneShot_Agent_Live_Screen.html` from ChatGPT Library, inspected in headless Chromium at desktop and mobile viewports. The original seven-role robot, role-specific work scene, requirement pane, running-step timeline, and stage handoff graphics are preserved. Extra host-stage labels explicitly distinguish Input, Fixture Validation, and Build Admission from Builder operations.

## Browser usage

Run from the existing `web/` Vite app, open `/demo.html?scenario=happy`. Use Scenario, Play/Pause, Next Scene, Restart, Inspect Artifact, Export JSONL and playback Speed. Offline use: open the standalone HTML with a browser that permits local file URLs or use Playwright `page.set_content()`; no other CSS/JS imports are required.

Synthetic scenarios: `happy` (17), `gap` (12), `blocked` (7), `recovery` (13), `mcp` (11), `audit` (10). All 70 scenes feed the original OneShot view through its existing test-only event projection, with sequential event IDs and the original stage-specific visualizations.

## Host and model routing side panel

The existing /demo.html playback includes a **right-side routing inspector** with Standard Workflow, Parallel Task Execution (40-task example) and Repository Audit views. Standard shows **Host intake → Research Catalog → shared intent for all three roles → Host-controlled validation gates → Builder candidate → Modal Sandbox → host verification**, with proposed LangGraph tracing. Parallel displays **four distinct Builder lanes** with per-task admission/preflight and isolated Sandbox attempts; the Repository Audit view hides model/Build lanes and stays read-only.

Use the Research, Audit Discovery, Planning and Builder model menus to change **the highlighted line color and displayed model name**. Solid lines represent host-owned steps; dashed lines represent model calls; double lines identify Modal Sandbox execution; dotted lines represent tracing. The Builder menu can show Qwen3.8 or Muse Wonder; those integrations remain proposed. The 40-task view shows four proposed worker lanes and a dependency-aware host verification barrier; it does **not** claim that four builds actually ran. The Catalog is only a synthetic Research investigation matcher, not accepted requirements. Structural Gap Analysis, Scanner, specification freeze, Fixture Validation, Package Lock, Build TaskTodo compilation and Build Admission remain separate host gates in the canonical workflow.

**These controls never change MODEL_API_KEY, contact a provider, schedule a sandbox or authorize execution.** Credentials remain server-side. LangGraph is proposed; the host's events and checkpoints are the current source of truth.

## Verification

`cd web && npm ci && npx playwright install chromium && npm run test:demo`

`python web/demo/capture.py --source web/public/demo.html --chromium /usr/bin/chromium --out demo-capture --scenario all`

The capture script records MP4/WebM, screenshots, JSONL action logs, and storyboards. Offline recordings test visual projection, controls, warnings, and navigation. They are **not** production Build/E2E evidence. The `web/public/live.html` production-style reference and React host frontend are unchanged.

## Boundary

This demo never submits tasks to `/api`, never calls MCP, never authorizes Build, and never generates trusted receipts. Real OneShot workflow verification requires a runnable repository, working host/provider integration and independently observed persisted records.