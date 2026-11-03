import { expect, test } from '@playwright/test'

/**
 * Catalog case: ui.reports.download
 *
 * Every run can be exported in five formats; the download must be a real file
 * whose name is derived from the run key.
 */
const FORMATS = [
  { testId: 'download-markdown', extension: 'md' },
  { testId: 'download-html', extension: 'html' },
  { testId: 'download-junit', extension: 'xml' },
  { testId: 'download-csv', extension: 'csv' },
  { testId: 'download-json', extension: 'json' }
]

test.describe('Report downloads', () => {
  test('every report format downloads for a run', async ({ page }) => {
    await page.goto('/runs')

    const firstRun = page.locator('table tbody tr a', { hasText: /^RUN-/ }).first()
    await expect(firstRun).toBeVisible()
    const runKey = (await firstRun.textContent()).trim()
    await firstRun.click()

    await expect(page.getByRole('heading', { level: 1 })).toHaveText(runKey)

    for (const format of FORMATS) {
      const link = page.getByTestId(format.testId)
      await expect(link).toBeVisible()

      const [download] = await Promise.all([page.waitForEvent('download'), link.click()])
      expect(download.suggestedFilename()).toBe(`${runKey}-report.${format.extension}`)

      const failure = await download.failure()
      expect(failure, `${format.testId} download failed: ${failure}`).toBeNull()
    }
  })
})
