import { vi } from 'vitest'

type Role = 'admin' | 'office_manager' | 'counselor' | 'viewer'

type FetchState = {
  readonly role: Role
  readonly failLogin?: boolean
}

export const adminNavigation = [
  'Status Dashboard',
  'Treatment Plans',
  'Manual Upload',
  'API Testing Harness',
  'Users',
  'Forensic Logs',
  'Settings',
  'Help',
] as const

const counselorNavigation = ['Status Dashboard', 'Treatment Plans', 'Manual Upload', 'Help'] as const

export function setupFetch(state: FetchState = { role: 'admin' }) {
  const deletedSourceFileIds = new Set<string>()
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    const path = pathFrom(input)

    if (path === '/api/auth/login' && method === 'POST') {
      if (state.failLogin) return jsonResponse({ detail: 'Invalid credentials' }, 401)
      return jsonResponse({ access_token: 'token-from-backend', token_type: 'bearer', must_reset_password: false })
    }
    if (path === '/api/users/me') return jsonResponse(userPayload(state.role))
    if (path === '/api/v2/navigation') return jsonResponse({ items: state.role === 'admin' ? adminNavigation : counselorNavigation, active_runtime: 'v2' })
    if (path === '/api/v2/dashboard') return jsonResponse(dashboardPayload())
    if (path === '/api/v2/treatment-plans') return jsonResponse(treatmentPlansPayload())
    if (path === '/api/v2/treatment-plans/812') return jsonResponse(treatmentPlanDetailPayload(deletedSourceFileIds.has('source-file-812')))
    if (path === '/api/v2/treatment-plans/812/manager-actions' && method === 'POST') return jsonResponse({ status: 'saved' })
    if (path === '/api/v2/treatment-plans/812/source-documents/source-file-812' && method === 'DELETE') {
      deletedSourceFileIds.add('source-file-812')
      return jsonResponse({ status: 'deleted', source_file_id: 'source-file-812', file_removed: true })
    }
    if (path === '/api/v2/treatment-plans/812/source-documents/source-file-812/download') return sourceDocumentDownloadResponse()
    if (path === '/api/v2/manual-uploads/treatment-plan-aggregate' && method === 'POST') return importResponse('812', false)
    if (path === '/api/v2/manual-uploads/treatment-plan-file' && method === 'POST') return importResponse('914', true)
    if (path === '/api/settings') return jsonResponse(settingsPayload())
    if (path === '/api/api-configuration') return jsonResponse(apiConfigurationPayload(method === 'PATCH'))
    if (path === '/api/users') return jsonResponse([userPayload('admin'), userPayload('counselor')])
    if (path === '/api/audit/logs') return jsonResponse(auditLogsPayload())
    if (path === '/api/v2/api-harness/jobs' && method === 'POST') return jsonResponse(jobPayload())
    if (path === '/api/v2/api-harness/jobs/job-812/artifacts') return jsonResponse(jobPayload().artifacts)
    return jsonResponse({ detail: `Unexpected test route ${method} ${path}` }, 404)
  })

  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function pathFrom(input: RequestInfo | URL): string {
  return typeof input === 'string' ? input : input instanceof URL ? input.pathname : input.url
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status, headers: { 'content-type': 'application/json' } })
}

function sourceDocumentDownloadResponse(): Response {
  return new Response('Patient ID: 812\nIntervention: Synthetic archived source.', {
    status: 200,
    headers: {
      'content-disposition': 'attachment; filename="manual-treatment-plan-source-source-file-812.txt"',
      'content-type': 'text/plain',
    },
  })
}

function importResponse(patientId: string, archived: boolean): Response {
  return jsonResponse({ status: 'imported', patient_id: patientId, patient_display_label: `Patient ID ${patientId}`, source_mode: 'manual_upload', criteria_total: 42, encrypted_at_rest: true, source_file_archived: archived, source_file_id: archived ? 'source-file-914' : null }, 201)
}

function userPayload(role: Role) {
  return {
    id: role === 'admin' ? 1 : 2,
    username: role,
    full_name: role === 'admin' ? 'Local Administrator' : 'Counselor User',
    role,
    is_active: true,
    is_locked: false,
    must_reset_password: false,
    last_login_at: null,
    created_at: '2026-07-08T09:00:00Z',
  }
}

function dashboardPayload() {
  return {
    source_cards: [
      { label: 'Manual upload readiness', status: 'ready', detail: 'Manual evidence accepted.' },
      { label: 'API readiness', status: 'configured for testing', detail: 'Alleva harness is bounded.' },
      { label: 'Alleva treatment-plan sync readiness', status: 'blocked', detail: 'Live sync remains gated.' },
    ],
    metrics: { active_patient_ids: 2, needs_review: 4, missing_data: 5, conflicting: 1, unable: 0 },
    blockers: ['LOC-change update window is unvalidated and configurable.'],
  }
}

function treatmentPlansPayload() {
  return {
    items: [{
      patient_id: '812',
      patient_display_label: 'Patient ID 812',
      current_level_of_care: 'PHP',
      admission_date: '2026-06-01',
      next_due_date: '2026-07-15',
      status: 'Needs Review',
      missing_criteria_count: 2,
      returned_criteria_count: 0,
      source_mode: 'alleva_rest_api',
      warnings: ['LOC-change update window remains unvalidated.'],
    }],
    status_order: ['Missing Data', 'Needs Review', 'Incomplete', 'Within Window', 'Late', 'Conflicting Evidence', 'Unable to Evaluate'],
  }
}

