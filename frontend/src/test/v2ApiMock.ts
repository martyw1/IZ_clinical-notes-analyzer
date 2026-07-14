import { vi } from 'vitest'
import { auditLogsPayload, auditVerificationPayload } from './v2AuditMock'

type Role = 'admin' | 'office_manager' | 'counselor' | 'viewer'

type FetchState = {
  readonly role: Role
  readonly failLogin?: boolean
  readonly harnessFails?: boolean
  readonly apiSaveFails?: boolean
  readonly workflowCreateFails?: boolean
  readonly mustResetPassword?: boolean
  readonly multiPlan?: boolean
}

export const adminNavigation = ['Status Dashboard', 'Treatment Plans', 'Patient Roster', 'Manual Upload', 'API Testing Harness', 'Users', 'Forensic Logs', 'Settings', 'Help'] as const

const counselorNavigation = ['Status Dashboard', 'Treatment Plans', 'Patient Roster', 'Manual Upload', 'Corrections', 'Help'] as const

export function setupFetch(state: FetchState = { role: 'admin' }) {
  const deletedSourceFileIds = new Set<string>(); let correctionSubmitted = false; let workflowProfileStatus: 'draft' | 'published' = 'draft'; let syncEnabled = false; let apiConfigured = false; let passwordResetRequired = state.mustResetPassword ?? false; let harnessPolls = 0
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const method = init?.method ?? 'GET'
    const path = pathFrom(input)

    if (path === '/api/auth/login' && method === 'POST') {
      if (state.failLogin) return jsonResponse({ detail: 'Invalid credentials' }, 401)
      return jsonResponse({ access_token: 'token-from-backend', token_type: 'bearer', must_reset_password: passwordResetRequired, auth_state: passwordResetRequired ? 'password_change_required' : 'active' })
    }
    if (path === '/api/users/me/change-password' && method === 'POST') { passwordResetRequired = false; return jsonResponse({ access_token: 'token-after-password-change', token_type: 'bearer', auth_state: 'active', must_reset_password: false }) }
    if (path === '/api/users/me') return jsonResponse({ ...userPayload(state.role), must_reset_password: passwordResetRequired, auth_state: passwordResetRequired ? 'password_change_required' : 'active' })
    if (path === '/api/v2/navigation') return jsonResponse({ items: state.role === 'admin' ? adminNavigation : counselorNavigation, active_runtime: 'v2' })
    if (path === '/api/v2/dashboard') return jsonResponse(dashboardPayload())
    if (path === '/api/v2/treatment-plans') return jsonResponse(treatmentPlansPayload(state.multiPlan))
    if (path === '/api/v2/patient-roster') return jsonResponse(patientRosterPayload())
    if (path === '/api/v2/exports/treatment-plans.csv') return treatmentPlanExportResponse()
    if (path === '/api/v2/treatment-plans/812') return jsonResponse(treatmentPlanDetailPayload(deletedSourceFileIds.has('source-file-812')))
    if (path === '/api/v2/treatment-plans/812/plan-812') return jsonResponse(treatmentPlanDetailPayload(deletedSourceFileIds.has('source-file-812'), 'plan-812'))
    if (path === '/api/v2/treatment-plans/812/plan-813') return jsonResponse(treatmentPlanDetailPayload(false, 'plan-813'))
    if (path === '/api/v2/treatment-plans/812/manager-actions' && method === 'POST') return jsonResponse({ status: 'saved' })
    if (path === '/api/v2/corrections') return jsonResponse({ items: correctionSubmitted ? [] : [correctionQueueItemPayload()] })
    if (path === '/api/v2/treatment-plans/812/correction-submissions' && method === 'POST') { correctionSubmitted = true; return jsonResponse({ status: 'submitted' }) }
    if (path === '/api/v2/treatment-plans/812/source-documents/source-file-812' && method === 'DELETE') {
      deletedSourceFileIds.add('source-file-812')
      return jsonResponse({ status: 'deleted', source_file_id: 'source-file-812', file_removed: true })
    }
    if (path === '/api/v2/treatment-plans/812/source-documents/source-file-812/download') return sourceDocumentDownloadResponse()
    if (path === '/api/v2/manual-uploads/treatment-plan-aggregate' && method === 'POST') return importResponse('812', false)
    if (path === '/api/v2/manual-uploads/treatment-plan-file' && method === 'POST') {
      const correctionConfirmed = init?.body instanceof FormData
        && init.body.get('confirm_patient_id_correction') === 'true'
      return importResponse('914', true, correctionConfirmed)
    }
    if (path === '/api/settings') return jsonResponse(settingsPayload())
    if (path === '/api/api-configuration') {
      if (method === 'PATCH' && typeof init?.body === 'string') {
        if (state.apiSaveFails) return jsonResponse({ detail: 'Configuration could not be saved' }, 503)
        const body = JSON.parse(init.body)
        apiConfigured = apiConfigured || typeof body.client_secret === 'string'
        syncEnabled = body.api_enabled === true
          && body.treatment_plan_sync_enabled === true
      }
      return jsonResponse(apiConfigurationPayload(apiConfigured, syncEnabled))
    }
    if (path === '/api/v2/alleva-sync/run' && method === 'POST') return jsonResponse(syncJobPayload('queued'), 202)
    if (path === '/api/v2/alleva-sync/jobs/sync-912') return jsonResponse(syncJobPayload('completed'))
    if (path === '/api/api-configuration/pull-definitions' && method === 'POST') return jsonResponse({ status: 'ok', definition_summary: { title: 'Mock Treatment Plan API', operation_count: 3 }, redaction_status: 'safe_summary_only' })
    if (path === '/api/api-configuration/test-connectivity' && method === 'POST') return jsonResponse({ status: 'ok', token_auth_style: 'body', message: 'OAuth client-credentials token obtained and discarded after verification.', token_type: 'Bearer', expires_in: 3600 })
    if (path === '/api/api-configuration/test-operation' && method === 'POST') return jsonResponse({ status: 'ok', message: 'Read-only operation completed.', status_code: 200, content_type: 'application/json', response_bytes: 24, response_truncated: false })
    if (path === '/api/users' && method === 'POST') return jsonResponse({ ...userPayload('counselor'), username: 'newcounselor', full_name: 'New Counselor', must_reset_password: true })
    if (path === '/api/users/2/reset-password' && method === 'POST') return jsonResponse({ ...userPayload('counselor'), must_reset_password: true })
    if (path === '/api/users') return jsonResponse([userPayload('admin'), userPayload('counselor')])
    if (path === '/api/facilities') return jsonResponse([{ id: 10, facility_key: 'r3-default', display_name: 'R3 Default Facility', timezone: 'America/New_York', is_active: true }])
    if (path === '/api/users/2/facilities/10' && method === 'PUT') return jsonResponse([10])
    if (path === '/api/patient-assignments/812/counselor' && method === 'PUT') return jsonResponse({ patient_id: '812', counselor_username: 'counselor', is_active: true })
    if (path === '/api/workflow-definitions' && method === 'POST' && state.workflowCreateFails) return jsonResponse({ detail: 'Workflow key already exists' }, 409)
    if (path === '/api/workflow-definitions') return jsonResponse([workflowProfilePayload(workflowProfileStatus)])
    if (path === '/api/workflow-definitions/7/versions/71/publish' && method === 'POST') {
      workflowProfileStatus = 'published'
      return jsonResponse(workflowProfilePayload(workflowProfileStatus))
    }
    if (path === '/api/audit/logs') return jsonResponse(auditLogsPayload())
    if (path === '/api/audit/verify') return jsonResponse(auditVerificationPayload)
    if (path === '/api/v2/api-harness/jobs' && method === 'POST') return jsonResponse(jobPayload('queued'))
    if (path === '/api/v2/api-harness/jobs/job-812') { harnessPolls += 1; return jsonResponse(jobPayload(harnessPolls > 20 ? (state.harnessFails ? 'failed' : 'completed') : 'running')) }
    if (path === '/api/v2/api-harness/jobs/job-812/artifacts') return jsonResponse(state.harnessFails ? [{ artifact_id: 'all-treatment-plans.error-log.jsonl', name: 'all-treatment-plans.error-log.jsonl', media_type: 'application/json', size_bytes: 180, redaction_mode: 'redacted' }] : jobPayload().artifacts)
    if (path === '/api/v2/api-harness/jobs/job-812/preview') return jsonResponse({ job_id: 'job-812', max_records: 25, max_fields: 50, records: [{ job_id: 'job-812', record_index: 1, record_id: 'TP-SYNTHETIC-1', source_endpoint: 'GET /treatment-plans', redaction_status: 'redacted' }], message: 'Preview is bounded to 25 records and 50 fields; full output is local artifact files.' })
    return jsonResponse({ detail: `Unexpected test route ${method} ${path}` }, 404)
  })

  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function pathFrom(input: RequestInfo | URL): string {
  const value = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
  return new URL(value, 'http://localhost').pathname
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

function treatmentPlanExportResponse(): Response {
  return new Response('patient_id,treatment_plan_id,status\r\n812,plan-812,Needs Review\r\n', {
    status: 200,
    headers: {
      'content-disposition': 'attachment; filename="treatment-plans.csv"',
      'content-type': 'text/csv',
    },
  })
}

function importResponse(patientId: string, archived: boolean, patientIdCorrectionApplied = false): Response {
  return jsonResponse({ status: 'imported', patient_id: patientId, patient_display_label: `Patient ID ${patientId}`, source_mode: 'manual_upload', criteria_total: 42, encrypted_at_rest: true, source_file_archived: archived, source_file_id: archived ? 'source-file-914' : null, patient_id_correction_applied: patientIdCorrectionApplied }, 201)
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
    auth_state: 'active',
    locked_until: null,
    facility_ids: role === 'admin' ? [10] : [],
    last_login_at: null,
    created_at: '2026-07-08T09:00:00Z',
  }
}

