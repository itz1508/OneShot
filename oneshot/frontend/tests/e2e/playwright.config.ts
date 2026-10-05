import { defineConfig, devices } from "@playwright/test";

/**
 * Minimal Playwright config — targets a running `next dev` on 3000 and a
 * running daemon on 8787. Both are user-managed on a dev host; the sandbox
 * cannot run this file.
 */
export default defineConfig({
  testDir: "./chat",
  timeout: 30_000,
  reporter: [["list"]],
  use: {
    baseURL: process.env.RSM_CHAT_BASE_URL ?? "http://127.0.0.1:3000",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
