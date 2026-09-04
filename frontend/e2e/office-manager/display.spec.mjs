import { test, expect, login, apiFor, fixtureContract, capture, writeEvidence } from './support/fixtures.mjs'

const widths = [375, 768, 1280]
const plan = fixtureContract().plans.sourceCollision
const actions = ['Approve criterion', 'Save comment', 'Return for correction', 'Save override']
test.use({ timezoneId: 'America/New_York' })

async function selectedRow(page) {
  await page.getByRole('button', { name: 'Treatment Plans Roster', exact: true }).click()
  const button = page.locator(`tr[data-plan-version-id="${plan.plan_version_id}"]`).getByRole('button', { name: `Open treatment plan ${plan.plan_id} for MRN ${plan.patient_id}`, exact: true })
  await expect(button).toBeVisible()
  return button.locator('xpath=ancestor::tr')
}
async function openPlan(page) {
  const row = await selectedRow(page)
  await row.getByRole('button', { name: `Open treatment plan ${plan.plan_id} for MRN ${plan.patient_id}`, exact: true }).click()
  await expect(page.locator('.criterion-row')).toHaveCount(42)
}
function expectedUtc(wire) {
  return new Date(wire.replace(' ', 'T') + (/(?:Z|[+-]\d{2}:\d{2})$/.test(wire) ? '' : 'Z'))
    .toISOString().slice(0, 16).replace('T', ' ') + ' UTC'
}
async function tabAudit(page) {
  const targets = page.locator('button:visible:enabled, input:visible:enabled, textarea:visible:enabled, select:visible:enabled, a[href]:visible, summary:visible')
  const eligible = await targets.count()
  await targets.first().focus()
  const reached = new Set([0])
  let missingIndicator = 0
  for (let index = 0; index <= eligible; index += 1) {
    await page.keyboard.press('Tab')
    const active = await targets.evaluateAll(nodes => {
      const index = nodes.indexOf(document.activeElement)
      const style = getComputedStyle(document.activeElement)
      return { index, indicator: (style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) > 0) || style.boxShadow !== 'none' }
    })
    if (active.index >= 0) { reached.add(active.index); if (!active.indicator) missingIndicator += 1 }
  }
  return { eligible, reached: reached.size, missingIndicator, allReached: reached.size === eligible }
}
async function surfaces(page, name) {
  const states = []
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 })
    const keyboard = await tabAudit(page)
    const fits = await page.evaluate(() => ({ document: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      body: document.body.scrollWidth <= document.body.clientWidth }))
    await capture(page, `task-5-${name}-${width}.png`)
    states.push({ width, ...fits, keyboard })
  }
  writeEvidence(`task-5-${name}-layout.json`, { states, inputMask: 'harness privacy overlay', interaction: 'Playwright keyboard' })
  for (const state of states) {
    expect(state.document && state.body, name + ' fits at ' + state.width).toBe(true)
    expect(state.keyboard.allReached, name + ' complete Tab traversal at ' + state.width).toBe(true)
    expect(state.keyboard.missingIndicator, name + ' visible focus at ' + state.width).toBe(0)
  }
  return states
}

test('populated Users cells retain readable labels at every width @happy @edge', async ({ page }) => {
  await login(page, 'admin')
  await page.getByRole('button', { name: 'Users', exact: true }).click()
  await expect(page.locator('.users-table tbody tr').first()).toBeVisible()
  const labels = []
  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 })
    labels.push({ width, values: await page.locator('.users-table tbody tr').first().locator('td').evaluateAll(cells =>
      cells.map(cell => ({ attribute: cell.getAttribute('data-label'), generated: getComputedStyle(cell, '::before').content }))) })
  }
  const states = await surfaces(page, 'users')
  writeEvidence('task-5-users.json', { realBackend: true, accountMutations: 0, labels, states })
  for (const state of labels) {
    expect(state.values.map(cell => cell.attribute)).toEqual(['User', 'Role', 'Status', 'Password reset', 'Action'])
    if (state.width < 900) expect(state.values.every(cell => cell.generated === '"' + cell.attribute + '"')).toBe(true)
  }
})

test('real audit timestamps retain their UTC clock values @happy @edge', async ({ page }) => {
  await login(page, 'admin')
  const response = page.waitForResponse(response => new URL(response.url()).pathname === '/api/audit/logs')
  await page.getByRole('button', { name: 'Forensic Logs', exact: true }).click()
  const wire = (await (await response).json()).items[0].timestamp_utc
  await expect(page.locator('.forensic-table time').first()).toBeVisible()
  const displayed = await page.locator('.forensic-table time').first().innerText()
  const states = await surfaces(page, 'logs')
  writeEvidence('task-5-audit-utc.json', { realBackend: true, wire, offsetPresent: /(?:Z|[+-]\d{2}:\d{2})$/.test(wire),
    displayed, expected: expectedUtc(wire), matches: displayed === expectedUtc(wire), timezone: 'America/New_York', states })
  expect(displayed === expectedUtc(wire), 'Audit UTC value matches actual wire').toBe(true)
})