function dashboardPayload() {
  return {
    refreshed_at: '2026-07-11T12:00:00+00:00',
    source_cards: [
      { label: 'Manual upload readiness', status: 'ready', detail: 'Manual evidence accepted.' },
      { label: 'API readiness', status: 'configured for testing', detail: 'Alleva harness is bounded.' },
      { label: 'Alleva treatment-plan sync readiness', status: 'blocked', detail: 'Live sync remains gated.' },
    ],
    metrics: { active_patient_ids: 2, needs_review: 4, missing_data: 5, conflicting: 1, unable: 0 },
    blockers: ['LOC-change update window is unvalidated and configurable.'],
  }
}

function treatmentPlansPayload(multiPlan = false) {
  const baseItem = {
    patient_id: '812',
    patient_display_label: 'Patient ID 812',
    current_level_of_care: 'PHP',
    admission_date: '2026-06-01',
    status: 'Needs Review',
    missing_criteria_count: 2,
    returned_criteria_count: 0,
    source_mode: 'alleva_rest_api',
    warnings: ['LOC-change update window remains unvalidated.'],
  }
  return {
    items: [{
      ...baseItem,
      treatment_plan_id: 'plan-812',
      next_due_date: '2026-07-15',
    }, ...(multiPlan ? [{ ...baseItem, treatment_plan_id: 'plan-813', next_due_date: '2026-08-15' }] : [])],
    status_order: ['Missing Data', 'Needs Review', 'Incomplete', 'Within Window', 'Late', 'Conflicting Evidence', 'Unable to Evaluate'],
  }
}

