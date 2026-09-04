import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import path from 'node:path'
import { test, expect, login, apiFor, fixtureContract, capture, writeEvidence } from './support/fixtures.mjs'

const N = 'Needs Review', M = 'Missing Data', P = 'Present', C = 'Compliant', U = 'Unable to Evaluate', A = 'Not Applicable', R = 'Current/Compliant'
// Literal per-input oracle: criterion, empty/partial/full statuses, partial/full observed support.
const oracle = [
  ['confirm_correct_client_chart', N, N, N, false, false],
  ['classify_new_or_update_review', N, N, N, false, false],
  ['confirm_client_active', N, N, N, false, false],
  ['confirm_admission_date', M, P, P, true, true],
  ['confirm_current_loc', M, M, P, false, true],
  ['confirm_loc_rule_mapping', M, M, P, false, true],
  ['capture_loc_history', N, N, N, false, false],
  ['classify_source_documents', N, N, N, false, false],
  ['confirm_document_dates', N, N, N, false, false],
  ['confirm_document_completion_status', N, N, N, false, false],
  ['confirm_staff_signature_status', M, M, P, false, true],
  ['confirm_client_signature_status', N, N, N, false, false],
  ['check_conflicting_evidence', C, C, C, true, true],
  ['initial_plan_exists', M, M, P, false, true],
  ['initial_plan_dated_correctly', M, M, C, true, true],
  ['initial_plan_required_signatures', M, M, C, true, true],
  ['master_plan_exists', M, M, P, false, true],
  ['master_plan_within_30_days', M, M, C, true, true],
  ['master_plan_required_signatures', M, M, P, false, true],
  ['latest_valid_review_identified', M, P, P, true, true],
  ['calculate_next_review_due_date', U, U, R, true, true],
  ['apply_php_timing_rule', A, A, R, false, false],
  ['apply_iop_op_timing_rule', A, A, A, false, false],
  ['mark_current_inside_window', A, A, R, false, false],
  ['mark_due_soon', A, A, A, false, false],
  ['mark_overdue', A, A, A, false, false],
  ['check_php_individual_session_evidence', N, N, N, false, false],
  ['check_iop_op_individual_session_evidence', N, N, N, false, false],
  ['identify_loc_change', A, A, A, false, true],
  ['loc_change_update_document', A, A, A, false, false],
  ['loc_change_deadline_unresolved', A, A, A, false, false],
  ['flag_missing_data_not_compliance', M, M, C, false, false],
  ['allow_manual_reviewer_confirmation', N, N, N, false, false],
  ['require_manual_override_reason', N, N, N, false, false],
  ['produce_final_checklist_result', M, M, R, false, false],
  ['update_status_worklist_after_review', N, N, N, false, false],
  ['route_chart_for_manager_review', N, N, N, false, false],
  ['return_chart_with_correction_comments', N, N, N, false, false],
  ['approve_after_issues_resolved_or_accepted', N, N, N, false, false],
  ['preserve_review_history', N, N, N, false, false],
  ['continue_periodic_api_monitoring', N, N, N, false, false],
  ['use_synthetic_or_approved_non_phi_data', N, N, N, false, false],
]
const metricOracle = { active_patient_ids: 3, overdue_plans: 1, urgent_plans: 1, due_soon_plans: 1,
  needs_review: 1, missing_data: 57, returned: 1, conflicting: 1, unable: 1 }
const labels = ['Patient records with plans', 'Overdue plans', 'Urgent plans', 'Due soon plans', 'Plans needing review',
  'Missing Data criteria', 'Open correction items', 'Plans with conflicting evidence', 'Plans unable to evaluate']
const cases = [['overdue', -31, 'Overdue'], ['urgent', -30, 'Urgent'], ['dueSoon', -27, 'Due Soon'],
  ['full', -16, R], ['needsReview', -16, N], ['conflicting', -16, 'Conflicting Evidence'], ['unable', -16, U],
  ['missing', -16, M], ['empty', -16, M], ['partial', -16, M]]
