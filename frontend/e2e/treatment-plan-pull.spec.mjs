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
  let activeContractVersion = ''
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
    if (path === '/api/api-configuration') return respond({ vendor_name: 'Synthetic Alleva', api_base_url: 'http://synthetic.invalid', openapi_url: 'http://synthetic.invalid/openapi.json', token_url: 'http://synthetic.invalid/token', client_id: 'synthetic-client', api_key_configured: true, client_secret_configured: true, token_auth_style: 'body', scopes: 'plans.read', pagination_limit: 100, sync_limit: 100, timeout_seconds: 10, api_enabled: true, treatment_plan_sync_enabled: true, treatment_plan_sync_approved: true, treatment_plan_endpoint_mapping_validated: true, active_contract_version: activeContractVersion })
    if (path === '/api/api-configuration/test-connectivity' && method === 'POST') return respond({ status: 'ok', token_auth_style: 'body', message: 'OAuth connection succeeded.', token_type: 'Bearer', expires_in: 3600 })
    if (path === '/api/v2/alleva-sync/contracts' && method === 'POST') {
      const contract = route.request().postDataJSON()
      expect(contract.api_base_url).toBe('http://synthetic.invalid')
      expect(contract.endpoints.treatment_plans.field_mappings.client_id).toBe('client.id')
      expect(contract.endpoints.treatment_plans.field_mappings.client_reference).toBe('client.route')
      expect(contract.endpoints.treatment_plans.parameters.client_id).toBe('ClientId')
      expect(JSON.stringify(contract)).not.toContain('synthetic-client')
      activeContractVersion = contract.contract_version
      return respond({ contract_version: activeContractVersion, contract_sha256: 'a'.repeat(64), effective_at: '2026-07-13T10:00:00Z', approved_at: '2026-07-13T10:00:00Z' }, 201)
    }
    if (path === '/api/v2/alleva-sync/run' && method === 'POST') {
      syncCount += 1
      return respond({ job_id: `sync-ui-${syncCount}`, status: 'queued', progress_percent: 0, records_written: 0, records_failed: 0, warnings_count: 0, artifacts: [] }, 202)
    }
    if (path.startsWith('/api/v2/alleva-sync/jobs/')) {
      synced = true
      return respond({ job_id: path.split('/').at(-1), status: 'completed', progress_percent: 100, records_written: 2, records_failed: 0, warnings_count: 0, artifacts: [] })
    }
    if (path === '/api/v2/treatment-plans') return respond({ items: synced ? queueItems : [], status_order: ['Needs Review', 'Unable to Evaluate'] })
    if (path === '/api/v2/treatment-plans/912/plan-912' || path === '/api/v2/treatment-plans/912/plan-913') {
      detailRequests.push(path)
      return respond(planDetail(path.endsWith('plan-913') ? 'plan-913' : 'plan-912'))
    }
    if (path === '/api/v2/patient-roster') return respond({ items: synced ? [{ patient_id: '912', source_mode: 'alleva_rest_api', lifecycle_state: 'active', current_level_of_care: 'PHP', treatment_plan_id: 'plan-913', treatment_plan_status: 'Unable to Evaluate', first_seen_at: '2026-07-13T10:00:00Z', last_seen_at: '2026-07-13T10:05:00Z', reconciled_at: '2026-07-13T10:05:00Z' }] : [] })
    return respond({ detail: `Unexpected ${method} ${path}` }, 404)
  })

  await page.goto('/')
  await page.getByLabel('Username').fill('e2eadmin')
  await page.getByLabel('Password').fill('SyntheticUiPass1')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await page.getByRole('button', { name: 'API Testing Harness' }).click()
  await page.getByRole('button', { name: 'Test saved OAuth credentials' }).click()
  await expect(page.getByText('OAuth connection succeeded.')).toBeVisible()
  await page.getByLabel('Mapping version').fill('synthetic-ui-contract-v2')
  await page.getByLabel('Non-PHI test population reference').fill('Synthetic sandbox cohort 2026-07-13')
  await page.getByLabel('Vendor-approved maximum requests per minute').fill('60')
  await page.getByLabel(/I confirm this endpoint mapping/i).check()
  await captureViewports(page, testInfo, 'alleva-contract-setup')
  await page.getByRole('button', { name: 'Record approved Alleva v1 mapping' }).click()
  await expect(page.getByRole('heading', { name: 'Alleva v1 mapping is active' })).toBeVisible()
  await expect(page.getByText('synthetic-ui-contract-v2', { exact: true })).toBeVisible()
  await page.screenshot({ path: testInfo.outputPath('alleva-contract-activated.png'), fullPage: true })

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
  await page.getByRole('button', { name: 'Pull full treatment plans' }).click()
  await expect(page.getByRole('status')).toContainText('2 treatment plans')
  await expect(page.getByRole('heading', { name: 'Patient roster' })).toBeVisible()
  await expect(page.getByText('plan-913')).toBeVisible()
  await expect(page.getByText('Unable to Evaluate')).toBeVisible()
  await expect(page.getByText(/Patient names are excluded/i)).toBeVisible()
  await captureViewports(page, testInfo, 'patient-roster-after-pull')
})
