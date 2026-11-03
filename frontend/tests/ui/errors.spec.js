import { expect, test } from '@playwright/test'

/**
 * Catalog case: ui.errors.unknown_run
 *
 * Unknown identifiers must degrade to an explicit, recoverable error state
 * instead of a blank page or a crashed component.
 */
test.describe('Error handling', () => {
  test('an unknown run key shows a recoverable error', async ({ page }) => {
    await page.goto('/runs/RUN-19700101-0000-XXXX')

    const banner = page.getByRole('alert')
    await expect(banner).toBeVisible()
    await expect(banner).toContainText('Could not load this view.')
    await expect(banner).toContainText('Run RUN-19700101-0000-XXXX not found')

    // The retry control exists so the operator can recover after the data lands.
    await expect(banner.getByRole('button', { name: 'Retry' })).toBeVisible()

    // Unknown routes render the in-app 404 page, not a blank shell.
    await page.goto('/this-route-does-not-exist')
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Page not found')
    await expect(page.getByRole('link', { name: 'Go to dashboard' })).toBeVisible()
  })
})
