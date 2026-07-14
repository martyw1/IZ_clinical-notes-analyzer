import { expect, test } from '@playwright/test'

const queueItems = [
  {
    patient_id: '912', patient_display_label: 'Patient ID 912', treatment_plan_id: 'plan-912',
    current_level_of_care: 'PHP', admission_date: '2026-06-01', next_due_date: '2026-07-01',
    status: 'Needs Review', missing_criteria_count: 0, returned_criteria_count: 0,
    source_mode: 'alleva_rest_api', warnings: [],
  },
  {
    patient_id: '912', patient_display_label: 'Patient ID 912', treatment_plan_id: 'plan-913',
    current_level_of_care: 'PHP', admission_date: '2026-06-01', next_due_date: '2026-08-01',
    status: 'Unable to Evaluate', missing_criteria_count: 0, returned_criteria_count: 0,
    source_mode: 'alleva_rest_api', warnings: [],
  },
]

function planDetail(planId) {
  return {
    patient_id: '912', patient_display_label: 'Patient ID 912', source_mode: 'alleva_rest_api',
    current_level_of_care: 'PHP', admission_date: '2026-06-01', date_clock_due_date: '2026-08-01',
    overall_status: planId === 'plan-913' ? 'Unable to Evaluate' : 'Needs Review',
    content_sections_present: ['problems'], content_sections_missing: [], data_quality_warnings: [],
    criteria_results: [], manager_reviews: [], overrides: [], source_documents: [],
    evidence_coverage_summary: { criteria_total: 0, criteria_with_evidence: 0, criteria_missing_evidence: 0, runtime_only_fields: [] },
    content_snapshot: {
      plan_id: planId,
      reason_for_admission: 'Synthetic UI validation.', initial_client_needs: '', family_education_needs: '',
      problems: [{ problem_number: '1', problem_description: `Synthetic problem for ${planId}.`, diagnoses: [], behavioral_definitions: [], goals: [] }],
      signatures: [], observed_fields: [],
    },
  }
}

async function captureViewports(page, testInfo, label) {
  for (const width of [375, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 })
    await page.evaluate(() => {
      for (const child of [...document.body.children]) {
        if (child.id !== 'root' && child.tagName !== 'SCRIPT') child.remove()
      }
    })
    await page.screenshot({ path: testInfo.outputPath(`${label}-${width}.png`), fullPage: true })
  }
}

