# OneShot — work-screen video demo

**Status:** synthetic video visualization; no production execution, MCP requests, or host authorization.

**Visual source:** user-provided `OneShot_Agent_Live_Screen.html` from ChatGPT Library, inspected in headless Chromium at desktop and mobile viewports. The original seven-role robot, role-specific work scene, requirement pane, running-step timeline, and stage handoff graphics are preserved. Extra host-stage labels explicitly distinguish Input, Fixture Validation, and Build Admission from Builder operations.

## Browser usage

Run from the existing `web/` Vite app, open `/demo.html?scenario=happy`. Use Scenario, Play/Pause, Next Scene, Restart, Inspect Artifact, Export JSONL and playback Speed. Offline use: open the standalone HTML with a browser that permits local file URLs or use Playwright `page.set_content()`; no other CSS/JS imports are required.

Synthetic scenarios: `happy` (17), `gap` (12), `blocked` (7), `recovery` (13), `mcp` (11), `audit` (10). All 70 scenes feed the original OneShot view through its existing test-only event projection, with sequential event IDs and the original stage-specific visualizations.

## Verification

`cd web && npm ci && npx playwright install chromium && npm run test:demo`

`python web/demo/capture.py --source web/public/demo.html --chromium /usr/bin/chromium --out demo-capture --scenario all`

The capture script records MP4/WebM, screenshots, JSONL action logs, and storyboards. Offline recordings test visual projection, controls, warnings, and navigation. They are **not** production Build/E2E evidence. The `web/public/live.html` production-style reference and React host frontend are unchanged.

## Boundary

This demo never submits tasks to `/api`, never calls MCP, never authorizes Build, and never generates trusted receipts. Real OneShot workflow verification requires a runnable repository, working host/provider integration and independently observed persisted records.