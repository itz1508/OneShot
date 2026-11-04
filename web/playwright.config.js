import { defineConfig } from '@playwright/test'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const repoRoot = fileURLToPath(new URL('..', import.meta.url))
const pythonVersion = process.env.ONESHOT_TEST_PYTHON || '3.11'

export default defineConfig({
  testDir: './tests',
  timeout: 120_000,
  workers: 1,
  expect: { timeout: 30_000 },
  use: { baseURL: 'http://127.0.0.1:5173', browserName: 'chromium' },
  reporter: [['list'], ['html', { open: 'never' }]],
  webServer: [
    {
      command: `uv run --no-sync --python ${pythonVersion} uvicorn mvp.api:app --host 127.0.0.1 --port 8000`,
      cwd: repoRoot,
      env: {
        ONESHOT_STATE_ROOT: process.env.ONESHOT_STATE_ROOT || join(tmpdir(), 'oneshot-playwright-audit'),
        MCP_WORKSPACE_ROOT: repoRoot,
        MCP_TRUSTED_ANCESTRY: 'true',
        ONESHOT_WEB_ORIGIN: 'http://127.0.0.1:5173',
        ONESHOT_MCP_URL: '',
        ONESHOT_MCP_COMMAND: 'uv',
        ONESHOT_MCP_ARGS_JSON: JSON.stringify([
          'run', '--no-sync', '--python', pythonVersion, 'python',
          join(repoRoot, 'tests', 'fixtures', 'mcp_research_server.py'),
        ]),
      },
      url: 'http://127.0.0.1:8000/api/health',
      timeout: 30_000,
      reuseExistingServer: false,
    },
    {
      command: 'npm run dev',
      url: 'http://127.0.0.1:5173',
      timeout: 30_000,
      reuseExistingServer: false,
    },
  ],
})