function treatmentPlanDetailPayload(sourceFileDeleted = false) {
  return {
    patient_id: '812',
    patient_display_label: 'Patient ID 812',
    source_mode: 'alleva_rest_api',
    current_level_of_care: 'PHP',
    admission_date: '2026-06-01',
    date_clock_due_date: '2026-07-15',
    overall_status: 'Needs Review',
    content_sections_present: ['diagnoses', 'goals', 'objectives', 'interventions', 'signatures_metadata'],
    content_sections_missing: ['trusted_nextReviewDue'],
    manager_reviews: [{
      criterion_id: 'confirm_current_loc',
      action: 'override',
      manager_status: 'Override',
      comment: 'Accepted after source review.',
      override_reason: 'Signed plan and LOC evidence match imported record.',
      actor_username: 'admin',
      actor_role: 'admin',
      created_at: '2026-07-08T10:30:00Z',
    }],
    overrides: [{
      criterion_id: 'confirm_current_loc',
      override_reason: 'Signed plan and LOC evidence match imported record.',
      comment: 'Accepted after source review.',
      actor_username: 'admin',
      actor_role: 'admin',
      created_at: '2026-07-08T10:30:00Z',
    }],
    criteria_results: [{
      criterion_id: 'confirm_current_loc',
      criterion_title: 'Confirm current LOC',
      result_status: 'Needs Review',
      severity: 'medium',
      finding_message: 'Criterion needs manager review.',
      evidence_refs: [{ source_json_path: 'client.levelOfCare', safe_preview: 'PHP' }],
      source_json_paths: ['client.levelOfCare'],
      manager_action_options: ['override with reason'],
    }],
    source_documents: sourceFileDeleted ? [] : [sourceDocumentPayload()],
    evidence_coverage_summary: { criteria_total: 42, criteria_with_evidence: 40, criteria_missing_evidence: 2 },
    content_snapshot: treatmentPlanSnapshot(),
  }
}

function sourceDocumentPayload() {
  return {
    source_file_id: 'source-file-812', source_kind: 'manual_treatment_plan_file', source_format: 'text', content_type: 'text/plain', size_bytes: 128,
    sha256: 'synthetic-safe-sha256', redaction_status: 'encrypted_original_file', created_at: '2026-07-08T10:00:00Z',
    download_url: '/api/v2/treatment-plans/812/source-documents/source-file-812/download',
  }
}

function treatmentPlanSnapshot() {
  return {
    reason_for_admission: 'Clinical rationale is present.',
    initial_client_needs: 'Initial needs include stabilization.',
    family_education_needs: 'Family education reviewed.',
    problems: [{
      problem_number: '1',
      problem_description: 'Recovery stabilization needs continued clinical support.',
      diagnoses: [{ icd10_code: 'F10.20', diagnosis_description: 'Synthetic active diagnosis' }],
      behavioral_definitions: [{ behavioral_definition: 'Synthetic behavioral definition.' }],
      goals: [{
        goal_number: '1',
        goal_description: 'Improve recovery stability.',
        objectives: [{
          objective_number: '1',
          objective_description: 'Identify three coping skills.',
          interventions: [{ intervention_description: 'Weekly skills practice.' }],
        }],
      }],
    }],
    signatures: [{
      signature_type: 'staff',
      signer_role_or_type: 'clinician',
      signature_datetime: '2026-07-01T15:30:00-04:00',
      has_signature_data: true,
      signature_data_omitted_reason: 'signature image/base64 never returned in default browser payload',
    }],
    observed_fields: [{
      field_path: 'signatures.staff.signatureData',
      value_type: 'string',
      state: 'redacted',
      sample_redacted_value: '[signature image omitted]',
      used_by_checklist: false,
    }],
  }
}

function settingsPayload() {
  return {
    organization_name: 'R3 Recovery Services',
    facility_timezone: 'America/New_York',
    treatment_plan_master_due_days: 30,
    treatment_plan_php_review_interval_days: 30,
    treatment_plan_iop_op_review_interval_days: 90,
    treatment_plan_loc_change_window_days: 7,
    treatment_plan_loc_change_window_validated: false,
  }
}

function apiConfigurationPayload(configured: boolean) {
  return {
    vendor_name: 'Alleva REST API',
    api_base_url: 'https://api.allevasoft.com',
    openapi_url: 'https://api.allevasoft.com/swagger/v1/swagger.json',
    token_url: 'https://api.allevasoft.com/connect/token',
    client_id: 'configured-client-id',
    api_key_configured: configured,
    client_secret_configured: configured,
    token_auth_style: 'body',
    scopes: '',
    pagination_limit: 500,
    sync_limit: 100,
    timeout_seconds: 10,
    api_enabled: false,
  }
}

function auditLogsPayload() {
  return {
    items: [{
      event_id: 'evt-1',
      timestamp_utc: '2026-07-08T10:00:00Z',
      actor_username: 'admin',
      actor_role: 'admin',
      action: 'settings.api_profile.saved',
      details: { client_secret_configured: true },
      target_entity_type: 'api_connection_profile', target_entity_id: 'Alleva REST API', outcome_status: 'success', prev_hash: '0', hash: 'abc',
    }],
  }
}

function jobPayload() {
  return {
    job_id: 'job-812',
    status: 'completed',
    progress_percent: 100,
    records_written: 6,
    records_failed: 0,
    warnings_count: 0,
    artifacts: [{ artifact_id: 'run-summary.json', name: 'run-summary.json', media_type: 'application/json', size_bytes: 200, redaction_mode: 'safe' }, { artifact_id: 'all-treatment-plans.all-fields.redacted.jsonl', name: 'all-treatment-plans.all-fields.redacted.jsonl', media_type: 'application/jsonl', size_bytes: 800, redaction_mode: 'safe' }],
  }
}
