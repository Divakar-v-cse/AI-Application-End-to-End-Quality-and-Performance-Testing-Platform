import { expect, test } from '@playwright/test'

/**
 * Catalog case: ui.forms.run_validation
 *
 * The dashboard run form must only offer valid suites, submit the selected
 * suite, and surface the execution outcome with per-suite results.
 */
test.describe('Run form', () => {
  test('validates the suite selection and reports the execution outcome', async ({ page }) => {
    await page.goto('/dashboard')

    const suite = page.getByTestId('run-suite')
    const options = await suite.locator('option').evaluateAll((nodes) => nodes.map((node) => node.value))
    expect(options.sort()).toEqual(['all', 'api', 'db', 'perf', 'ui'])

    // The database suite is always runnable (the UI runner needs browsers).
    await suite.selectOption('db')
    await expect(suite).toHaveValue('db')

    await page.getByTestId('run-suite-button').click()

    const outcome = page.getByTestId('run-outcome')
    await expect(outcome).toBeVisible({ timeout: 30_000 })
    await expect(outcome).toContainText(/RUN-\d{8}-\d{6}-[0-9A-F]{4}/)
    await expect(outcome).toContainText(/PASSED|FAILED|SKIPPED/)
    await expect(outcome).toContainText(/15\/15 passed/)

    // Filtering the history by suite narrows the table to that suite only.
    await page.goto('/runs')
    await expect(page.locator('table tbody tr').first()).toBeVisible()

    await page.getByTestId('filter-suite').selectOption('db')
    await expect(page.getByTestId('filter-suite')).toHaveValue('db')

    const rows = page.locator('table tbody tr')
    await expect(rows.first()).toBeVisible()
    const rowCount = await rows.count()
    expect(rowCount).toBeGreaterThan(0)
    for (const row of await rows.all()) {
      await expect(row).toContainText('db')
    }
  })
})
