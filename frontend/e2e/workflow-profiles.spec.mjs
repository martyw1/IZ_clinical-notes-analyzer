import { expect, test } from '@playwright/test'

const bootstrapUsername = process.env.IZ_CNA_E2E_ADMIN_USERNAME ?? 'e2eadmin'
const bootstrapPassword = process.env.IZ_CNA_E2E_ADMIN_PASSWORD ?? 'E2eActivePass456'

test('admin sees workflow profiles withheld and opens supported controls', async ({ page }, testInfo) => {
  await page.goto('/')
  await page.getByLabel('Username').fill(bootstrapUsername)
  await page.getByLabel('Password').fill(bootstrapPassword)
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page.getByRole('button', { name: 'Workflow Profiles' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Settings' }).click()
  await expect(page.getByRole('heading', { name: 'Local V2 controls' })).toBeVisible()
  await page.getByRole('button', { name: 'API Testing Harness' }).click()
  await expect(page.getByRole('heading', { name: 'Alleva/OpenAPI testing' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('supported-admin-controls.png') })
})

test('admin uploads a treatment plan and opens its persisted missing-data detail from Patient Roster', async ({ page }, testInfo) => {
  const yesterday = new Date()
  yesterday.setDate(yesterday.getDate() - 1)
  const dueDate = yesterday.toISOString().slice(0, 10)

  await page.goto('/')
  await page.getByLabel('Username').fill(bootstrapUsername)
  await page.getByLabel('Password').fill(bootstrapPassword)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('button', { name: 'Manual Upload' }).click()
  await page.getByLabel('Treatment-plan binder files').setInputFiles({
    name: 'synthetic-late-treatment-plan.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from(`MRN: 915\nCurrent Level of Care: PHP\nAdmission Date: 2026-06-01\nNext Due Date: ${dueDate}\nSignature Date: 2026-06-02\nIntervention: Synthetic intervention.`),
  })
  await page.getByRole('button', { name: 'Upload and securely process binder' }).click()
  await expect(page.getByRole('status')).toContainText('Imported MRN 915')
  await page.getByRole('button', { name: 'Review in Patient Roster' }).click()
  await page.getByRole('combobox', { name: 'Treatment plans for MRN 915' }).selectOption({ index: 1 })
  await expect(page.getByRole('heading', { name: /Treatment Plan ID manual-915-/ })).toBeVisible()
  await expect(page.getByText('Missing Data', { exact: true }).first()).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('manual-upload-missing-data-status.png') })
})

test('admin enables treatment-plan sync and sees a mocked synced treatment plan', async ({ page }, testInfo) => {
  let syncEnabled = false
  let syncCompleted = false
  await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    const respond = async (payload) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(payload) })
    if (path === '/api/auth/login' && method === 'POST') return respond({ access_token: 'browser-sync-token', token_type: 'bearer', must_reset_password: false })
    if (path === '/api/users/me') return respond({ id: 1, username: 'e2eadmin', full_name: 'E2E Administrator', role: 'admin', is_active: true, is_locked: false, must_reset_password: false })
    if (path === '/api/v2/navigation') return respond({ items: ['Status Dashboard', 'Patient Roster', 'Manual Upload', 'Treatment Plan Detail', 'Treatment Plans Roster', 'API Testing Harness', 'Users', 'Forensic Logs', 'Settings', 'Help'], active_runtime: 'v2' })
    if (path === '/api/v2/dashboard') return respond({ source_cards: [], metrics: {}, blockers: [] })
    if (path === '/api/settings') return respond({ organization_name: 'R3 Recovery Services', facility_timezone: 'America/New_York', treatment_plan_master_due_days: 30, treatment_plan_php_review_interval_days: 30, treatment_plan_iop_op_review_interval_days: 90, treatment_plan_loc_change_window_days: 7, treatment_plan_loc_change_window_validated: false })
    if (path === '/api/api-configuration') return respond({ vendor_name: 'Mock Alleva', api_base_url: 'http://mock.invalid', openapi_url: 'http://mock.invalid/openapi.json', token_url: 'http://mock.invalid/token', client_id_configured: true, api_key_configured: syncEnabled, client_secret_configured: true, token_auth_style: 'body', scopes: '', api_version: '1.0', treatment_plan_start_date: '2020-01-01T00:00:00Z', pagination_limit: 100, sync_limit: 100, requests_per_minute: 600, timeout_seconds: 10, api_enabled: syncEnabled, treatment_plan_sync_enabled: syncEnabled, treatment_plan_sync_approved: syncEnabled, active_contract_version: null })
    if (path === '/api/v2/api-harness/jobs') return respond([])
    if (path === '/api/v2/alleva-sync/run' && method === 'POST') return respond({ job_id: 'sync-browser-912', status: 'queued', progress_percent: 0, records_written: 0, records_failed: 0, warnings_count: 0, artifacts: [] })
    if (path === '/api/v2/alleva-sync/jobs/sync-browser-912') { syncCompleted = true; return respond({ job_id: 'sync-browser-912', status: 'completed', progress_percent: 100, records_written: 1, records_failed: 0, warnings_count: 0, artifacts: [] }) }
    if (path === '/api/v2/treatment-plan-roster') return respond({ items: syncCompleted ? [{ treatment_plan_id: 'plan-912', mrn: '912', last_updated: '2026-07-12T12:00:00Z', previous_treatment_plan_id: '', initial_treatment_plan_id: 'plan-912', initial_treatment_plan_date: '2026-06-01' }] : [] })
    if (path === '/api/v2/treatment-plans/912/plan-912') return respond({ patient_id: '912', patient_display_label: 'MRN 912', source_mode: 'alleva_rest_api', current_level_of_care: 'PHP', admission_date: '2026-06-01', date_clock_due_date: '2026-07-01', overall_status: 'Needs Review', content_sections_present: ['problems'], content_sections_missing: [], data_quality_warnings: [], criteria_results: [], manager_reviews: [], overrides: [], source_documents: [], evidence_coverage_summary: { criteria_total: 42, criteria_with_evidence: 1, criteria_missing_evidence: 0, runtime_only_fields: [] }, content_snapshot: { plan_id: 'plan-912', problems: [], signatures: [], observed_fields: [] } })
    return respond({ detail: `Unexpected ${method} ${path}` })
  })

  await page.goto('/')
  await page.getByLabel('Username').fill(bootstrapUsername)
  await page.getByLabel('Password').fill(bootstrapPassword)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('button', { name: 'Settings' }).click()
  await page.getByLabel('Enable API testing').check()
  await page.getByLabel('Enable treatment-plan sync').check()
  syncEnabled = true
  await page.getByRole('button', { name: 'Save API configuration' }).click()
  await page.getByRole('button', { name: 'Run treatment-plan sync' }).click()
  await expect(page.getByText('Treatment-plan sync completed: 1 imported, 0 skipped.')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('approved-sync-settings.png') })
  await page.getByRole('button', { name: 'Treatment Plans Roster' }).click()
  await page.getByRole('button', { name: 'Open treatment plan plan-912 for MRN 912' }).click()
  await expect(page.getByRole('heading', { name: 'Treatment Plan ID plan-912' })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('approved-sync-treatment-plan.png') })
})

