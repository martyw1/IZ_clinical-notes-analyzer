import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { expect, fixtureContract, writeEvidence } from './support/fixtures.mjs'
import { startOwned, waitOwned, stopOwned } from './support/processes.mjs'

export const rosterSearchLabel = 'Search MRN, patient name, plan ID, reference, or service date'
export const csvHeaders = ['patient_id', 'plan_version_id', 'patient_record_id', 'treatment_plan_id', 'status',
  'current_level_of_care', 'admission_date', 'next_due_date', 'source_mode', 'version_ordinal',
  'missing_criteria_count', 'returned_criteria_count']

export function failureBoundary(error, scenario, phase) {
  const scenarios = ['roster-happy', 'roster-edge', 'metadata-happy', 'metadata-edge', 'selection-happy', 'selection-edge']
  const phases = ['initial-read', 'population-import', 'population-check', 'login', 'roster', 'source-filter',
    'local-filter', 'viewport-boundary', 'filtered-export', 'empty-export', 'denied-exports', 'patient-record',
    'assignment', 'help', 'binder-upload', 'supplied-metadata', 'omitted-metadata', 'source-isolation',
    'name-filter', 'patient-search', 'audit', 'source-import', 'source-memberships', 'source-detail',
    'source-download', 'source-ui', 'source-removal', 'source-post-delete', 'history', 'new-import',
    'manager-action', 'selected-csv', 'correction', 'late-read', 'late-save', 'session-expiry', 'mismatched-record']
  const stack = typeof error?.stack === 'string' ? error.stack : ''
  const framePattern = /(?:^|\n)[ \t]+at [^\r\n]*[/\\]frontend[/\\]e2e[/\\]office-manager[/\\]((?:roster|metadata|selection)\.spec\.mjs|task7TestUtils\.mjs):([1-9]\d{0,5}):([1-9]\d{0,5})\)?[ \t]*\r?(?=\n|$)/g
  const scopedFrames = [...new Set([...stack.matchAll(framePattern)].map(match => match[1] + ':' + match[2] + ':' + match[3]))].slice(0, 8)
  writeEvidence('task-7-failure-' + (scenarios.includes(scenario) ? scenario : 'unknown') + '.json',
    { phase: phases.includes(phase) ? phase : 'unknown', scopedFrames, rawErrorContentOmitted: true })
}

export function identity(plan) {
  for (const key of ['patient_record_id', 'plan_version_id']) {
    expect(Number.isSafeInteger(plan[key]) && plan[key] > 0, 'Positive exact ' + key).toBe(true)
  }
  expect(['manual_upload', 'alleva_rest_api']).toContain(plan.source_mode)
  const externalId = plan.treatment_plan_id ?? plan.plan_id
  expect(typeof externalId === 'string' && externalId.length > 0, 'External plan consistency ID').toBe(true)
  return { patient_record_id: plan.patient_record_id, plan_version_id: plan.plan_version_id,
    source_mode: plan.source_mode, treatment_plan_id: externalId }
}

export function query(plan) {
  return new URLSearchParams(Object.entries(identity(plan)).map(([key, value]) => [key, String(value)]))
}

export function assertQuery(url, plan) {
  const params = new URL(url).searchParams
  for (const [key, value] of Object.entries(identity(plan))) expect(params.get(key), key).toBe(String(value))
}

export function planPath(plan) {
  return '/api/v2/treatment-plans/' + encodeURIComponent(plan.patient_id) + '?' + query(plan)
}

export function hash(bytes) { return createHash('sha256').update(bytes).digest('hex') }
export function sortedIds(values) { return [...values].sort((left, right) => left - right) }

export async function detail(api, plan) {
  const response = await api.get(planPath(plan))
  expect(response.status(), 'Exact selected detail').toBe(200)
  const body = await response.json()
  expect(body.patient_record_id).toBe(plan.patient_record_id)
  expect(body.plan_version_id).toBe(plan.plan_version_id)
  expect(body.source_mode).toBe(plan.source_mode)
  expect(body.treatment_plan_id).toBe(identity(plan).treatment_plan_id)
  return body
}

export async function list(api) {
  const response = await api.get('/api/v2/treatment-plans')
  expect(response.status()).toBe(200)
  const body = await response.json()
  body.items.forEach(identity)
  return body.items
}

