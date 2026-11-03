import { expect, test } from '@playwright/test'

/**
 * Catalog cases:
 *   ui.dashboard.kpis
 *   ui.dashboard.run_detail
 */
const KPI_LABELS = [
  'Total automated tests',
  'Passed',
  'Failed',
  'API p95 latency',
  'Avg page load',
  'Load error rate',
  'Data validation failures',
  'Active gate failures'
]

test.describe('Quality dashboard', () => {
  test('renders every KPI from live data', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { level: 1, name: 'Quality Dashboard' })).toBeVisible()

    for (const label of KPI_LABELS) {
      const card = page.locator('.kpi', { hasText: label })
      await expect(card, `KPI ${label} must be rendered`).toHaveCount(1)
      await expect(card.locator('.kpi-value')).not.toHaveText('—')
    }

    // The KPI grid is fed by /api/dashboard/summary, so a numeric total proves
    // the request succeeded rather than rendering placeholders.
    const total = page.locator('.kpi', { hasText: 'Total automated tests' }).locator('.kpi-value')
    await expect(total).toHaveText(/^[\d,]+$/)

    await expect(page.getByRole('heading', { name: 'Execution trend' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Recent executions' })).toBeVisible()
  })

  test('opens a run detail with gates, results and reports', async ({ page }) => {
    await page.goto('/dashboard')

    const firstRun = page.locator('table tbody tr a', { hasText: /^RUN-/ }).first()
    await expect(firstRun).toBeVisible()
    const runKey = (await firstRun.textContent()).trim()

    await firstRun.click()

    await expect(page).toHaveURL(new RegExp(`/runs/${runKey}$`))
    await expect(page.getByRole('heading', { level: 1 })).toHaveText(runKey)

    await expect(page.getByRole('heading', { name: 'Quality gates' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible()
    await expect(page.locator('.gate-row').first()).toBeVisible()

    // Re-evaluating recomputes the gates from the persisted results.
    await page.getByTestId('reevaluate-gates').click()
    await expect(page.getByText('Quality gates recomputed from the persisted results.')).toBeVisible()

    const resultRows = page.locator('table tbody tr')
    await expect(resultRows.first()).toBeVisible()
    expect(await resultRows.count()).toBeGreaterThan(0)
  })
})