test('admin can cancel a queued treatment-plan sync', async ({ page }, testInfo) => {
  let cancellationRequested = false
  let syncResumed = false
  await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    const respond = async (payload) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(payload) })
    if (path === '/api/auth/login' && method === 'POST') return respond({ access_token: 'browser-sync-cancel-token', token_type: 'bearer', must_reset_password: false })
    if (path === '/api/users/me') return respond({ id: 1, username: 'e2eadmin', full_name: 'E2E Administrator', role: 'admin', is_active: true, is_locked: false, must_reset_password: false })
    if (path === '/api/v2/navigation') return respond({ items: ['Status Dashboard', 'Patient Roster', 'Manual Upload', 'Treatment Plan Detail', 'Treatment Plans Roster', 'Settings'], active_runtime: 'v2' })
    if (path === '/api/v2/dashboard') return respond({ source_cards: [], metrics: {}, blockers: [] })
    if (path === '/api/settings') return respond({ organization_name: 'R3 Recovery Services', facility_timezone: 'America/New_York', treatment_plan_master_due_days: 30, treatment_plan_php_review_interval_days: 30, treatment_plan_iop_op_review_interval_days: 90, treatment_plan_loc_change_window_days: 7, treatment_plan_loc_change_window_validated: false })
    if (path === '/api/api-configuration') return respond({ vendor_name: 'Mock Alleva', api_base_url: 'http://mock.invalid', openapi_url: 'http://mock.invalid/openapi.json', token_url: 'http://mock.invalid/token', client_id_configured: true, api_key_configured: true, client_secret_configured: true, token_auth_style: 'body', scopes: '', api_version: '1.0', treatment_plan_start_date: '2020-01-01T00:00:00Z', pagination_limit: 100, sync_limit: 100, requests_per_minute: 600, timeout_seconds: 10, api_enabled: true, treatment_plan_sync_enabled: true, treatment_plan_sync_approved: true, active_contract_version: null })
    if (path === '/api/v2/api-harness/jobs') return respond([])
    if (path === '/api/v2/alleva-sync/run' && method === 'POST') return respond({ job_id: 'sync-browser-cancel', status: 'queued', progress_percent: 0, records_written: 0, records_failed: 0, warnings_count: 0, artifacts: [] })
    if (path === '/api/v2/api-harness/jobs/sync-browser-cancel/cancel' && method === 'POST') { cancellationRequested = true; return respond({ job_id: 'sync-browser-cancel', status: 'cancelled', progress_percent: 100, records_written: 0, records_failed: 0, warnings_count: 0, artifacts: [] }) }
    if (path === '/api/v2/alleva-sync/jobs/sync-browser-cancel/resume' && method === 'POST') { syncResumed = true; return respond({ job_id: 'sync-browser-resumed', status: 'queued', progress_percent: 0, records_written: 0, records_failed: 0, warnings_count: 0, artifacts: [] }) }
    if (path === '/api/v2/alleva-sync/jobs/sync-browser-resumed') return respond({ job_id: 'sync-browser-resumed', status: syncResumed ? 'completed' : 'queued', progress_percent: syncResumed ? 100 : 0, records_written: 1, records_failed: 0, warnings_count: 0, artifacts: [] })
    if (path === '/api/v2/alleva-sync/jobs/sync-browser-cancel') return respond({ job_id: 'sync-browser-cancel', status: cancellationRequested ? 'cancelled' : 'queued', progress_percent: cancellationRequested ? 100 : 0, records_written: 0, records_failed: 0, warnings_count: 0, artifacts: [] })
    return respond({ detail: `Unexpected ${method} ${path}` })
  })

  await page.goto('/')
  await page.getByLabel('Username').fill(bootstrapUsername)
  await page.getByLabel('Password').fill(bootstrapPassword)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('button', { name: 'Settings' }).click()
  await page.getByRole('button', { name: 'Run treatment-plan sync' }).click()
  await expect(page.getByRole('button', { name: 'Cancel treatment-plan sync' })).toBeVisible()
  await page.getByRole('button', { name: 'Cancel treatment-plan sync' }).click()
  await expect(page.getByText('Treatment-plan sync cancelled: 0 imported, 0 skipped.')).toBeVisible()
  await page.getByRole('button', { name: 'Resume treatment-plan sync safely' }).click()
  await expect(page.getByText('Treatment-plan sync completed: 1 imported, 0 skipped.')).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('approved-sync-resumed.png') })
})
