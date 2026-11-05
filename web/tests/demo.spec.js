import { test, expect } from '@playwright/test'

const scenarios = ['happy', 'gap', 'blocked', 'recovery', 'mcp', 'audit']

for (const scenario of scenarios) {
  test(`${scenario} demo plays all scenes with no backend requests`, async ({ page }) => {
    const backendCalls = []
    page.on('request', (request) => {
      if (request.url().includes('/api/') || request.url().includes('/mcp')) backendCalls.push(request.url())
    })
    await page.goto(`/demo.html?scenario=${scenario}`)
    await expect(page.getByText('SIMULATED · NO BACKEND')).toBeVisible()
    const expected = await page.evaluate(() => window.__oneshotDemo.scenarios.find((s) => s.id === new URLSearchParams(location.search).get('scenario')).scenes)
    for (let index = 0; index < expected; index++) await page.getByRole('button', { name: 'Next scene' }).click()
    const state = await page.evaluate(() => window.__oneshotDemo.getState())
    expect(state.synthetic).toBe(true)
    expect(state.events).toHaveLength(expected)
    expect(state.sceneIndex).toBe(expected - 1)
    expect(state.events.every((e) => e.scenarioId === scenario)).toBe(true)
    expect(backendCalls).toEqual([])
    await expect(page.locator('#percent')).toHaveText('100%')
    await page.getByRole('button', { name: /Open _.*\.json/ }).first().click()
    await expect(page.getByRole('dialog', { name: 'Review artifact' })).toBeVisible()
    await expect(page.locator('#fileEditor')).toHaveAttribute('readonly', '')
    await expect(page.locator('#fileEditor')).toHaveValue(/"synthetic": true/)
  })
}

test('paused playback and deterministic reload with step parameter', async ({ page }) => {
  await page.goto('/demo.html?scenario=happy&step=5')
  expect(await page.evaluate(() => window.__oneshotDemo.getState().sceneIndex)).toBe(5)
  await page.getByRole('button', { name: 'Play', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Pause' })).toBeVisible()
  await page.getByRole('button', { name: 'Pause' }).click()
  await expect(page.getByRole('button', { name: 'Play' })).toBeVisible()
  await page.getByRole('button', { name: 'Restart' }).click()
  await expect(page.locator('#percent')).toHaveText('0%')
})

test('blocked scenario never produces a build receipt', async ({ page }) => {
  await page.goto('/demo.html?scenario=blocked')
  const count = await page.evaluate(() => window.__oneshotDemo.scenarios.find((s) => s.id === 'blocked').scenes)
  for (let i = 0; i < count; i++) await page.locator('#next').click()
  const result = await page.evaluate(() => window.__oneshotDemo.getState())
  expect(Object.keys(result.artifacts)).not.toContain('_build.json')
  await expect(page.locator('#execution')).toHaveText('blocked (demo)')
})