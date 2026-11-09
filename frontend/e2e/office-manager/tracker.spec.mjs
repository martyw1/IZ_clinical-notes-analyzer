import { test, expect, login, apiFor } from './support/fixtures.mjs'
import { importAggregate, planRow } from './task7TestUtils.mjs'

test('manager reviews an overdue plan from the dashboard and finds it in reviewed rows @happy', async ({ page }) => {
  const api = await apiFor()
  try {
    const overdueDate = new Date(Date.now() - 90 * 86_400_000).toISOString()
    const saved = await importAggregate(api, {
      patientId: 'SYNTHETIC-TRACKER-REVIEW', planId: 'synthetic-tracker-review', stamp: overdueDate,
    })
    await login(page)
    const dashboardTile = page.locator('[data-metric="overdue_plans"]')
    const count = await dashboardTile.getByRole('button', { name: 'Overdue plans' }).textContent()
    await dashboardTile.getByRole('button', { name: 'Overdue plans' }).click()
    await expect(page.getByLabel('Worklist')).toHaveValue('Overdue')
    const row = planRow(page, saved)
    await row.getByRole('button', { name: /Open treatment plan synthetic-tracker-review/ }).click()
    await page.getByRole('button', { name: 'Mark overdue plan reviewed' }).click()
    await expect(page.getByText(/Reviewed on .* E[DS]T/)).toBeVisible()

    await page.getByRole('button', { name: 'Status Dashboard', exact: true }).click()
    await expect(dashboardTile.locator('dd')).toHaveText(count)
    await dashboardTile.getByRole('button', { name: 'Overdue plans' }).click()
    const reviewed = page.getByRole('button', { name: /Reviewed overdue/ })
    await expect(reviewed).toHaveAttribute('aria-expanded', 'false')
    await expect(row).toHaveCount(0)
    await reviewed.click()
    await expect(row.getByText('Yes', { exact: true })).toBeVisible()
  } finally {
    await api.dispose()
  }
})

test('manager can distinguish same-name counselors and open an exact caseload plan @happy', async ({ page }) => {
  const api = await apiFor()
  try {
    const response = await api.get('/api/v2/patient-roster')
    expect(response.ok()).toBeTruthy()
    const data = await response.json()
    const counselors = data.counselors.filter(({ name }) => name === 'Synthetic Tracker Counselor')
    expect(counselors).toHaveLength(2)
    const selected = counselors[0]
    const patient = data.items.find(row => row.primary_counselor_id === selected.id)

    await login(page)
    await page.getByRole('button', { name: 'Clinicians', exact: true }).click()
    await page.getByLabel('Search clinicians').fill('tracker counselor')
    await expect(page.getByRole('button', { name: /Synthetic Tracker Counselor/ })).toHaveCount(2)
    await page.getByRole('button', { name: `Synthetic Tracker Counselor (#${selected.id})`, exact: true }).click()
    await expect(page.getByRole('table', { name: 'Clinician caseload' }).getByRole('row')).toHaveCount(2)
    await page.getByRole('table', { name: 'Clinician caseload' }).getByRole('button', { name: patient.treatment_plans[0].treatment_plan_id }).click()
    await expect(page.getByLabel('Saved treatment-plan version')).toHaveValue(String(patient.treatment_plans[0].plan_version_id))
  } finally {
    await api.dispose()
  }
})