export async function importAggregate(api, { patientId, planId, fullName = '', reference = '', serviceDate = '', stamp = '2026-09-04T12:00:00Z' }) {
  const template = JSON.parse(readFileSync(fixtureContract().files.aggregate, 'utf8'))
  const payload = { ...template, patient_id: patientId, patient_display_label: 'MRN ' + patientId,
    patient_full_name: fullName, source_mode: 'manual_upload', source_last_updated: stamp,
    content_snapshot: { ...template.content_snapshot, patient_id: patientId, plan_id: planId,
      source_mode: 'manual_upload', original_plan_reference: reference, service_date: serviceDate },
    treatment_plans: [{ plan_id: planId, plan_date: '2026-08-01', is_active: true }],
    manager_reviews: [], overrides: [], source_documents: [] }
  const response = await api.post('/api/v2/manual-uploads/treatment-plan-aggregate', { data: payload })
  expect(response.status(), 'Actual aggregate import').toBe(201)
  const result = await response.json()
  identity(result)
  return { ...result, plan_id: result.treatment_plan_id }
}

export async function importBinder(api, files) {
  const form = new FormData()
  for (const [index, bytes] of files.entries()) form.append('file', new Blob([bytes], { type: 'text/plain' }), 'synthetic-' + index + '.txt')
  const response = await api.post('/api/v2/manual-uploads/treatment-plan-file', { multipart: form })
  expect(response.status(), 'Actual binder import').toBe(201)
  const result = await response.json()
  identity(result)
  return { ...result, plan_id: result.treatment_plan_id }
}

export async function openRoster(page) {
  await page.getByRole('button', { name: 'Treatment Plans Roster', exact: true }).click()
  await expect(page.getByRole('combobox', { name: 'Source filter', exact: true })).toHaveValue('all')
  await expect(page.getByLabel(rosterSearchLabel, { exact: true })).toBeVisible()
}

export function planRow(page, plan) { return page.locator('tr[data-plan-version-id="' + plan.plan_version_id + '"]') }

export function fact(page, title) {
  return page.locator('.detail-identity-panel .plan-fact-grid > div').filter({ has: page.getByText(title, { exact: true }) }).locator('dd')
}

export async function expectSelected(page, plan) {
  await expect(page.getByRole('heading', { name: 'Treatment Plan ID ' + identity(plan).treatment_plan_id, exact: true })).toBeVisible()
  await expect(fact(page, 'Saved version ID')).toHaveText(String(plan.plan_version_id))
  await expect(fact(page, 'Patient record')).toHaveText(String(plan.patient_record_id))
  await expect(fact(page, 'Source')).toHaveText(plan.source_mode === 'manual_upload' ? 'Manual' : 'Alleva')
  await expect(page.locator('.criterion-row')).toHaveCount(42)
  await expect(page.getByText('Loading selected treatment-plan detail...', { exact: true })).toHaveCount(0)
}

export async function openPlan(page, plan) {
  await openRoster(page)
  const pending = page.waitForResponse(response => {
    const url = new URL(response.url())
    return response.request().method() === 'GET' && url.pathname === '/api/v2/treatment-plans/' + encodeURIComponent(plan.patient_id) + '/' + encodeURIComponent(identity(plan).treatment_plan_id)
      && url.searchParams.get('plan_version_id') === String(plan.plan_version_id)
  })
  await planRow(page, plan).getByRole('button', { name: 'Open treatment plan ' + identity(plan).treatment_plan_id + ' for MRN ' + plan.patient_id, exact: true }).click()
  const response = await pending
  expect(response.status(), 'Actual selected detail HTTP response').toBe(200)
  assertQuery(response.url(), plan)
  const body = await response.json()
  expect(body.treatment_plan_id, 'Authoritative HTTP envelope external ID').toBe(identity(plan).treatment_plan_id)
  const envelope = identity(body)
  expect(envelope).toEqual(identity(plan))
  await expectSelected(page, plan)
  writeEvidence('task-7-http-mapper-' + plan.plan_version_id + '.json', {
    route: '/api/v2/treatment-plans/{patient_id}/{treatment_plan_id}', httpStatus: response.status(), envelope,
    displayed: { patientRecordId: await fact(page, 'Patient record').innerText(),
      planVersionId: await fact(page, 'Saved version ID').innerText(), source: await fact(page, 'Source').innerText(),
      heading: await page.getByRole('heading', { name: 'Treatment Plan ID ' + envelope.treatment_plan_id, exact: true }).innerText() },
    exactEnvelopeAndRenderedIdentityMatched: true, rawResponseBodyPersisted: false,
  })
}

export async function downloadBytes(page, action) {
  const pending = page.waitForEvent('download')
  await action()
  const download = await pending
  try {
    const stream = await download.createReadStream()
    expect(stream, 'Actual browser download stream').not.toBeNull()
    const chunks = []
    for await (const chunk of stream) chunks.push(chunk)
    return Buffer.concat(chunks)
  } finally { await download.delete() }
}

