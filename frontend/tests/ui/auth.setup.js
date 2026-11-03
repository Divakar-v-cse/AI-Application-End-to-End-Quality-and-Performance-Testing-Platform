import { mkdirSync } from 'node:fs'
import { dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test as setup } from '@playwright/test'

/**
 * Signs in once through the real login form and stores the browser state
 * (localStorage token) for every other spec. Keeping the login in a setup
 * project means the suite exercises the form exactly once and the remaining
 * specs start authenticated.
 */
const STATE = fileURLToPath(new URL('./.auth/state.json', import.meta.url))
const EMAIL = process.env.DEMO_USER_EMAIL || 'qa@example.com'
const PASSWORD = process.env.DEMO_USER_PASSWORD || 'Passw0rd!'

setup('authenticate as the demo QA user', async ({ page }) => {
  mkdirSync(dirname(STATE), { recursive: true })

  await page.goto('/login')
  await page.getByTestId('login-email').fill(EMAIL)
  await page.getByTestId('login-password').fill(PASSWORD)
  await page.getByTestId('login-submit').click()

  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByRole('heading', { level: 1, name: 'Quality Dashboard' })).toBeVisible()

  await page.context().storageState({ path: STATE })
})
