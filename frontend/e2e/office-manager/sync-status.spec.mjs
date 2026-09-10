import { test, expect, login, capture, writeEvidence } from './support/fixtures.mjs'

test.use({ timezoneId: 'America/New_York' })

for (const status of ['completed', 'failed']) {
  test(`saved sync ${status} status is readable after navigation @happy @edge`, async ({ page }) => {
    const message = status === 'failed' ? 'Alleva did not respond before the request timeout. Resume the sync safely.' : ''
    await page.route('**/api/v2/api-harness/jobs', route => route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify([{ job_id: 'synthetic-status', job_type: 'approved_treatment_plan_sync', status,
        phase: status, message, progress_percent: 100, records_seen: 395, records_written: 0,
        records_failed: 0, warnings_count: 0, errors_count: status === 'failed' ? 1 : 0,
        completed_at: status === 'completed' ? '2026-09-10T21:20:58.082903' : '', artifacts: [] }]),
    }))
    await login(page, 'admin')
    await page.getByRole('button', { name: 'Settings', exact: true }).click()
    if (status === 'failed') await expect(page.getByRole('alert')).toHaveText(message)
    else await expect(page.getByText(/Last run completed/)).toHaveText('Last run completed 2026-09-10 21:20 UTC.')
    const views = []
    for (const width of [375, 768, 1280]) {
      await page.setViewportSize({ width, height: 900 })
      await page.locator('.compact-job-status').scrollIntoViewIfNeeded()
      const fits = await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)
      expect(fits).toBe(true)
      await capture(page, `sync-status-${status}-${width}.png`)
      views.push({ width, fits })
    }
    await page.getByRole('button', { name: 'Help', exact: true }).click()
    await page.getByRole('button', { name: 'Settings', exact: true }).click()
    if (status === 'failed') await expect(page.getByRole('alert')).toHaveText(message)
    else await expect(page.getByText(/Last run completed/)).toContainText('21:20 UTC')
    writeEvidence(`sync-status-${status}.json`, { status, views, simulatedJobResponse: true, navigationPreservesStatus: true })
  })
}