const selector = plan => ({ plan_version_id: plan.plan_version_id, patient_record_id: plan.patient_record_id, source_mode: plan.source_mode })
const localDay = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
const shifted = (day, offset) => new Date(Date.parse(`${day}T12:00:00Z`) + offset * 86400000).toISOString().slice(0, 10)
let seededState

function failureBoundary(error, name) {
  const scopedFrames = [...String(error?.stack ?? '').matchAll(/metrics\.spec\.mjs:\d+:\d+/g)].map(match => match[0])
  writeEvidence(`task-8-failure-${name}.json`, { scopedFrames, rawErrorContentOmitted: true })
}

async function servedBundle(api, name) {
  const dist = path.join(process.env.IZ_OM_REPO_ROOT, 'frontend/dist')
  const index = readFileSync(path.join(dist, 'index.html'), 'utf8')
  const paths = ['/', ...[...index.matchAll(/(?:src|href)="(\/assets\/[^\"]+)"/g)].map(match => match[1])]
  const files = []
  for (const url of paths) {
    const response = await api.get(url)
    writeEvidence(`task-8-served-${name}.json`, { stage: 'response', url, status: response.status(), files })
    expect(response.status()).toBe(200)
    const served = await response.body()
    const actual = createHash('sha256').update(served).digest('hex')
    const raw = readFileSync(path.join(dist, url === '/' ? 'index.html' : url.slice(1)))
    const diskSha256 = createHash('sha256').update(raw).digest('hex')
    const representation = url === '/' ? Buffer.from(raw.toString('utf8').replace(/\r\n|\r/g, '\n')) : raw
    const expected = createHash('sha256').update(representation).digest('hex')
    writeEvidence(`task-8-served-${name}.json`, { stage: 'hash-check', url, actual, expected, files })
    expect(actual, `Served build asset ${url}`).toBe(expected)
    files.push({ url, actual, expected, diskSha256, diskBytes: raw.length, servedBytes: served.length,
      expectedBytes: representation.length, contentLength: response.headers()['content-length'], contentType: response.headers()['content-type'],
      transformation: url === '/' ? 'Python read_text universal newlines' : 'none' })
  }
  expect(files).toHaveLength(3)
  writeEvidence(`task-8-served-${name}.json`, { files, allServedBytesMatchExpectedRepresentation: true, htmlRawIdentityClaimed: false })
}

function payloadFor(template, kind, day, offset, suffix) {
  const payload = structuredClone(template), admission = shifted(day, offset), sparse = ['empty', 'partial'].includes(kind)
  payload.source_last_updated = `${day}T12:00:00Z`
  payload.treatment_review_data_status = 'task8_structured_synthetic'
  payload.admission_date = kind === 'empty' ? '' : admission
  payload.current_level_of_care = sparse ? 'Unknown' : 'PHP'
  payload.source_due_date = sparse ? '' : kind === 'unable' ? 'not-a-date' : shifted(admission, kind === 'conflicting' ? 31 : 30)
  payload.treatment_plans = sparse ? [] : [{ plan_id: `task8-${suffix}`, plan_kind: 'initial_plan', plan_date: admission }]
  payload.active_treatment_plans = payload.treatment_plans
  payload.treatment_reviews = []
  payload.loc_history = sparse ? [] : [{ level_of_care: 'PHP', effective_date: admission }]
  payload.source_evidence = []
  payload.evidence_coverage_summary.criteria_conflicting = 0
  payload.content_snapshot.plan_id = `task8-${suffix}`
  payload.content_snapshot.signatures = sparse ? [] : ['initial_plan', 'master_plan'].filter(role => kind !== 'missing' || role !== 'initial_plan').map(role => ({
    signature_type: role, evidence_role: role, has_signature_data: true, signer_role_or_type: 'clinician',
    signature_datetime: shifted(admission, kind === 'needsReview' && role === 'initial_plan' ? 1 : 0),
    signature_data_length: 0, signature_data_omitted_reason: 'synthetic metadata only', source_json_path: `source.signatures.${role}`,
  }))
  return payload
}