test('full treatment-plan pull populates both operational tabs and keeps multiple plans selectable', async ({ page }, testInfo) => {
  let syncCount = 0
  let synced = false
  let rosterSynced = false
  const detailRequests = []
  await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    const respond = (payload, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) })
    if (path === '/api/auth/login' && method === 'POST') return respond({ access_token: 'synthetic-ui-token', token_type: 'bearer', must_reset_password: false })
    if (path === '/api/users/me') return respond({ id: 1, username: 'e2eadmin', full_name: 'E2E Administrator', role: 'admin', is_active: true, is_locked: false, must_reset_password: false })
    if (path === '/api/v2/navigation') return respond({ items: ['Status Dashboard', 'Treatment Plans', 'Patient Roster', 'API Testing Harness', 'Settings'], active_runtime: 'v2' })
    if (path === '/api/v2/dashboard') return respond({ source_cards: [], metrics: {}, blockers: [] })
    if (path === '/api/settings') return respond({ organization_name: 'R3 Recovery Services', facility_timezone: 'America/New_York', treatment_plan_master_due_days: 30, treatment_plan_php_review_interval_days: 30, treatment_plan_iop_op_review_interval_days: 90, treatment_plan_loc_change_window_days: 7, treatment_plan_loc_change_window_validated: false })
    if (path === '/api/api-configuration') return respond({ vendor_name: 'Synthetic Alleva', api_base_url: 'http://synthetic.invalid', openapi_url: 'http://synthetic.invalid/openapi.json', token_url: 'http://synthetic.invalid/token', client_id_configured: true, api_key_configured: true, client_secret_configured: true, token_auth_style: 'body', scopes: 'plans.read', api_version: '1.0', treatment_plan_start_date: '2020-01-01T00:00:00Z', pagination_limit: 100, sync_limit: 100, requests_per_minute: 600, timeout_seconds: 10, api_enabled: true, treatment_plan_sync_enabled: true, treatment_plan_sync_approved: true, active_contract_version: null })
    if (path === '/api/api-configuration/test-connectivity' && method === 'POST') return respond({ status: 'ok', token_auth_style: 'body', message: 'OAuth connection succeeded.', token_type: 'Bearer', expires_in: 3600 })
    if (path === '/api/v2/alleva-sync/run' && method === 'POST') {
      syncCount += 1
      return respond({ job_id: `sync-ui-${syncCount}`, status: 'queued', progress_percent: 0, records_written: 0, records_failed: 0, warnings_count: 0, artifacts: [] }, 202)
    }
    if (path.startsWith('/api/v2/alleva-sync/jobs/')) {
      synced = true
      return respond({ job_id: path.split('/').at(-1), status: 'completed', progress_percent: 100, records_written: 2, records_failed: 0, warnings_count: 0, artifacts: [] })
    }
    if (path === '/api/v2/patient-roster/pull' && method === 'POST') {
      return respond({ job_id: 'roster-ui-1', status: 'queued', progress_percent: 0, records_written: 0, records_failed: 0, warnings_count: 0, artifacts: [] }, 202)
    }
    if (path === '/api/v2/patient-roster/jobs/latest') {
      return rosterSynced
        ? respond({ job_id: 'roster-ui-1', status: 'completed', progress_percent: 100, records_written: 1, records_failed: 0, warnings_count: 0, artifacts: [] })
        : respond({ detail: 'No roster job has run.' }, 404)
    }
    if (path === '/api/v2/patient-roster/jobs/roster-ui-1') {
      rosterSynced = true
      return respond({ job_id: 'roster-ui-1', status: 'completed', progress_percent: 100, records_written: 1, records_failed: 0, warnings_count: 0, artifacts: [] })
    }
    if (path === '/api/v2/treatment-plans') return respond({ items: synced ? queueItems : [], status_order: ['Needs Review', 'Unable to Evaluate'] })
    if (path === '/api/v2/treatment-plans/912/plan-912' || path === '/api/v2/treatment-plans/912/plan-913') {
      detailRequests.push(path)
      return respond(planDetail(path.endsWith('plan-913') ? 'plan-913' : 'plan-912'))
    }
    if (path === '/api/v2/patient-roster') return respond({ items: rosterSynced ? [{ patient_id: '912', source_mode: 'alleva_rest_api', lifecycle_state: 'active', current_level_of_care: 'PHP', treatment_plan_id: 'plan-913', treatment_plan_status: 'Unable to Evaluate', first_seen_at: '2026-07-13T10:00:00Z', last_seen_at: '2026-07-13T10:05:00Z', reconciled_at: '2026-07-13T10:05:00Z' }] : [] })
    return respond({ detail: `Unexpected ${method} ${path}` }, 404)
  })

  await page.goto('/')
  await page.getByLabel('Username').fill('e2eadmin')
  await page.getByLabel('Password').fill('SyntheticUiPass1')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await page.getByRole('button', { name: 'API Testing Harness' }).click()
  await page.getByRole('button', { name: 'Test saved OAuth credentials' }).click()
  await expect(page.getByText('OAuth connection succeeded.')).toBeVisible()
  await expect(page.getByText(/built-in Alleva v1 mapping is applied automatically/i)).toBeVisible()
  await expect(page.getByRole('button', { name: /record approved/i })).toHaveCount(0)
  await captureViewports(page, testInfo, 'alleva-automatic-mapping')

  await page.getByRole('button', { name: 'Treatment Plans', exact: true }).click()
  await page.getByRole('button', { name: 'Pull full treatment plans' }).click()
  await expect(page.getByRole('status')).toContainText('2 treatment plans')
  await expect(page.getByRole('button', { name: 'plan-912' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'plan-913' })).toBeVisible()
  await page.getByRole('button', { name: 'plan-913' }).click()
  await expect(page.getByRole('heading', { name: 'Treatment Plan ID plan-913' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'plan-913' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText('Synthetic problem for plan-913.')).toBeVisible()
  expect(detailRequests).toContain('/api/v2/treatment-plans/912/plan-913')
  await captureViewports(page, testInfo, 'treatment-plans-multiple-plans')

  await page.getByRole('button', { name: 'Patient Roster' }).click()
  await page.getByRole('button', { name: 'Pull active patient roster' }).click()
  await expect(page.getByRole('status')).toContainText('Completed successfully. 1 record updated.')
  await expect(page.getByRole('heading', { name: 'Patient roster', exact: true })).toBeVisible()
  await expect(page.getByText('plan-913')).toBeVisible()
  await expect(page.getByText('Unable to Evaluate')).toBeVisible()
  await expect(page.getByText(/Patient names are excluded/i)).toBeVisible()
  await captureViewports(page, testInfo, 'patient-roster-after-pull')
})