test('Settings loads directly with reachable controls at every width @happy @edge', async ({ page }) => {
  await login(page, 'admin')
  await page.getByRole('button', { name: 'Settings', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Save settings', exact: true })).toBeEnabled()
  writeEvidence('task-5-settings.json', { realBackend: true, configurationMutations: 0, states: await surfaces(page, 'settings') })
})

test('real persisted manager history retains its UTC clock value @happy @edge', async ({ page }) => {
  const api = await apiFor()
  let wire
  try {
    const query = new URLSearchParams({ plan_version_id: String(plan.plan_version_id), patient_record_id: String(plan.patient_record_id), source_mode: plan.source_mode })
    const detailPath = `/api/v2/treatment-plans/${plan.patient_id}/${plan.plan_id}?${query}`
    const response = await api.get(detailPath)
    expect(response.status()).toBe(200)
    const before = await response.json()
    expect(before.manager_reviews.length).toBe(0)
    const saved = await api.post(`/api/v2/treatment-plans/${plan.patient_id}/manager-actions`, { data: {
      plan_version_id: plan.plan_version_id, patient_record_id: plan.patient_record_id, source_mode: plan.source_mode,
      treatment_plan_id: plan.plan_id, criterion_id: before.criteria_results[0].criterion_id,
      action: 'comment', comment: 'Synthetic presentation UTC check.', override_reason: '',
    } })
    expect(saved.status()).toBe(200)
    wire = (await (await api.get(detailPath)).json()).manager_reviews[0].created_at
  } finally { await api.dispose() }
  writeEvidence('task-5-manager-wire.json', { realBackend: true, wire, planVersionId: plan.plan_version_id, syntheticCommentsCreated: 1 })
  await login(page)
  await openPlan(page)
  const history = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Persisted manager actions', exact: true }) })
  await expect(history.locator('.artifact-list li')).toHaveCount(1)
  const displayed = (await history.locator('.artifact-list li').innerText()).match(/\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC/)?.[0] ?? ''
  await capture(page, 'task-5-manager-utc.png')
  writeEvidence('task-5-manager-utc.json', { realBackend: true, wire, displayed, expected: expectedUtc(wire),
    matches: displayed === expectedUtc(wire), offsetPresent: /(?:Z|[+-]\d{2}:\d{2})$/.test(wire), planVersionId: plan.plan_version_id })
  expect(displayed === expectedUtc(wire), 'Manager history UTC value matches freshly loaded wire').toBe(true)
})

test('real detail exposes 42 criteria and only four safe search fields @happy @edge', async ({ page }) => {
  await login(page)
  await openPlan(page)
  const rows = page.locator('.criterion-row')
  const fields = []
  for (let index = 0; index < 42; index += 1) {
    await rows.nth(index).click()
    await expect(rows.nth(index)).toHaveAttribute('aria-pressed', 'true')
    const title = await rows.nth(index).locator('span').first().innerText()
    await expect(page.locator('.evidence-panel h3')).toHaveText(title)
    fields.push({ title, finding: await page.locator('.evidence-finding span').innerText(),
      path: await page.locator('.evidence-panel dd').nth(0).innerText(), preview: await page.locator('.evidence-panel dd').nth(1).innerText() })
  }
  const search = page.getByLabel('Search checklist evidence', { exact: true })
  const results = []
  for (const field of ['title', 'finding', 'preview', 'path']) {
    const source = fields.find(item => item[field] !== 'Not supplied' && /[a-z]/i.test(item[field]))
    expect(Boolean(source), 'Real searchable field exists: ' + field).toBe(true)
    await search.fill(source[field].toUpperCase())
    const matched = (await rows.locator('span:first-child').allTextContents()).includes(source.title)
    results.push({ field, count: await rows.count(), matched })
    expect(matched, 'Case-insensitive real evidence field: ' + field).toBe(true)
  }
  const clinical = await page.locator('.clinical-overview-grid dd').first().innerText()
  expect(clinical !== 'Not supplied' && clinical.length > 5, 'Actual rendered clinical source exists').toBe(true)
  expect(fields.every(item => Object.values(item).every(value => !value.toLowerCase().includes(clinical.toLowerCase()))),
    'Actual clinical value occurs only in clinical source, not the four safe fields').toBe(true)
  await search.fill(clinical.toUpperCase())
  await expect(rows).toHaveCount(0)
  await search.fill('')
  await expect(rows).toHaveCount(42)
  await expect(page.locator('.criterion-row[aria-pressed=true]')).toHaveCount(1)
  const metadata = page.locator('.signature-metadata').first()
  await expect(metadata.locator('dt')).toHaveText(['Signature type', 'Signer role or type', 'Signature date', 'Explanation'])
  await expect(page.locator('.clinical-overview-grid').getByText('Not supplied', { exact: true }).first()).toBeVisible()
  const time = metadata.locator('time')
  const signatureWire = await time.getAttribute('datetime')
  expect(await time.innerText()).toBe(new Date(signatureWire).toISOString().slice(0, 16).replace('T', ' ') + ' UTC')
  writeEvidence('task-5-detail.json', { realBackend: true, criteriaClicked: fields.length, results,
    actualClinicalOverviewExcluded: true, selectionRestored: true, signatureSemanticFields: 4, signatureWire,
    states: await surfaces(page, 'detail') })
})

for (const state of ['populated', 'absent', 'no-match', 'error']) {
  test(`selected patient presentation: ${state} ${['populated', 'absent'].includes(state) ? '@happy @edge' : '@edge'}`, async ({ page }) => {
    await login(page)
    let intercepted = 0
    await page.route(url => url.pathname === `/api/v2/patients/${plan.patient_id}` && url.searchParams.get('source_mode') === plan.source_mode && url.searchParams.get('patient_record_id') === String(plan.patient_record_id), route => {
      if (route.request().method() !== 'GET') return route.continue()
      intercepted += 1
      return route.fulfill({ status: state === 'error' ? 503 : 200, contentType: 'application/json', body: JSON.stringify(state === 'error'
        ? { detail: 'Synthetic selected patient unavailable.' }
        : { patient_record_id: plan.patient_record_id, mrn: plan.patient_id, full_name: 'Synthetic presentation patient', source_mode: plan.source_mode, lifecycle_state: 'active',
          current_level_of_care: 'PHP', source_last_updated: '2026-09-01T12:00:00Z', first_seen_at: '2026-08-01T12:00:00Z',
          last_seen_at: '2026-09-01T12:00:00Z', reconciled_at: '2026-09-01T12:00:00Z', treatment_plans: [],
          patient_record: state === 'absent' ? {} : { identity: { full_name: 'Synthetic presentation patient' }, care: { level_of_care: 'PHP' } } }) })
    })
    const row = await selectedRow(page)
    await row.getByRole('button', { name: `Open patient record for Name unavailable, MRN ${plan.patient_id}`, exact: true }).click()
    if (state === 'error') await expect(page.getByRole('alert')).toBeVisible()
    else {
      await expect(page.getByLabel('Search patient information', { exact: true })).toBeVisible()
      if (state === 'no-match') await page.getByLabel('Search patient information', { exact: true }).fill('zz-no-patient-fields')
      if (state === 'absent') await expect(page.getByText('No patient snapshot is available for this record.', { exact: true })).toBeVisible()
      if (state === 'no-match') await expect(page.getByText('No patient fields match the current search.', { exact: true })).toBeVisible()
      if (state === 'populated') await expect(page.locator('.patient-record-document dl').getByText('Synthetic presentation patient', { exact: true })).toBeVisible()
    }
    await expect(page.getByText('Loading patient record...', { exact: true })).toHaveCount(0)
    writeEvidence(`task-5-patient-${state}.json`, { mockedPresentation: true, backendIntegrationClaimed: false,
      mockedMethod: 'GET', mockedPath: `/api/v2/patients/${plan.patient_id}?patient_record_id=${plan.patient_record_id}&source_mode=${plan.source_mode}`, intercepted,
      states: await surfaces(page, 'patient-' + state) })
    expect(intercepted).toBeGreaterThan(0)
  })
}

test('zero evidence matches disable all four actions and emit zero POSTs @edge', async ({ page }) => {
  await login(page)
  await openPlan(page)
  let posts = 0
  await page.route('**/api/**', route => {
    if (route.request().method() === 'POST') { posts += 1; return route.abort('blockedbyclient') }
    return route.continue()
  })
  await page.getByLabel('Manager comment', { exact: true }).fill('Synthetic guard check.')
  await page.getByLabel('Override reason', { exact: true }).fill('Synthetic guard reason.')
  await page.getByLabel('Search checklist evidence', { exact: true }).fill('zz-no-such-evidence')
  await expect(page.locator('.criterion-row')).toHaveCount(0)
  const observed = []
  for (const name of actions) {
    const button = page.getByRole('button', { name, exact: true })
    await expect(button).toBeDisabled()
    await button.click({ force: true })
    await button.evaluate(element => element.click())
    observed.push({ name, disabled: await button.isDisabled(), forcedPlaywrightClickAttempted: true, domClickAttempted: true })
  }
  await surfaces(page, 'detail-no-match')
  expect(posts).toBe(0)
  await page.getByLabel('Search checklist evidence', { exact: true }).fill('')
  await expect(page.locator('.criterion-row[aria-pressed=true]')).toHaveCount(1)
  for (const name of actions) await expect(page.getByRole('button', { name, exact: true })).toBeEnabled()
  writeEvidence('task-5-disabled-actions.json', { realBackendDetail: true, failClosedPostGuard: true, observed, posts, selectionRestored: true })
})
