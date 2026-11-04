import { test, expect } from '@playwright/test'

test('deployed live page runs Audit concurrently with SSE and reloads result', async ({ page }) => {
  const errors = []
  page.on('pageerror', error => errors.push(error.message))

  await page.goto('/live.html')
  await expect(page.locator('#conn')).toHaveAttribute('data-ok', 'true', { timeout: 60_000 })
  await page.locator('#q').fill('Audit the deployed source bundle')
  await expect(page.locator('#send')).toBeEnabled()
  await page.locator('#send').click()

  // The page connects EventSource before POST /audit. Without Modal input
  // concurrency, a single container can indefinitely queue that POST.
  await expect(page.getByText('Looked through the workspace', { exact: false })).toBeVisible({
    timeout: 120_000,
  })
  await expect(page.locator('.msg.agent.warn')).toHaveCount(0)
  expect(page.url()).toMatch(/#[0-9a-f]{32}$/)
  const taskUrl = page.url()

  await page.reload()
  await expect(page).toHaveURL(taskUrl)
  await expect(page.getByText('Looked through the workspace', { exact: false })).toBeVisible()
  expect(errors).toEqual([])
})