export function parseCsv(bytes) {
  const text = bytes.toString('utf8').replace(/^\uFEFF/, '')
  const rows = []
  let row = [], cell = '', quoted = false
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    if (char === '"') {
      if (quoted && text[index + 1] === '"') { cell += '"'; index += 1 } else quoted = !quoted
    } else if (char === ',' && !quoted) { row.push(cell); cell = '' }
    else if (char === '\n' && !quoted) { row.push(cell.replace(/\r$/, '')); rows.push(row); row = []; cell = '' }
    else cell += char
  }
  if (cell || row.length) { row.push(cell); rows.push(row) }
  expect(quoted, 'CSV quotes close').toBe(false)
  const headers = rows.shift() ?? []
  return { text, headers, rows: rows.map(values => Object.fromEntries(headers.map((header, index) => [header, values[index]]))) }
}

export async function exportList(page, expectedIds, source = 'all') {
  const pendingRequest = page.waitForRequest(request => new URL(request.url()).pathname === '/api/v2/exports/treatment-plans.csv' && request.method() === 'POST')
  const bytes = await downloadBytes(page, () => page.getByRole('button', { name: 'Export treatment plans and statuses', exact: true }).click())
  const body = (await pendingRequest).postDataJSON()
  expect(Object.keys(body).sort()).toEqual(source === 'all' ? ['plan_version_ids'] : ['plan_version_ids', 'source_mode'])
  expect(sortedIds(body.plan_version_ids)).toEqual(sortedIds(expectedIds))
  if (source !== 'all') expect(body.source_mode).toBe(source)
  const csv = parseCsv(bytes)
  expect(csv.headers).toEqual(csvHeaders)
  const exportedIds = csv.rows.map(row => Number(row.plan_version_id))
  expect(sortedIds(exportedIds)).toEqual(sortedIds(expectedIds))
  expect(new Set(exportedIds).size).toBe(exportedIds.length)
  return { csv, evidence: { submittedIds: body.plan_version_ids, exportedIds, source, csvSha256: hash(bytes), headers: csv.headers } }
}

export async function sourceSnapshot(sourceIds, phase) {
  expect(['A', 'B', 'C', 'D', 'after409']).toContain(phase)
  const fixture = fixtureContract()
  const executable = path.join(process.env.IZ_OM_REPO_ROOT, 'backend/.venv/Scripts/python.exe')
  const helper = path.join(process.env.IZ_OM_REPO_ROOT, 'backend/tests/office_manager_source_snapshot.py')
  const prefix = 'task-7-source-probe-' + phase
  const registration = { phase, purpose: 'exact-source-read-only-fingerprint', runId: fixture.run_id,
    sourceIds, helper: 'backend/tests/office_manager_source_snapshot.py', mode: 'sqlite-mode-ro', requested: true }
  writeEvidence(prefix + '-registration.json', registration)
  let owned, stdout = '', stderrLength = 0, overflow = false
  try {
    owned = startOwned(executable, [helper, path.join(fixture.physical_data_dir, 'fixture-contract.json'), fixture.run_id, ...sourceIds],
      { cwd: process.env.IZ_OM_REPO_ROOT, env: process.env })
    writeEvidence(prefix + '-started.json', { ...registration, pid: owned.record.pid, startedAt: owned.record.startedAt })
    owned.child.stdout.on('data', chunk => {
      if (stdout.length + chunk.length > 64_000) overflow = true
      else stdout += chunk.toString('utf8')
    })
    owned.child.stderr.on('data', chunk => { stderrLength += chunk.length })
    const exitCode = await waitOwned(owned, 15_000)
    expect(exitCode, 'Read-only source snapshot helper exits cleanly').toBe(0)
    expect(stderrLength, 'Helper emits no raw error output').toBe(0)
    expect(overflow, 'Bounded helper output').toBe(false)
    const snapshot = JSON.parse(stdout)
    expect(snapshot.read_only && snapshot.ownership_verified && snapshot.integrity_ok).toBe(true)
    expect(snapshot.foreign_key_violation_count).toBe(0)
    expect(snapshot.sources.map(source => source.source_file_id).sort()).toEqual([...sourceIds].sort())
    expect(snapshot.schema_history.at(-1).version).toBe(fixture.schema_version)
    for (const source of snapshot.sources) {
      expect(source).not.toHaveProperty('encrypted_relative_path')
      expect(source.relative_path_sha256).toMatch(/^[a-f0-9]{64}$/)
      expect(source.ciphertext_sha256).toMatch(/^[a-f0-9]{64}$/)
      expect(source.source_kind).toBe('manual_treatment_plan_file')
    }
    return snapshot
  } finally {
    if (owned) {
      await stopOwned(owned)
      writeEvidence(prefix + '-process.json', { phase, pid: owned.record.pid, startedAt: owned.record.startedAt,
        exitCode: owned.record.exitCode, stopped: owned.record.stopped, stdoutLength: stdout.length, stderrLength,
        overflow, rawOutputOmitted: true, helper: registration.helper })
      expect(owned.record.stopped, 'Owned helper handle is stopped').toBe(true)
    }
  }
}