test('same patient and plan IDs remain selectable by source identity', async ({ page }, testInfo) => {
  const sharedItems = [
    {
      patient_id: '843', patient_display_label: 'Patient ID 843', treatment_plan_id: 'plan-shared',
      current_level_of_care: 'IOP', admission_date: '2026-06-01', next_due_date: '2026-07-01',
      status: 'Needs Review', missing_criteria_count: 0, returned_criteria_count: 0,
      source_mode: 'manual_upload', warnings: [],
    },
    {
      patient_id: '843', patient_display_label: 'Patient ID 843', treatment_plan_id: 'plan-shared',
      current_level_of_care: 'RTC', admission_date: '2026-06-01', next_due_date: '2026-08-01',
      status: 'Unable to Evaluate', missing_criteria_count: 0, returned_criteria_count: 0,
      source_mode: 'alleva_rest_api', warnings: [],
    },
  ]
  const detailRequests = []
  await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
    const requestUrl = new URL(route.request().url())
    const path = requestUrl.pathname
    const sourceMode = requestUrl.searchParams.get('source_mode')
    const method = route.request().method()
    const respond = (payload, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) })
    if (path === '/api/auth/login' && method === 'POST') return respond({ access_token: 'synthetic-ui-token', token_type: 'bearer', must_reset_password: false })
    if (path === '/api/users/me') return respond({ id: 1, username: 'e2eadmin', full_name: 'E2E Administrator', role: 'admin', is_active: true, is_locked: false, must_reset_password: false })
    if (path === '/api/v2/navigation') return respond({ items: ['Status Dashboard', 'Treatment Plans'], active_runtime: 'v2' })
    if (path === '/api/v2/dashboard') return respond({ source_cards: [], metrics: {}, blockers: [] })
    if (path === '/api/api-configuration') return respond({ vendor_name: 'Synthetic Alleva', api_base_url: 'http://synthetic.invalid', openapi_url: 'http://synthetic.invalid/openapi.json', token_url: 'http://synthetic.invalid/token', client_id_configured: true, api_key_configured: true, client_secret_configured: true, token_auth_style: 'body', scopes: 'plans.read', api_version: '1.0', treatment_plan_start_date: '2020-01-01T00:00:00Z', pagination_limit: 100, sync_limit: 100, requests_per_minute: 600, timeout_seconds: 10, api_enabled: true, treatment_plan_sync_enabled: true, treatment_plan_sync_approved: true })
    if (path === '/api/v2/treatment-plans') return respond({ items: sharedItems, status_order: ['Needs Review', 'Unable to Evaluate'] })
    if (path === '/api/v2/treatment-plans/843/plan-shared') {
      detailRequests.push(route.request().url())
      const isAlleva = sourceMode === 'alleva_rest_api'
      return respond({
        patient_id: '843', patient_display_label: 'Patient ID 843', source_mode: sourceMode,
        current_level_of_care: isAlleva ? 'RTC' : 'IOP', admission_date: '2026-06-01',
        date_clock_due_date: isAlleva ? '2026-08-01' : '2026-07-01',
        overall_status: isAlleva ? 'Unable to Evaluate' : 'Needs Review',
        content_sections_present: ['problems'], content_sections_missing: [], data_quality_warnings: [],
        criteria_results: [], manager_reviews: [], overrides: [], source_documents: [],
        evidence_coverage_summary: { criteria_total: 0, criteria_with_evidence: 0, criteria_missing_evidence: 0, runtime_only_fields: [] },
        content_snapshot: {
          plan_id: 'plan-shared', reason_for_admission: isAlleva ? 'Alleva source detail.' : 'Manual source detail.',
          initial_client_needs: '', family_education_needs: '', problems: [], signatures: [], observed_fields: [],
        },
      })
    }
    return respond({ detail: `Unexpected ${method} ${path}` }, 404)
  })

  await page.goto('/')
  await page.getByLabel('Username').fill('e2eadmin')
  await page.getByLabel('Password').fill('SyntheticUiPass1')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('button', { name: 'Treatment Plans', exact: true }).click()

  const sharedButtons = page.getByRole('button', { name: 'plan-shared' })
  await expect(sharedButtons).toHaveCount(2)
  await expect(page.getByText('Manual source detail.')).toBeVisible()
  await sharedButtons.nth(1).click()
  await expect(page.getByText('Alleva source detail.')).toBeVisible()
  await expect(sharedButtons.nth(1)).toHaveAttribute('aria-pressed', 'true')
  expect(detailRequests.some((url) => url.endsWith('source_mode=manual_upload'))).toBe(true)
  expect(detailRequests.some((url) => url.endsWith('source_mode=alleva_rest_api'))).toBe(true)
  await captureViewports(page, testInfo, 'treatment-plans-source-collision')
})