async function detail(api, plan) {
  const response = await api.get(`/api/v2/treatment-plans/${plan.patient_id}/${plan.plan_id}`, { params: selector(plan) })
  expect(response.status()).toBe(200)
  const result = await response.json()
  expect(result.plan_version_id).toBe(plan.plan_version_id)
  return result
}

async function seed(api) {
  if (seededState) return seededState
  const fixture = fixtureContract(), day = localDay(), template = JSON.parse(readFileSync(fixture.files.aggregate, 'utf8')), plans = {}
  writeEvidence('task-8-fixture-oracle.json', { day, timezone: 'America/New_York', cases, metricOracle, oracle,
    assumptions: 'Dedicated fresh metrics scenario: four initial latest plans / three authorized rows; each initial plan has seven Missing Data criteria. New incomplete plans add 5 + 13 + 11. No app response builds expected values.' })
  for (const [kind, offset, status] of [['historical', -31, 'Overdue'], ...cases]) {
    const suffix = kind === 'historical' ? 'full' : kind
    const response = await api.post('/api/v2/manual-uploads/treatment-plan-aggregate', { data: payloadFor(template, kind, day, offset, suffix) })
    expect(response.status()).toBe(201)
    plans[kind] = { ...await response.json(), plan_id: `task8-${suffix}` }
    expect((await detail(api, plans[kind])).overall_status, kind).toBe(status)
  }
  const returned = await api.post(`/api/v2/treatment-plans/${fixture.plans.primaryV1.patient_id}/manager-actions`, { data: {
    ...selector(fixture.plans.primaryV1), criterion_id: 'confirm_current_loc', action: 'return_for_correction',
    assigned_counselor_username: fixture.users.counselor.username, comment: 'Synthetic Task 8 historical correction.',
  } })
  expect(returned.status()).toBe(200)
  const rowsResponse = await api.get('/api/v2/treatment-plans')
  expect(rowsResponse.status()).toBe(200)
  const actualIds = (await rowsResponse.json()).items.map(row => row.plan_version_id).sort((a, b) => a - b)
  const expectedIds = [fixture.plans.primaryV2, fixture.plans.secondaryPlan, fixture.plans.patientTwo, fixture.plans.sourceCollision,
    ...cases.map(([kind]) => plans[kind])].map(row => row.plan_version_id).sort((a, b) => a - b)
  expect(actualIds).toEqual(expectedIds)
  writeEvidence('task-8-population.json', { expectedIds, actualIds, excludedHistorical: plans.historical.plan_version_id,
    deniedFacility: fixture.plans.facilityCollision.plan_version_id, correctedHistorical: fixture.plans.primaryV1.plan_version_id })
  seededState = { day, plans, fixture }
  return seededState
}

async function surfaces(page, name) {
  const states = []
  for (const width of [375, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 })
    const fits = await page.evaluate(() => ({ document: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
      body: document.body.scrollWidth <= document.body.clientWidth }))
    await capture(page, `task-8-${name}-${width}.png`)
    states.push({ width, ...fits })
    expect(fits.document && fits.body, `${name} fits ${width}`).toBe(true)
  }
  writeEvidence(`task-8-${name}-layout.json`, { states })
}

