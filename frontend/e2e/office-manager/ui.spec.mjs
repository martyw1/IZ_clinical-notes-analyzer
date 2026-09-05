import { test, expect, login, fixtureContract, capture, writeEvidence } from './support/fixtures.mjs'

const widths = [375, 768, 1280]

async function captureWidths(page, name, records) {
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 })
    await page.evaluate(() => window.scrollTo(0, 0))
    const fits = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)
    records.push({ page: name, width, fits })
    await capture(page, `ui-${name}-${width}.png`)
    expect(fits, `${name} fits ${width}px`).toBe(true)
  }
}

test('navigation and populated records remain usable across screen sizes @happy @edge', async ({ page }) => {
  test.setTimeout(120_000)
  const records = []
  await page.goto('/')
  await captureWidths(page, 'login', records)
  await login(page, 'admin')
  const navigation = page.getByRole('navigation', { name: 'Primary navigation' })
  const views = await navigation.getByRole('button').allTextContents()
  for (const view of views) {
    await navigation.getByRole('button', { name: view, exact: true }).click()
    await expect(page.locator('main')).not.toBeEmpty()
    await expect(page.getByText(/^Loading[^\n]*\.\.\.$/)).toHaveCount(0)
    await captureWidths(page, view.toLowerCase().replaceAll(' ', '-'), records)
  }
  const plan = fixtureContract().plans.sourceCollision
  await navigation.getByRole('button', { name: 'Treatment Plans Roster', exact: true }).click()
  const row = page.locator(`tr[data-plan-version-id="${plan.plan_version_id}"]`)
  await row.getByRole('button', { name: `Open treatment plan ${plan.plan_id} for MRN ${plan.patient_id}`, exact: true }).click()
  await expect(page.locator('.criterion-row')).toHaveCount(42)
  await captureWidths(page, 'selected-plan', records)
  await navigation.getByRole('button', { name: 'Treatment Plans Roster', exact: true }).click()
  await row.getByRole('button', { name: /^Open patient record for/ }).click()
  await expect(page.getByLabel('Search patient information', { exact: true })).toBeVisible()
  await captureWidths(page, 'selected-patient', records)
  await page.getByRole('link', { name: 'Skip to content' }).focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('#main-content')).toBeFocused()
  await page.getByRole('button', { name: 'Sign out', exact: true }).click()
  await login(page, 'counselor')
  await navigation.getByRole('button', { name: 'Corrections', exact: true }).click()
  await expect(page.getByText(/^Loading[^\n]*\.\.\.$/)).toHaveCount(0)
  await captureWidths(page, 'corrections', records)
  writeEvidence('ui-surfaces.json', { records, skipNavigationWorks: true, roles: ['admin', 'counselor'], realBackend: true })
})

test('dashboard recovers after failed initial load and failed refresh @edge', async ({ page }) => {
  let failRequest = true
  await page.route('**/api/v2/dashboard', route => failRequest
    ? route.fulfill({ status: 503, contentType: 'application/json', body: '{}' })
    : route.continue())
  await login(page)
  await expect(page.getByRole('alert')).toBeVisible()
  await capture(page, 'ui-dashboard-initial-error.png')
  failRequest = false
  await page.getByRole('button', { name: 'Refresh dashboard', exact: true }).click()
  await expect(page.locator('.metric-tile')).toHaveCount(9)
  await expect(page.getByRole('alert')).toHaveCount(0)
  const previousCounts = await page.locator('.metric-tile dd').allTextContents()
  failRequest = true
  await page.getByRole('button', { name: 'Refresh dashboard', exact: true }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  await expect(page.locator('.metric-tile dd')).toHaveText(previousCounts)
  await capture(page, 'ui-dashboard-refresh-error.png')
  failRequest = false
  await page.getByRole('button', { name: 'Refresh dashboard', exact: true }).click()
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Refresh dashboard', exact: true })).toBeEnabled()
  await page.getByText('How these counts are calculated', { exact: true }).click()
  await expect(page.getByText(/not a partition/)).toBeVisible()
  await capture(page, 'ui-dashboard-recovered.png')
  writeEvidence('ui-dashboard-recovery.json', { simulated503: true, actualBackendRecovery: true, initialRetry: true, refreshRetry: true, previousCountsRetained: true })
})
