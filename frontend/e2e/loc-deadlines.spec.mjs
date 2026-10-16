import { expect, test } from '@playwright/test'

test('saved latest-plan deadlines and earlier comments agree across the real API and desktop UI', async ({ page, request }) => {
  test.skip(process.env.IZ_CNA_E2E_SYNTHETIC_DEADLINES !== '1', 'Requires isolated synthetic deadline fixtures')
  const password = process.env.IZ_CNA_E2E_ADMIN_PASSWORD
  const login = await request.post('/api/auth/login', { data: { username: 'e2eadmin', password } })
  expect(login.ok()).toBeTruthy()
  const { access_token } = await login.json()
  const headers = { authorization: `Bearer ${access_token}` }
  const dashboard = await request.get('/api/v2/dashboard', { headers })
  expect((await dashboard.json()).metrics).toEqual({ overdue_plans: 1, due_soon_plans: 1 })
  const plans = await request.get('/api/v2/treatment-plans', { headers })
  const latest = (await plans.json()).items.find(item => item.patient_id === 'SYNTHETIC-BROWSER-DUE')
  expect(latest).toBeTruthy()

  await page.goto('/')
  await page.getByLabel('Username').fill('e2eadmin')
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.locator('[data-metric="overdue_plans"] dd')).toHaveText('1')
  await expect(page.locator('[data-metric="due_soon_plans"] dd')).toHaveText('1')
  await expect(page.getByRole('heading', { name: 'Workload' })).toHaveCount(0)
  await expect(page.locator('[data-metric="urgent_plans"]')).toHaveCount(0)
  for (let visit = 0; visit < 2; visit += 1) {
    if (visit) await page.reload()
    await page.getByRole('button', { name: 'Patient Roster', exact: true }).click()
    await page.getByRole('combobox', { name: 'Treatment plans for MRN SYNTHETIC-BROWSER-DUE' }).selectOption(String(latest.plan_version_id))
    await expect(page.getByRole('heading', { name: 'Treatment Plan ID synthetic-browser-plan' })).toBeVisible()
    await expect(page.getByText('Next update due (computed)', { exact: true }).locator('..').locator('dd')).toContainText(latest.next_due_date)
    await expect(page.getByRole('heading', { name: 'Comments from earlier versions of this plan' })).toBeVisible()
    await expect(page.getByText('Comment: Synthetic comment retained after plan update', { exact: true })).toHaveCount(1)
  }
})
