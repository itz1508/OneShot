import { test, expect } from '@playwright/test'

test('real Audit capability persists findings, replays after reload, and exposes read-only artifacts', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('combobox', { name: 'Task capability' }).selectOption('audit')
  await page.getByRole('textbox', { name: 'Task description' }).fill('Audit repository integration and persistence')
  await page.getByRole('button', { name: 'Submit task' }).click()
  await expect(page.getByRole('status', { name: 'Execution status' })).toHaveText('audit_pending')
  await page.getByRole('button', { name: 'Run Audit' }).click()
  await expect(page.getByRole('status', { name: 'Execution status' })).toHaveText('audit_completed')
  await expect(page.getByText('_audit.json')).toBeVisible()
  const taskUrl = page.url()
  await page.reload()
  await expect(page).toHaveURL(taskUrl)
  await expect(page.getByRole('status', { name: 'Execution status' })).toHaveText('audit_completed')
  await page.getByText('_audit.json').click()
  await expect(page.getByRole('dialog', { name: 'Review artifact' })).toBeVisible()
  await expect(page.locator('#file-editor')).toHaveAttribute('readonly', '')
  await expect(page.getByText('Verified, read-only artifact')).toBeVisible()
})

test('API rejects cross-purpose dispatch without advancing stages', async ({ request }) => {
  const researchResponse = await request.post('http://127.0.0.1:8000/api/tasks', {
    data: { prompt: 'Research the repository' },
  })
  expect(researchResponse.status()).toBe(201)
  const research = await researchResponse.json()
  const auditResponse = await request.post('http://127.0.0.1:8000/api/tasks', {
    data: { prompt: 'Audit the repository', purpose: 'audit' },
  })
  expect(auditResponse.status()).toBe(201)
  const audit = await auditResponse.json()
  expect((await request.post(`http://127.0.0.1:8000/api/tasks/${research.task_id}/audit`)).status()).toBe(400)
  expect((await request.post(`http://127.0.0.1:8000/api/tasks/${audit.task_id}/research`)).status()).toBe(400)
  const state = await request.get(`http://127.0.0.1:8000/api/tasks/${audit.task_id}`)
  const record = await state.json()
  expect(record.current_stage).toBe('research')
  expect(record.completed_stages).toEqual([])
})
