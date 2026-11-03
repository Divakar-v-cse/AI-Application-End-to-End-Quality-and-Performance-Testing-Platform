import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright configuration for the AI Quality Platform UI suite.
 *
 * The frontend and the backend are both started automatically (or reused when
 * they are already running). Override the ports/locations with:
 *   PW_BASE_URL, PW_PORT, API_BASE_URL, PYTHON_BIN, DEMO_USER_EMAIL,
 *   DEMO_USER_PASSWORD.
 *
 * Run: `npm run test:e2e` (from frontend/) or
 *      `npx playwright test --reporter=json` for the machine-readable report
 *      that POST /api/ingest/playwright consumes.
 */
const port = Number(process.env.PW_PORT || 5173)
const baseURL = process.env.PW_BASE_URL || `http://127.0.0.1:${port}`
const apiURL = process.env.API_BASE_URL || 'http://127.0.0.1:8000'

const venvPython = join('..', '.venv', 'Scripts', 'python.exe')
const python =
  process.env.PYTHON_BIN || (existsSync(join(process.cwd(), venvPython)) ? `"${venvPython}"` : 'python')

export const STORAGE_STATE = 'tests/ui/.auth/state.json'

export default defineConfig({
  testDir: './tests/ui',
  outputDir: './test-results/artifacts',
  timeout: 45_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  forbidOnly: Boolean(process.env.CI),
  reporter: [
    ['list'],
    ['json', { outputFile: 'test-results/playwright-report.json' }],
    ['html', { outputFolder: 'playwright-report', open: 'never' }]
  ],
  use: {
    baseURL,
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off'
  },
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.js/ },
    {
      name: 'chromium',
      dependencies: ['setup'],
      testIgnore: /auth\.setup\.js/,
      use: { ...devices['Desktop Chrome'], storageState: STORAGE_STATE, viewport: { width: 1440, height: 900 } }
    }
  ],
  webServer: [
    {
      command: `${python} -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
      cwd: '../backend',
      url: `${apiURL}/healthz`,
      reuseExistingServer: true,
      timeout: 120_000,
      stdout: 'ignore',
      stderr: 'pipe'
    },
    {
      command: `npm run dev -- --port ${port} --host 127.0.0.1`,
      cwd: '.',
      url: baseURL,
      reuseExistingServer: true,
      timeout: 120_000,
      stdout: 'ignore',
      stderr: 'pipe'
    }
  ]
})
