import { expect, test } from '@playwright/test'

/**
 * Catalog case: ui.navigation.all_views
 *
 * Every sidebar destination must render without a client-side error and keep
 * the browser URL in sync.
 */
const VIEWS = [
  { label: 'Dashboard', path: '/dashboard', title: 'Quality Dashboard', heading: 'Quality Dashboard' },
  { label: 'Test Runs', path: '/runs', title: 'Test Runs', heading: 'Test Runs' },
  { label: 'API Metrics', path: '/metrics', title: 'API Metrics', heading: 'API Metrics' },
  { label: 'Data Quality', path: '/data-quality', title: 'Data Quality', heading: 'Data Quality' },
  { label: 'Performance', path: '/performance', title: 'Performance', heading: 'Performance testing' },
  { label: 'Quality Gates', path: '/gates', title: 'Quality Gates', heading: 'CI/CD quality gates' },
  { label: 'AI Chatbot', path: '/chatbot', title: 'AI Chatbot', heading: 'Demo AI application' }
]

test.describe('Navigation', () => {
  test('all views render from the sidebar', async ({ page }) => {
    const pageErrors = []
    page.on('pageerror', (error) => pageErrors.push(error.message))

    await page.goto('/dashboard')

    for (const view of VIEWS) {
      await page.locator('nav.nav a.nav-item', { hasText: view.label }).click()

      await expect(page).toHaveURL(new RegExp(`${view.path}$`))
      await expect(page.locator('.topbar-title')).toHaveText(view.title)
      await expect(page.getByRole('heading', { level: 1 })).toHaveText(view.heading)
    }

    expect(pageErrors, 'no uncaught errors while navigating').toEqual([])
  })
})
