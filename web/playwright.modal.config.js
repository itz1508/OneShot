import { defineConfig } from '@playwright/test'

const baseURL = process.env.MODAL_BASE_URL
if (!baseURL || !/^https:\/\/[a-zA-Z0-9.-]+\.modal\.run\/?$/.test(baseURL)) {
  throw new Error('MODAL_BASE_URL must be the deployed HTTPS Modal endpoint')
}

export default defineConfig({
  testDir: './tests-modal',
  timeout: 150_000,
  workers: 1,
  expect: { timeout: 90_000 },
  use: { baseURL, browserName: 'chromium' },
  reporter: [['list'], ['html', { open: 'never' }]],
})
