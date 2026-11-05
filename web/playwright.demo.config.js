import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  testMatch: 'demo.spec.js',
  timeout: 30_000,
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:5174', browserName: 'chromium', viewport: { width: 1440, height: 900 } },
  reporter: [['list']],
  webServer: {
    command: 'python3 -m http.server 5174 --directory public',
    url: 'http://127.0.0.1:5174/demo.html',
    timeout: 15_000,
    reuseExistingServer: false,
  },
})