test('multi-file Manual Upload processes a binder and opens Treatment Plans without retaining filenames', async ({ page }) => {
  await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    const respond = (payload, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(payload) })
    if (path === '/api/auth/login' && method === 'POST') return respond({ access_token: 'synthetic-ui-token', token_type: 'bearer', must_reset_password: false })
    if (path === '/api/users/me') return respond({ id: 1, username: 'e2eadmin', full_name: 'E2E Administrator', role: 'admin', is_active: true, is_locked: false, must_reset_password: false })
    if (path === '/api/v2/navigation') return respond({ items: ['Status Dashboard', 'Treatment Plans', 'Manual Upload'], active_runtime: 'v2' })
    if (path === '/api/v2/dashboard') return respond({ source_cards: [], metrics: {}, blockers: [] })
    if (path === '/api/v2/manual-uploads/treatment-plan-file' && method === 'POST') {
      return respond({
        status: 'imported_with_warnings', patient_id: 'synthetic-demo', patient_display_label: 'Patient ID synthetic-demo',
        source_mode: 'manual_upload', criteria_total: 42, encrypted_at_rest: true, source_file_archived: true,
        source_file_id: 'source-1', source_file_ids: ['source-1', 'source-2'], patient_id_correction_applied: false,
        file_count: 2, parsed_file_count: 1, opaque_file_count: 1, overall_status: 'Unable to Evaluate',
        warnings: ['One uploaded source was archived as opaque content and was not parsed.'],
      }, 201)
    }
    if (path === '/api/api-configuration') return respond({ client_id_configured: false, client_secret_configured: false, api_enabled: false, treatment_plan_sync_enabled: false, treatment_plan_sync_approved: false })
    if (path === '/api/v2/treatment-plans') return respond({ items: [], status_order: ['Unable to Evaluate'] })
    return respond({ detail: `Unexpected ${method} ${path}` }, 404)
  })

  await page.goto('/')
  await page.getByLabel('Username').fill('e2eadmin')
  await page.getByLabel('Password').fill('SyntheticUiPass1')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('button', { name: 'Manual Upload' }).click()

  await page.getByLabel('Treatment-plan binder files').setInputFiles([
    { name: 'synthetic-evidence.txt', mimeType: 'text/plain', buffer: Buffer.from('Patient ID: synthetic-demo') },
    { name: 'synthetic-scan.png', mimeType: 'image/png', buffer: Buffer.from('opaque synthetic bytes') },
  ])
  await expect(page.getByText('2 files selected')).toBeVisible()
  await page.getByRole('button', { name: 'Upload and securely process binder' }).click()
  await expect(page.getByRole('status')).toContainText('Secure processing complete')
  await expect(page.getByText('1 parsed')).toBeVisible()
  await expect(page.getByText('1 stored without parsing')).toBeVisible()
  await expect(page.getByText('synthetic-evidence.txt')).toHaveCount(0)
  await expect(page.getByText('synthetic-scan.png')).toHaveCount(0)
  await page.getByRole('button', { name: 'Review in Treatment Plans' }).click()
  await expect(page.getByRole('heading', { name: 'Treatment Plan Workbench' })).toBeVisible()
})
