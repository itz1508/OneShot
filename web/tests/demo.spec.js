import { test, expect } from '@playwright/test'

const scenarios = ['happy', 'gap', 'blocked', 'recovery', 'mcp', 'audit']
for (const scenario of scenarios) {
  test(`${scenario}: OneShot work screen projects every synthetic workflow action`, async ({ page }) => {
    const calls = []
    const errors = []
    page.on('request', (req) => { if (req.url().includes('/api/') || req.url().includes('/mcp')) calls.push(req.url()) })
    page.on('pageerror', (error) => errors.push(String(error)))
    await page.goto(`/demo.html?scenario=${scenario}`)
    await expect(page.getByText('SIMULATED · NO BACKEND')).toBeVisible()
    const expected = await page.evaluate(() => window.__oneshotDemo.scenarios.find((s) => s.id === new URLSearchParams(location.search).get('scenario')).scenes)
    await expect(page.locator('#demo-count')).toHaveText(`Scene 0 / ${expected}`)
    for (let i = 0; i < expected; i++) {
      await page.getByRole('button', { name: 'Next scene' }).click()
      await expect(page.locator('.robot')).toBeVisible()
      await expect(page.locator('#demo-count')).toHaveText(`Scene ${i + 1} / ${expected}`)
      const projection = await page.evaluate(() => window.__oneshotDemo.getState())
      expect(projection.sceneIndex).toBe(i)
      expect(projection.synthetic).toBe(true)
    }
    const final = await page.evaluate(() => window.__oneshotDemo.getState())
    expect(final.presentation.status).toBe(scenario === 'blocked' ? 'error' : 'complete')
    expect(final.events.length).toBeGreaterThan(expected)
    expect(errors).toEqual([])
    expect(calls).toEqual([])
    if (scenario === 'blocked') expect(final.artifacts).not.toHaveProperty('_build.json')
    await page.locator('#demo-artifacts').click()
    await expect(page.locator('#inspector')).toBeVisible()
    await expect(page.locator('#inspect-content')).toContainText('"synthetic": true')
  })
}

test('playback control preserves stage behavior on pause and reset', async ({ page }) => {
  await page.goto('/demo.html?scenario=happy&step=5')
  expect(await page.evaluate(() => window.__oneshotDemo.getState().sceneIndex)).toBe(5)
  await page.locator('#play').click()
  await expect(page.locator('#play')).toHaveText('Pause')
  await page.locator('#play').click()
  await expect(page.locator('#play')).toHaveText('Play')
  await page.locator('#restart-demo').click()
  await expect(page.locator('#demo-count')).toHaveText('Scene 0 / 17')
})

test('sequence gap fails closed in the original OneShot projection', async ({ page }) => {
  await page.goto('/demo.html')
  const result = await page.evaluate(() => {
    window.__OneShotTest.reset('sample')
    const accepted = window.__OneShotTest.apply({ seq: 2, run_id: 'gap-test', type: 'stage.started', data: { role: 'build' } })
    return { accepted, status: window.__OneShotTest.state.status, errors: window.__OneShotTest.state.errors }
  })
  expect(result.accepted).toBe(false)
  expect(result.status).toBe('error')
  expect(result.errors.join(' ')).toContain('EVENT GAP')
})