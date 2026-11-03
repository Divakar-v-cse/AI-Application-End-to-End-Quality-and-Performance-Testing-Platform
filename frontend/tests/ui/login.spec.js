import { expect, test } from '@playwright/test'

/**
 * Catalog cases:
 *   ui.login.valid_credentials
 *   ui.login.invalid_credentials
 *   ui.login.empty_form
 */
test.use({ storageState: { cookies: [], origins: [] } })

const EMAIL = process.env.DEMO_USER_EMAIL || 'qa@example.com'
const PASSWORD = process.env.DEMO_USER_PASSWORD || 'Passw0rd!'

test.describe('Login', () => {
  test('valid credentials reach the dashboard', async ({ page }) => {
    await page.goto('/login')

    await page.getByTestId('login-email').fill(EMAIL)
    await page.getByTestId('login-password').fill(PASSWORD)
    await page.getByTestId('login-submit').click()

    await expect(page).toHaveURL(/\/dashboard$/)
    await expect(page.getByRole('heading', { level: 1, name: 'Quality Dashboard' })).toBeVisible()

    const token = await page.evaluate(() => localStorage.getItem('aqp.token'))
    expect(token, 'a bearer token is persisted for later API calls').toBeTruthy()

    const user = await page.evaluate(() => localStorage.getItem('aqp.user'))
    expect(JSON.parse(user)).toMatchObject({ email: EMAIL })
  })

  test('invalid credentials show an error', async ({ page }) => {
    await page.goto('/login')

    await page.getByTestId('login-email').fill(EMAIL)
    await page.getByTestId('login-password').fill('definitely-not-the-password')
    await page.getByTestId('login-submit').click()

    const error = page.getByTestId('login-error')
    await expect(error).toBeVisible()
    await expect(error).toHaveText(/invalid email or password/i)
    await expect(page).toHaveURL(/\/login$/)
    expect(await page.evaluate(() => localStorage.getItem('aqp.token'))).toBeNull()
  })

  test('empty and malformed input is rejected client-side', async ({ page }) => {
    await page.goto('/login')

    await page.getByTestId('login-email').fill('')
    await page.getByTestId('login-submit').click()
    await expect(page.getByTestId('login-error')).toHaveText('Email is required.')

    await page.getByTestId('login-email').fill('not-an-email')
    await page.getByTestId('login-submit').click()
    await expect(page.getByTestId('login-error')).toHaveText('Enter a valid email address.')

    await page.getByTestId('login-email').fill(EMAIL)
    await page.getByTestId('login-password').fill('')
    await page.getByTestId('login-submit').click()
    await expect(page.getByTestId('login-error')).toHaveText('Password is required.')
    await expect(page).toHaveURL(/\/login$/)
  })
})