async function dashboard(page, api) {
  const response = await api.get('/api/v2/dashboard')
  expect(response.status()).toBe(200)
  expect((await response.json()).metrics).toEqual(metricOracle)
  await page.getByRole('button', { name: 'Status Dashboard', exact: true }).click()
  await expect(page.locator('.metric-tile dt')).toHaveText(labels)
  await expect(page.locator('.metric-tile dd')).toHaveText(['3', '1', '1', '1', '1', '57', '1', '1', '1'])
  await expect(page.getByText(/not active-client lifecycle counts/)).toBeVisible()
  await expect(page.getByText(/counts are not a partition/)).toBeVisible()
  await surfaces(page, 'dashboard')
  const refresh = page.getByRole('button', { name: 'Refresh dashboard', exact: true })
  await refresh.hover()
  await capture(page, 'task-8-dashboard-hover.png')
  await refresh.focus()
  const beforeKeyboard = await refresh.evaluate(button => ({ focused: document.activeElement === button, focusVisible: button.matches(':focus-visible') }))
  await page.keyboard.press('Shift+Tab')
  await page.keyboard.press('Tab')
  const focusState = await refresh.evaluate(button => { const style = getComputedStyle(button); return { focused: document.activeElement === button,
    focusVisible: button.matches(':focus-visible'), outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, boxShadow: style.boxShadow } })
  const visibleFocus = (focusState.outlineStyle !== 'none' && parseFloat(focusState.outlineWidth) > 0) || focusState.boxShadow !== 'none'
  writeEvidence('task-8-focus-observation.json', { beforeKeyboard, afterKeyboard: focusState, visibleFocus })
  expect(focusState.focused, 'Keyboard traversal returns to Refresh dashboard').toBe(true)
  expect(visibleFocus, 'Dashboard keyboard focus is visible').toBe(true)
  await capture(page, 'task-8-dashboard-focus.png')
  const refreshed = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v2/dashboard')
  await page.keyboard.press('Enter')
  expect((await (await refreshed).json()).metrics).toEqual(metricOracle)
  await page.mouse.move(0, 0)
  await refresh.blur()
  await capture(page, 'task-8-dashboard-settled.png')
  writeEvidence('task-8-metrics.json', { metrics: metricOracle, realBackend: true, fixtureOracleMatched: true, keyboardRefresh: true, visibleFocus })
}

async function coverage(page, api, plan, kind) {
  const data = await detail(api, plan), column = { empty: 1, partial: 2, full: 3 }[kind]
  const expected = oracle.map(row => ({ criterion: row[0], status: row[column], observed: kind === 'empty' ? false : row[column + 2] }))
  const actual = data.criteria_results.map(row => ({ criterion: row.criterion_id, status: row.result_status, observed: row.evidence_refs.length > 0 }))
  writeEvidence(`task-8-coverage-api-${kind}.json`, { expected, actual })
  expect(actual).toEqual(expected)
  const totals = { empty: [42, 0, 13, 0, 1, 8], partial: [42, 7, 11, 0, 1, 8], full: [42, 14, 0, 0, 0, 6] }[kind]
  expect([data.evidence_coverage_summary.criteria_total, data.evidence_coverage_summary.criteria_with_evidence,
    data.evidence_coverage_summary.criteria_missing_evidence, data.evidence_coverage_summary.criteria_conflicting]).toEqual(totals.slice(0, 4))
  await page.getByRole('button', { name: 'Treatment Plans Roster', exact: true }).click()
  await page.getByRole('button', { name: `Open treatment plan ${plan.plan_id} for MRN ${plan.patient_id}`, exact: true }).click()
  await expect(page.locator('.criterion-row')).toHaveCount(42)
  for (let index = 0; index < 42; index += 1) {
    const row = page.locator('.criterion-row').nth(index)
    await row.click()
    await expect(row).toHaveAttribute('aria-pressed', 'true')
    await expect(row.locator('.status-badge')).toHaveText(expected[index].status)
    await expect(page.locator('.evidence-panel')).toHaveAttribute('id', `evidence-${expected[index].criterion}`)
    const preview = page.locator('.evidence-panel dd').nth(1)
    if (expected[index].observed) await expect(preview).toContainText('Observed source input.')
    else await expect(preview).toHaveText('Not supplied')
  }
  await page.locator('.criterion-row').nth(14).click()
  const summary = page.locator('.evidence-coverage-summary')
  await expect(summary.locator('.evidence-coverage-metric > span:first-child').filter({ hasText: /^Result status: Missing Data$/ })).toHaveCount(1)
  await expect(summary.locator('.evidence-coverage-metric > span:last-child')).toHaveText([...totals.map(String), '0'])
  await expect(page.getByText(/subtotals can overlap and do not partition the 42 criteria/)).toBeVisible()
  const locClock = page.locator('.source-comparison-grid > div').filter({ has: page.getByText('LOC-change clock', { exact: true }) })
  await expect(locClock.getByText('Unvalidated — configurable', { exact: true })).toBeVisible()
  writeEvidence(`task-8-coverage-${kind}.json`, { expected, actual, totals, criteriaClicked: 42, realBackend: true })
  await surfaces(page, `coverage-${kind}`)
  await page.locator('.evidence-panel').screenshot({ path: path.join(process.env.IZ_OM_EVIDENCE_DIR, `task-8-day-one-${kind}.png`), animations: 'disabled' })
  await summary.locator('xpath=..').screenshot({ path: path.join(process.env.IZ_OM_EVIDENCE_DIR, `task-8-summary-${kind}.png`), animations: 'disabled' })
}

