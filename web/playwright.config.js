import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  timeout: 120_000,
  expect: { timeout: 30_000 },
  use: { baseURL: 'http://127.0.0.1:5173', browserName: 'chromium' },
  reporter: [['list'], ['html', { open: 'never' }]],
})
