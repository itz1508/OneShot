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

test('visual model routing changes line colors without contacting providers', async ({ page }) => {
  const calls = []
  page.on('request', (request) => {
    if (request.url().includes('/api/') || request.url().includes('/mcp')) calls.push(request.url())
  })
  await page.goto('/demo.html?scenario=happy')
  await expect(page.locator('#route-sidebar')).toBeVisible()
  const initial = await page.locator('#route-sidebar').evaluate((element) =>
    getComputedStyle(element).getPropertyValue('--build-route').trim())
  await page.selectOption('#route-build', 'wonder')
  await expect(page.locator('#route-label-build')).toContainText('Muse Wonder')
  const switched = await page.locator('#route-sidebar').evaluate((element) =>
    getComputedStyle(element).getPropertyValue('--build-route').trim())
  expect(switched).not.toBe(initial)
  await page.selectOption('#route-research', 'meta')
  await expect(page.locator('#route-label-research')).toContainText('Meta Muse Spark')
  await page.selectOption('#route-view', 'parallel')
  await expect(page.locator('.route-lanes')).toBeVisible()
  await expect(page.locator('.route-lanes .lane')).toHaveCount(4)
  await expect(page.locator('#route-lane-four')).toContainText('Muse Wonder')
  await expect(page.locator('.route-single-builder')).toBeHidden()
  await expect(page.locator('#route-modal-caption')).toContainText('separate admitted Sandbox attempts')
  await page.selectOption('#route-view', 'audit')
  await expect(page.locator('.route-build-chain')).toBeHidden()
  await expect(page.locator('.route-roles')).toBeHidden()
  await expect(page.locator('#route-model-controls')).toBeHidden()
  await expect(page.locator('#route-gates')).toBeHidden()
  await expect(page.locator('.route-only-audit')).toBeVisible()
  await page.selectOption('#route-view', 'standard')
  await expect(page.locator('.route-roles')).toBeVisible()
  await expect(page.locator('.route-single-builder')).toBeVisible()
  expect(calls).toEqual([])
})

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