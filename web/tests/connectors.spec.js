import { test, expect } from '@playwright/test'

test('Connection settings modal supports MCP and model API configuration', async ({ page }) => {
  let snapshot = {
    mcp: { status: 'disconnected', transport: 'http', tools: [], error: '', url: '', auth_type: 'none', has_bearer_token: false },
    model: { status: 'disconnected', api_base_url: '', model_id: '', error: '', provider_response: '', has_api_key: false },
  }

  await page.route('**/api/health', async (route) => {
    await route.fulfill({ json: { status: 'ok', mcp_transport_configured: false } })
  })
  await page.route('**/api/connectors', async (route) => {
    await route.fulfill({ json: snapshot })
  })
  await page.route('**/api/connectors/mcp/test', async (route) => {
    snapshot = {
      ...snapshot,
      mcp: {
        status: 'connected',
        transport: 'http',
        url: 'http://127.0.0.1:9234/mcp',
        auth_type: 'none',
        error: '',
        tool_count: 2,
        tools: [
          { name: 'oneshot_research', description: 'Research tool' },
          { name: 'source_lookup', description: 'Lookup source data' },
        ],
        has_bearer_token: false,
      },
    }
    await route.fulfill({
      json: {
        status: 'connected',
        transport: 'http',
        url: 'http://127.0.0.1:9234/mcp',
        auth_type: 'none',
        error: '',
        tool_count: 2,
        tools: [
          { name: 'oneshot_research', description: 'Research tool' },
          { name: 'source_lookup', description: 'Lookup source data' },
        ],
      },
    })
  })
  await page.route('**/api/connectors/model/test', async (route) => {
    snapshot = {
      ...snapshot,
      model: {
        status: 'connected',
        api_base_url: 'https://api.example.test/v1',
        model_id: 'test-model',
        error: '',
        provider_response: 'provider-ready',
        has_api_key: true,
      },
    }
    await route.fulfill({
      json: {
        status: 'connected',
        api_base_url: 'https://api.example.test/v1',
        model_id: 'test-model',
        provider_response: 'provider-ready',
        error: '',
      },
    })
  })
  await page.route('**/api/connectors/model/save', async (route) => {
    snapshot = {
      ...snapshot,
      model: {
        ...snapshot.model,
        status: 'saved',
        api_base_url: 'https://api.example.test/v1',
        model_id: 'test-model',
        error: '',
        provider_response: snapshot.model.provider_response,
        has_api_key: true,
      },
    }
    await route.fulfill({
      json: {
        status: 'saved',
        api_base_url: 'https://api.example.test/v1',
        model_id: 'test-model',
        provider_response: '',
        error: '',
      },
    })
  })

  await page.goto('/')
  await page.getByRole('complementary', { name: 'Primary navigation' }).getByRole('button', { name: 'Open connection settings' }).click()
  const dialog = page.getByRole('dialog', { name: 'Connection settings' })
  await expect(dialog).toBeVisible()
  await page.getByLabel('MCP server URL').fill('http://127.0.0.1:9234/mcp')
  await page.getByLabel('Authentication type').selectOption('none')
  await page.getByRole('button', { name: 'Test Connection' }).first().click()
  await expect(page.getByText('MCP test passed: 2 tools discovered')).toBeVisible()
  await expect(page.getByText('oneshot_research')).toBeVisible()

  await page.getByLabel('API base URL').fill('https://api.example.test/v1')
  await page.getByLabel('Model ID').fill('test-model')
  await page.getByLabel('Secret API key').fill('sk-test')
  await page.getByRole('button', { name: 'Test Connection' }).last().click()
  await expect(page.getByText('Model test passed: provider-ready')).toBeVisible()
  await expect(page.getByText('Provider response: provider-ready')).toBeVisible()
})