function patientRosterPayload() {
  return {
    items: [{
      patient_id: '812',
      source_mode: 'alleva_rest_api',
      lifecycle_state: 'active',
      current_level_of_care: 'PHP',
      treatment_plan_id: 'plan-812',
      treatment_plan_status: 'Needs Review',
      first_seen_at: '2026-07-08T10:00:00Z',
      last_seen_at: '2026-07-12T10:00:00Z',
      reconciled_at: '2026-07-12T10:01:00Z',
    }],
  }
}

function correctionQueueItemPayload() { return { work_item_id: 71, plan_version_id: 18, patient_id: '812', patient_display_label: 'Patient ID 812', criterion_id: 'confirm_current_loc', criterion_title: 'Confirm current LOC', return_comment: 'Confirm the current LOC source.', returned_by_username: 'admin', returned_at: '2026-07-09T09:00:00Z' } }

function workflowProfilePayload(status: 'draft' | 'published') {
  const version = { id: 71, version: 1, status, version_notes: '' }
  return {
    id: 7,
    workflow_key: 'clinical_timeliness_review',
    display_name: 'Clinical Timeliness Review',
    description: 'Synthetic workflow profile for frontend validation.',
    is_active: true,
    current_version: status === 'published' ? version : null,
    versions: [version],
  }
}

function treatmentPlanDetailPayload(sourceFileDeleted = false, planId = 'plan-812') {
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
    data_quality_warnings: ['LOC-change update window remains unvalidated and configurable.'],
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
    content_snapshot: { ...treatmentPlanSnapshot(), plan_id: planId },
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

function apiConfigurationPayload(configured: boolean, syncEnabled: boolean) {
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
    api_enabled: syncEnabled,
    treatment_plan_sync_enabled: syncEnabled,
    treatment_plan_sync_approved: true,
    requests_per_minute: 600,
    active_contract_version: null,
    active_contract_effective_at: null,
  }
}

function jobPayload(status = 'completed') {
  return {
    job_id: 'job-812',
    status,
    progress_percent: 100,
    records_written: 6,
    records_failed: 0,
    warnings_count: 0,
    artifacts: [{ artifact_id: 'run-summary.json', name: 'run-summary.json', media_type: 'application/json', size_bytes: 200, redaction_mode: 'safe' }, { artifact_id: 'all-treatment-plans.all-fields.redacted.jsonl', name: 'all-treatment-plans.all-fields.redacted.jsonl', media_type: 'application/jsonl', size_bytes: 800, redaction_mode: 'safe' }],
  }
}

function syncJobPayload(status: string) {
  return { ...jobPayload(), job_id: 'sync-912', job_type: 'approved_treatment_plan_sync', status, records_written: status === 'completed' ? 1 : 0, records_failed: 0, warnings_count: 0 }
}