test('truthful mixed-unit dashboard and full source coverage @happy', async ({ page }) => {
  test.setTimeout(180_000)
  writeEvidence('task-8-stage-happy.json', { stage: 'before-api-context' })
  const api = await apiFor()
  try {
    writeEvidence('task-8-stage-happy.json', { stage: 'api-context-established' })
    await servedBundle(api, 'happy-before')
    const seeded = await seed(api)
    await login(page)
    await dashboard(page, api)
    await coverage(page, api, seeded.plans.full, 'full')
    expect(localDay(), 'Facility day must not roll over during the fixture').toBe(seeded.day)
    await servedBundle(api, 'happy-after')
  } catch (error) { failureBoundary(error, 'happy'); throw error } finally { await api.dispose() }
})

test('empty partial uncertain historical and unauthorized evidence stay distinct @edge', async ({ page }) => {
  test.setTimeout(180_000)
  writeEvidence('task-8-stage-edge.json', { stage: 'before-api-context' })
  const api = await apiFor(), counselor = await apiFor('counselor')
  try {
    writeEvidence('task-8-stage-edge.json', { stage: 'api-context-established' })
    await servedBundle(api, 'edge-before')
    const seeded = await seed(api)
    await login(page)
    await dashboard(page, api)
    for (const kind of ['empty', 'partial']) await coverage(page, api, seeded.plans[kind], kind)
    const denied = await api.get(`/api/v2/treatment-plans/${seeded.fixture.plans.facilityCollision.patient_id}`, { params: selector(seeded.fixture.plans.facilityCollision) })
    expect(denied.status()).toBe(403)
    for (const kind of ['conflicting', 'unable']) {
      const data = await detail(api, seeded.plans[kind])
      expect(data.criteria_results.find(row => row.criterion_id === 'check_conflicting_evidence').evidence_refs.some(ref => ref.source_json_path === 'source_due_date')).toBe(true)
    }
    const queue = await counselor.get('/api/v2/corrections'), item = (await queue.json()).items.find(row => row.plan_version_id === seeded.fixture.plans.primaryV1.plan_version_id)
    expect(item).toBeDefined()
    const submitted = await counselor.post(`/api/v2/treatment-plans/${item.patient_id}/correction-submissions`, { data: {
      work_item_id: item.work_item_id, criterion_id: item.criterion_id, comment: 'Synthetic Task 8 correction submitted.',
    } })
    expect(submitted.status()).toBe(200)
    expect((await (await api.get('/api/v2/dashboard')).json()).metrics).toEqual({ ...metricOracle, returned: 0 })
    writeEvidence('task-8-metrics-error.json', { deniedStatus: denied.status(), actualUncertainSourceRetained: true,
      partialMissingStatusRetained: true, historicalOpenItemCounted: true, closedItemExcluded: true, realBackend: true })
    expect(localDay()).toBe(seeded.day)
    await servedBundle(api, 'edge-after')
  } catch (error) { failureBoundary(error, 'edge'); throw error } finally { await api.dispose(); await counselor.dispose() }
})
