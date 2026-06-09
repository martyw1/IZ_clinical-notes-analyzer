import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'

type RouteHandler = (path: string, init?: RequestInit) => { status?: number; body?: unknown }

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
  } as Response
}

function installFetchMock(routes: Record<string, unknown | RouteHandler>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const rawUrl = typeof input === 'string' ? input : input.toString()
    const url = new URL(rawUrl, 'http://localhost')
    const key = `${(init?.method || 'GET').toUpperCase()} ${url.pathname}`
    const route = routes[key]
    if (!route) {
      throw new Error(`Unhandled request ${key}`)
    }

    if (typeof route === 'function') {
      const result = route(url.pathname, init)
      return jsonResponse(result.status ?? 200, result.body)
    }

    return jsonResponse(200, route)
  })

  globalThis.fetch = fn as unknown as typeof window.fetch
  return fn
}

function userPayload(role: 'admin' | 'counselor' | 'manager', mustResetPassword = false) {
  return {
    id: role === 'admin' ? 1 : role === 'manager' ? 2 : 3,
    username: role,
    full_name: role === 'manager' ? 'Office Manager' : role === 'counselor' ? 'Counselor One' : 'System Administrator',
    role,
    is_active: true,
    is_locked: false,
    must_reset_password: mustResetPassword,
    last_login_at: '2026-03-08T12:00:00Z',
    created_at: '2026-03-08T11:00:00Z',
  }
}

function chartSummary(state: string = 'Awaiting Office Manager Review') {
  return {
    id: 8,
    source_note_set_id: 5,
    patient_id: 'PAT-001',
    client_name: 'PAT-001',
    level_of_care: 'Residential',
    admission_date: '04/01/2025',
    discharge_date: '09/10/2025',
    primary_clinician: 'Marleigh Johnson',
    auditor_name: 'Counselor One',
    other_details: 'Auto-generated from uploaded clinical note binder.',
    counselor_id: 3,
    state,
    system_score: 84,
    system_summary: 'System evaluation completed for patient PAT-001.',
    manager_comment: state === 'Returned to Counselor' ? 'Attendance consent is missing a clear selection.' : '',
    reviewed_by_id: state === 'Awaiting Office Manager Review' ? null : 2,
    system_generated_at: '2026-03-08T12:00:00Z',
    reviewed_at: state === 'Awaiting Office Manager Review' ? null : '2026-03-08T13:00:00Z',
    created_at: '2026-03-08T12:00:00Z',
    notes: 'Binder uploaded from Alleva.',
    pending_items: 2,
    passed_items: 13,
    failed_items: 3,
    not_applicable_items: 0,
  }
}

function chartDetail(state: string = 'Awaiting Office Manager Review') {
  return {
    ...chartSummary(state),
    checklist_items: [
      {
        item_key: 'attendance_policy_consent',
        step: 5,
        section: 'Other / Admission Packet',
        label: 'Attendance Policy Consent',
        timeframe: 'Completed at admission',
        instructions: 'Verify that exactly one Accept or Decline option is selected and the form is fully signed.',
        evidence_hint: 'Note the selected option and whether both signatures are present.',
        policy_note: null,
        status: 'no',
        notes: 'Accept or Decline could not be confirmed from the uploaded packet.',
        evidence_location: 'Attendance Policy Consent (custom forms)',
        evidence_date: '04/01/2025',
        expiration_date: '',
      },
      {
        item_key: 'client_overview_primary_clinician',
        step: 2,
        section: 'Header Verification',
        label: 'Primary clinician assignment',
        timeframe: 'Audit setup',
        instructions: 'Confirm the primary clinician field is populated correctly in Client Overview before continuing the audit.',
        evidence_hint: 'Capture where the clinician assignment was verified and note any mismatch.',
        policy_note: null,
        status: 'yes',
        notes: 'Primary clinician supplied with uploaded binder.',
        evidence_location: 'Upload header',
        evidence_date: '04/01/2025',
        expiration_date: '',
      },
    ],
  }
}

function noteSetSummary() {
  return {
    id: 5,
    patient_id: 'PAT-001',
    review_chart_id: 8,
    version: 1,
    status: 'active',
    upload_mode: 'initial',
    source_system: 'Alleva EMR',
    primary_clinician: 'Marleigh Johnson',
    level_of_care: 'Residential',
    admission_date: '04/01/2025',
    discharge_date: '09/10/2025',
    upload_notes: 'Initial Alleva upload.',
    created_at: '2026-03-08T12:00:00Z',
    file_count: 1,
  }
}

function noteSetDetail() {
  return {
    ...noteSetSummary(),
    documents: [
      {
        id: 14,
        document_label: 'Intake Packet',
        original_filename: 'intake-packet.txt',
        content_type: 'text/plain',
        size_bytes: 2048,
        sha256: 'a'.repeat(64),
        alleva_bucket: 'custom_forms',
        document_type: 'clinical_note',
        completion_status: 'completed',
        client_signed: true,
        staff_signed: true,
        document_date: '04/01/2025',
        description: 'Admission binder import.',
        created_at: '2026-03-08T12:00:00Z',
      },
    ],
  }
}

function appSettingsPayload() {
  return {
    organization_name: 'R3 Recovery Services',
    access_intel_enabled: true,
    access_geo_lookup_url: 'https://ipwho.is/{ip}',
    access_reputation_url: 'https://api.abuseipdb.com/api/v2/check',
    access_reputation_api_key_configured: false,
    access_lookup_timeout_seconds: 4,
    llm_enabled: false,
    llm_provider_name: 'OpenAI-compatible',
    llm_base_url: 'https://api.openai.com/v1',
    llm_model: 'gpt-4.1-mini',
    llm_api_key_configured: false,
    llm_use_for_access_review: true,
    llm_use_for_evaluation_gap_analysis: true,
    llm_analysis_instructions: '',
    emr_api_enabled: false,
    emr_vendor_name: 'Alleva / SMART on FHIR',
    emr_fhir_base_url: '',
    emr_smart_client_id: '',
    emr_smart_client_secret_configured: false,
    emr_smart_scopes: 'openid fhirUser launch/patient patient/Patient.rs patient/DocumentReference.rs patient/Binary.rs patient/Provenance.rs',
    emr_api_timeout_seconds: 10,
    treatment_plan_loc_change_window_days: null,
    treatment_plan_loc_change_window_validated: false,
    updated_by_id: 1,
    updated_at: '2026-03-08T13:00:00Z',
  }
}

function emrProfilePayload() {
  return {
    vendor_name: 'Alleva / SMART on FHIR',
    adapter_key: 'alleva-smart-fhir-document-manager',
    live_import_status: 'disabled',
    enabled: false,
    fhir_base_url: '',
    smart_discovery_url: null,
    client_id_configured: false,
    client_secret_configured: false,
    scopes: ['openid', 'fhirUser', 'launch/patient', 'patient/Patient.rs', 'patient/DocumentReference.rs', 'patient/Binary.rs', 'patient/Provenance.rs'],
    supported_resources: ['Patient', 'DocumentReference', 'Binary', 'Provenance'],
    standards: ['HL7 FHIR R4 DocumentReference', 'HL7 FHIR R4 Binary', 'HL7 FHIR R4 Provenance', 'SMART App Launch OAuth2'],
    supported_export_formats: ['PDF', 'DOCX', 'TXT', 'CSV', 'RTF', 'JPG', 'PNG', 'ZIP'],
    document_manager_sections: [
      { key: 'custom_forms', label: 'Custom Forms', expected_content: ['Admission packets', 'signed client forms'] },
      { key: 'uploaded_documents', label: 'Uploaded Documents', expected_content: ['External PDFs', 'Word documents'] },
      { key: 'portal_documents', label: 'Portal Documents', expected_content: ['Client-uploaded portal documents'] },
    ],
    required_vendor_inputs: ['Alleva tenant FHIR base URL', 'SMART client ID', 'SMART client secret'],
  }
}

function readinessPayload() {
  return {
    status: 'ok',
    failed: 0,
    warnings: 0,
    checks: [{ name: 'python', status: 'ok', message: 'Python 3.11 or newer is required.', detail: '3.14.4' }],
  }
}

function workflowDefinitionsPayload() {
  const currentVersion = {
    id: 61,
    workflow_definition_id: 51,
    version: 1,
    status: 'published',
    definition_snapshot: { steps: [{ key: 'review_due_date', label: 'Review due date' }] },
    transition_rules: [{ from: 'draft', to: 'ready_for_review', roles: ['admin'] }],
    version_notes: 'Initial workflow profile.',
    created_by_id: 1,
    published_by_id: 1,
    archived_by_id: null,
    created_at: '2026-05-23T11:00:00Z',
    published_at: '2026-05-23T11:05:00Z',
    archived_at: null,
  }
  return [
    {
      id: 51,
      workflow_key: 'treatment_plan_followup',
      display_name: 'Treatment Plan Follow-up',
      description: 'Synthetic workflow profile for due-date follow-up.',
      category: 'treatment_plan',
      is_active: true,
      current_version_id: 61,
      created_by_id: 1,
      updated_by_id: 1,
      created_at: '2026-05-23T11:00:00Z',
      updated_at: '2026-05-23T11:05:00Z',
      current_version: currentVersion,
      versions: [currentVersion],
    },
  ]
}

function treatmentPlanChecklistPayload() {
  return {
    checklist_id: 'treatment-plan-v1',
    version: '1.0.0',
    display_name: 'Treatment Plan Checklist Version 1',
    organization: 'R3 Recovery Services',
    status: 'version_1_ready_with_loc_change_blocker',
    last_updated: '2026-06-09',
    source_of_truth: 'config/checklists/treatment-plan-v1.json',
    review_owner_roles: ['admin', 'manager'],
    viewer_roles: ['admin', 'manager', 'counselor'],
    acronyms: [
      { term: 'API', definition: 'Application Programming Interface', validation_status: 'standard' },
      { term: 'EMR', definition: 'Electronic Medical Record', validation_status: 'standard' },
      { term: 'PHI', definition: 'Protected Health Information', validation_status: 'standard' },
    ],
    review_statuses: [
      { key: 'not_reviewed', label: 'Not Reviewed', description: 'The item is known but not reviewed.' },
      { key: 'needs_human_review', label: 'Needs Human Review', description: 'The item needs a reviewer.' },
      { key: 'finalized', label: 'Finalized', description: 'The final disposition is saved.' },
    ],
    loc_change_blocker: {
      status: 'unvalidated',
      owner: 'R3/Marleigh',
      message: 'The treatment-plan update window after a level-of-care change is not confirmed.',
    },
    steps: Array.from({ length: 20 }, (_unused, index) => ({
      step: index + 1,
      key: index === 0 ? 'select_review_source' : index === 19 ? 'audit_and_traceability' : `step_${index + 1}`,
      title: index === 0 ? 'Select review source' : index === 19 ? 'Audit and traceability' : `Checklist step ${index + 1}`,
      source_modes: ['api', 'upload'],
      objective: 'Synthetic checklist objective.',
      required_metadata: ['patient_id'],
      required_documents: [],
      checks: ['Synthetic deterministic check.'],
      finding_examples: ['Synthetic finding.'],
      remediation_suggestions: ['Synthetic remediation.'],
      evidence_fields: ['source_document'],
      automation_level: 'deterministic',
      severity_default: 'high',
    })),
  }
}

function timelinessDashboardPayload() {
  return {
    total_active_clients: 1,
    compliant: 0,
    due_soon: 1,
    urgent: 0,
    overdue: 0,
    needs_review: 0,
    missing_data: 0,
    compliance_percentage: 0,
    loc_change_window_days: null,
    loc_change_window_validated: false,
    items: [
      {
        id: 21,
        patient_id: 'PAT-TP-001',
        permitted_name: 'Synthetic Client',
        current_level_of_care: 'IOP-5',
        counselor_name: 'Counselor One',
        admission_date: '2026-02-26',
        last_valid_review_date: '2026-04-02',
        next_due_date: '2026-06-01',
        days_until_due: 9,
        status: 'Due Soon',
        rule_used: 'TP-REVIEW-60',
        evidence_summary: 'Latest valid staff/therapist review signature was 2026-04-02 using IOP-5 60-day recurrence.',
        evidence_completeness_percent: 83,
        missing_evidence_fields: ['Source-document Next Review Due'],
        last_checked_at: '2026-05-23T12:00:00Z',
        last_imported_at: '2026-05-23T11:00:00Z',
      },
    ],
  }
}

function timelinessDetailPayload() {
  return {
    ...timelinessDashboardPayload().items[0],
    is_active: true,
    source_evidence: 'Synthetic spreadsheet row',
    evidence_comparison: {
      document_next_due_date: null,
      signature_anchor_due_date: '2026-06-01',
      loc_anchor_due_date: '2026-05-29',
      final_status: 'Due Soon',
      conflict_explanation:
        'source document Next Review Due is not recorded; staff signature anchor is 2026-06-01 (2026-04-02 + 60 days); LOC effective-date anchor is 2026-05-29 (2026-03-30 + 60 days); LOC-change anchor/window is unvalidated by R3/Marleigh.',
      source_evidence: 'Treatment Plan Review synthetic record; Synthetic LOC update',
      staff_signature_date: '2026-04-02',
      loc_effective_date: '2026-03-30',
      interval_days: 60,
      loc_change_window_days: null,
      loc_change_rule_validated: false,
    },
    rule_results: [
      {
        rule_id: 'TP-REVIEW-60',
        label: 'Ongoing Treatment Plan Review',
        due_date: '2026-06-01',
        status: 'Due Soon',
        evidence_summary: 'Latest valid staff/therapist review signature was 2026-04-02 using IOP-5 60-day recurrence.',
      },
      {
        rule_id: 'TP-LOC-CHANGE-UNVALIDATED',
        label: 'Level-of-care change update',
        due_date: '2026-03-30',
        status: 'Needs Review',
        evidence_summary: 'LOC-change update window is not validated by R3/Marleigh; manual review is required.',
      },
    ],
    level_of_care_history: [
      {
        id: 31,
        level_of_care: 'PHP',
        facility: 'Synthetic Facility',
        effective_date: '2026-02-26',
        discharge_date: '2026-03-30',
        interval_days: 30,
        is_current: false,
        source_evidence: 'Synthetic admission LOC',
      },
      {
        id: 32,
        level_of_care: 'IOP-5',
        facility: 'Synthetic Facility',
        effective_date: '2026-03-30',
        discharge_date: '',
        interval_days: 60,
        is_current: true,
        source_evidence: 'Synthetic LOC update',
      },
    ],
    treatment_plans: [
      {
        id: 41,
        plan_kind: 'review',
        document_date: '2026-04-02',
        staff_signature_date: '2026-04-02',
        client_signature_date: '',
        reviewer_signature_date: '',
        displayed_next_due_date: '',
        source_evidence: 'Synthetic Treatment Plan Review',
        source_section: 'Treatment Plan Reviews',
        source_document_id: 'doc-41',
        is_valid: true,
        conflict_note: '',
      },
    ],
    overrides: [],
    audit_history: [
      {
        event_id: 'evt-tp-1',
        timestamp_utc: '2026-05-23T12:00:00Z',
        actor_username: 'admin',
        actor_role: 'admin',
        actor_type: 'human',
        source_ip: '127.0.0.1',
        request_id: 'req-tp-1',
        event_category: 'workflow',
        action: 'timeliness.client.read',
        patient_id: 'PAT-TP-001',
        message: 'Treatment Plan Timeliness client PAT-TP-001 viewed.',
        details: '{}',
        outcome_status: 'success',
        severity: 'info',
      },
    ],
  }
}

function timelinessConflictSummary() {
  return {
    id: 22,
    patient_id: 'PAT-TP-AMBIG',
    permitted_name: 'Ambiguous Review Client',
    current_level_of_care: 'IOP-5',
    counselor_name: 'Counselor Two',
    admission_date: '2026-02-26',
    last_valid_review_date: '2026-04-02',
    next_due_date: '2026-05-29',
    days_until_due: 2,
    status: 'Needs Review',
    rule_used: 'TP-DUE-DATE-CONFLICT',
    evidence_summary: 'Displayed Next Review Due conflicts with the staff-signature anchor while LOC-change timing remains unvalidated.',
    evidence_completeness_percent: 100,
    missing_evidence_fields: [],
    last_checked_at: '2026-05-27T12:00:00Z',
    last_imported_at: '2026-05-27T11:00:00Z',
  }
}

function timelinessConflictDetailPayload() {
  return {
    ...timelinessDetailPayload(),
    ...timelinessConflictSummary(),
    evidence_comparison: {
      document_next_due_date: '2026-05-29',
      signature_anchor_due_date: '2026-06-01',
      loc_anchor_due_date: '2026-05-29',
      final_status: 'Needs Review',
      conflict_explanation:
        'source document Next Review Due is 2026-05-29; staff signature anchor is 2026-06-01 (2026-04-02 + 60 days); LOC effective-date anchor is 2026-05-29 (2026-03-30 + 60 days); LOC-change anchor/window is unvalidated by R3/Marleigh.',
      source_evidence: 'Treatment Plan Review synthetic record; Synthetic LOC update',
      staff_signature_date: '2026-04-02',
      loc_effective_date: '2026-03-30',
      interval_days: 60,
      loc_change_window_days: null,
      loc_change_rule_validated: false,
    },
    rule_results: [
      ...timelinessDetailPayload().rule_results,
      {
        rule_id: 'TP-DUE-DATE-CONFLICT',
        label: 'Displayed and calculated due dates',
        due_date: '2026-05-29',
        status: 'Needs Review',
        evidence_summary: 'Due-date evidence conflicts and needs manual review.',
      },
    ],
    treatment_plans: [
      {
        ...timelinessDetailPayload().treatment_plans[0],
        displayed_next_due_date: '2026-05-29',
      },
    ],
  }
}

function signIn() {
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'admin' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'r3!@analyzer#123' } })
  fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
}

describe('App turnkey workflow', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    window.history.replaceState(null, '', '/')
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: vi.fn(() => 'blob:synthetic-export'),
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: vi.fn(),
    })
  })

  it('renders the summary dashboard and admin tools for administrators', async () => {
    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-a', must_reset_password: false },
      'GET /api/users/me': userPayload('admin'),
      'GET /api/charts': [chartSummary()],
      'GET /api/patient-note-sets': [noteSetSummary()],
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
      'GET /api/users': [userPayload('admin')],
      'GET /api/settings': appSettingsPayload(),
      'GET /api/emr/profile': emrProfilePayload(),
      'GET /api/system/readiness': readinessPayload(),
      'GET /api/workflow-definitions': workflowDefinitionsPayload(),
    })

    render(<App />)
    signIn()

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Summary dashboard' })).toBeInTheDocument())
    expect(screen.getAllByRole('button', { name: 'User management' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: 'My account' }).length).toBeGreaterThan(0)
    expect(screen.getByText('Waiting re-verification')).toBeInTheDocument()
  })

  it('shows the canonical Treatment Plan Checklist Version 1', async () => {
    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-checklist', must_reset_password: false },
      'GET /api/users/me': userPayload('admin'),
      'GET /api/charts': [chartSummary()],
      'GET /api/patient-note-sets': [noteSetSummary()],
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
      'GET /api/users': [userPayload('admin')],
      'GET /api/settings': appSettingsPayload(),
      'GET /api/emr/profile': emrProfilePayload(),
      'GET /api/system/readiness': readinessPayload(),
      'GET /api/workflow-definitions': workflowDefinitionsPayload(),
      'GET /api/treatment-plan-checklist': treatmentPlanChecklistPayload(),
    })

    render(<App />)
    signIn()

    await waitFor(() => expect(screen.getByRole('button', { name: 'Checklist' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Checklist' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Treatment Plan Checklist Version 1' })).toBeInTheDocument())
    expect(screen.getByText('Application Programming Interface')).toBeInTheDocument()
    expect(screen.getByText(/Select review source/)).toBeInTheDocument()
    expect(screen.getByText(/Audit and traceability/)).toBeInTheDocument()
  })

  it('shows treatment plan timeliness detail and records a manual override', async () => {
    let overrideSaved = false
    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-tp', must_reset_password: false },
      'GET /api/users/me': userPayload('admin'),
      'GET /api/charts': [chartSummary()],
      'GET /api/patient-note-sets': [noteSetSummary()],
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
      'GET /api/users': [userPayload('admin')],
      'GET /api/settings': appSettingsPayload(),
      'GET /api/emr/profile': emrProfilePayload(),
      'GET /api/system/readiness': readinessPayload(),
      'GET /api/workflow-definitions': workflowDefinitionsPayload(),
      'GET /api/timeliness/dashboard': timelinessDashboardPayload(),
      'GET /api/timeliness/clients/21': () => ({
        body: {
          ...timelinessDetailPayload(),
          overrides: overrideSaved
            ? [
                {
                  id: 99,
                  field_name: 'status',
                  original_value: 'Due Soon',
                  new_value: 'Needs Review',
                  reason: 'Synthetic manager review.',
                  affected_rule: 'TP-REVIEW-60',
                  created_by_id: 1,
                  created_at: '2026-05-23T12:30:00Z',
                },
              ]
            : [],
        },
      }),
      'POST /api/timeliness/clients/21/overrides': (_path: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body || '{}'))
        overrideSaved = true
        return {
          body: {
            id: 99,
            field_name: body.field_name,
            original_value: body.original_value,
            new_value: body.new_value,
            reason: body.reason,
            affected_rule: body.affected_rule,
            created_by_id: 1,
            created_at: '2026-05-23T12:30:00Z',
          },
        }
      },
    })

    render(<App />)
    signIn()

    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Treatment plans' }).length).toBeGreaterThan(0))
    fireEvent.click(screen.getAllByRole('button', { name: 'Treatment plans' })[0])
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Treatment plan timeliness' })).toBeInTheDocument())
    expect(screen.getByText(/Updated evidence queue/)).toBeInTheDocument()
    expect(screen.getAllByText('Synthetic Client').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Unvalidated by R3\/Marleigh/i).length).toBeGreaterThan(0)
    expect(screen.getByRole('heading', { name: 'Rule results' })).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Reason'), { target: { value: 'Synthetic manager review.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save override' }))

    await waitFor(() => expect(screen.getByText('Treatment plan override recorded for patient PAT-TP-001.')).toBeInTheDocument())
    expect(screen.getByText(/Synthetic manager review/i)).toBeInTheDocument()
  })

  it('filters the timeliness queue and opens date-conflict evidence', async () => {
    const dashboard = {
      ...timelinessDashboardPayload(),
      total_active_clients: 2,
      due_soon: 1,
      needs_review: 1,
      items: [timelinessDashboardPayload().items[0], timelinessConflictSummary()],
    }

    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-tp-filter', must_reset_password: false },
      'GET /api/users/me': userPayload('admin'),
      'GET /api/charts': [chartSummary()],
      'GET /api/patient-note-sets': [noteSetSummary()],
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
      'GET /api/users': [userPayload('admin')],
      'GET /api/settings': appSettingsPayload(),
      'GET /api/emr/profile': emrProfilePayload(),
      'GET /api/system/readiness': readinessPayload(),
      'GET /api/workflow-definitions': workflowDefinitionsPayload(),
      'GET /api/timeliness/dashboard': dashboard,
      'GET /api/timeliness/clients/21': timelinessDetailPayload(),
      'GET /api/timeliness/clients/22': timelinessConflictDetailPayload(),
    })

    render(<App />)
    signIn()

    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Treatment plans' }).length).toBeGreaterThan(0))
    fireEvent.click(screen.getAllByRole('button', { name: 'Treatment plans' })[0])
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Treatment plan timeliness' })).toBeInTheDocument())
    expect(screen.getByRole('status', { name: 'Treatment plan timeliness update status' })).toHaveTextContent(/Source-document Next Review Due/)
    fireEvent.click(screen.getByRole('button', { name: /Needs Review 1/i }))

    fireEvent.click(screen.getByRole('button', { name: /Open Ambiguous Review Client treatment plan evidence/i }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Ambiguous Review Client' })).toBeInTheDocument())
    expect(screen.getAllByText('2026-05-29').length).toBeGreaterThan(0)
    expect(screen.getAllByText('2026-06-01').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Unvalidated LOC-change rule/i).length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: 'View evidence' }))
    await waitFor(() => expect(screen.getByRole('dialog', { name: 'Review due-date evidence' })).toBeInTheDocument())
    const evidenceDialog = within(screen.getByRole('dialog', { name: 'Review due-date evidence' }))
    expect(evidenceDialog.getByText('Source-document Next Review Due')).toBeInTheDocument()
    expect(evidenceDialog.getByText('Staff signature + LOC cadence')).toBeInTheDocument()
  })

  it('copies an Asana-ready timeliness task list', async () => {
    const writeText = vi.fn(async () => undefined)
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })

    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-tp-copy', must_reset_password: false },
      'GET /api/users/me': userPayload('admin'),
      'GET /api/charts': [chartSummary()],
      'GET /api/patient-note-sets': [noteSetSummary()],
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
      'GET /api/users': [userPayload('admin')],
      'GET /api/settings': appSettingsPayload(),
      'GET /api/emr/profile': emrProfilePayload(),
      'GET /api/system/readiness': readinessPayload(),
      'GET /api/workflow-definitions': workflowDefinitionsPayload(),
      'GET /api/timeliness/dashboard': timelinessDashboardPayload(),
      'GET /api/timeliness/clients/21': timelinessDetailPayload(),
    })

    render(<App />)
    signIn()

    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Treatment plans' }).length).toBeGreaterThan(0))
    fireEvent.click(screen.getAllByRole('button', { name: 'Treatment plans' })[0])
    await waitFor(() => expect(screen.getByRole('button', { name: 'Copy task list' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Copy task list' }))

    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1))
    expect(writeText.mock.calls[0][0]).toContain('client_label')
    expect(writeText.mock.calls[0][0]).toContain('Synthetic Client')
  })

  it('exports selected review and treatment plan reports as CSV and JSON', async () => {
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const createObjectUrl = vi.mocked(URL.createObjectURL)
    const revokeObjectUrl = vi.mocked(URL.revokeObjectURL)

    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-export', must_reset_password: false },
      'GET /api/users/me': userPayload('admin'),
      'GET /api/charts': [chartSummary()],
      'GET /api/patient-note-sets': [noteSetSummary()],
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
      'GET /api/users': [userPayload('admin')],
      'GET /api/settings': appSettingsPayload(),
      'GET /api/emr/profile': emrProfilePayload(),
      'GET /api/system/readiness': readinessPayload(),
      'GET /api/workflow-definitions': workflowDefinitionsPayload(),
      'GET /api/timeliness/dashboard': timelinessDashboardPayload(),
      'GET /api/timeliness/clients/21': timelinessDetailPayload(),
    })

    render(<App />)
    signIn()

    await waitFor(() => expect(screen.getByRole('button', { name: 'Review queue' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Review queue' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Patient PAT-001' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }))
    fireEvent.click(screen.getByRole('button', { name: 'Export JSON' }))

    fireEvent.click(screen.getByRole('button', { name: 'Treatment plans' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Treatment plan timeliness' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Export task list' }))
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }))
    fireEvent.click(screen.getByRole('button', { name: 'Export JSON' }))

    expect(createObjectUrl).toHaveBeenCalledTimes(5)
    expect(anchorClick).toHaveBeenCalledTimes(5)
    expect(revokeObjectUrl).toHaveBeenCalledTimes(5)
  })

  it('uploads a note binder and opens the generated automated review', async () => {
    let chartCalls = 0
    let noteSetCalls = 0

    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-b', must_reset_password: false },
      'GET /api/users/me': userPayload('counselor'),
      'POST /api/patient-note-sets/detect-patient-id': {
        patient_id: 'PAT-001',
        confidence: 'high',
        source_filename: 'intake-packet.txt',
        source_kind: 'text_label',
        match_text: 'Patient ID: PAT-001',
        reason: 'Detected patient ID from labeled content in intake-packet.txt.',
      },
      'GET /api/charts': () => {
        chartCalls += 1
        return { body: chartCalls === 1 ? [] : [chartSummary()] }
      },
      'GET /api/patient-note-sets': () => {
        noteSetCalls += 1
        return { body: noteSetCalls === 1 ? [] : [noteSetSummary()] }
      },
      'POST /api/patient-note-sets': noteSetDetail(),
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
    })

    render(<App />)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'counselor' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'password-1234' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Manual upload' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Manual upload' }))

    fireEvent.change(screen.getByLabelText('Client name'), { target: { value: 'Aegis Test' } })
    fireEvent.change(screen.getByLabelText('Level of care'), { target: { value: 'Residential' } })
    fireEvent.change(screen.getByLabelText('Primary clinician'), { target: { value: 'Marleigh Johnson' } })
    fireEvent.change(screen.getByLabelText('Clinical note files'), {
      target: {
        files: [new File(['Intake packet completed.'], 'intake-packet.txt', { type: 'text/plain' })],
      },
    })
    await waitFor(() => expect(screen.getByLabelText('Patient ID')).toHaveValue('PAT-001'))
    fireEvent.click(screen.getByRole('button', { name: 'Upload and run automated evaluation' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Criterion review workbench' })).toBeInTheDocument())
    expect(screen.getAllByText('Attendance Policy Consent').length).toBeGreaterThan(0)
  })

  it('lets an office manager drill into a criterion and save a decision', async () => {
    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-c', must_reset_password: false },
      'GET /api/users/me': userPayload('manager'),
      'GET /api/charts': [chartSummary()],
      'GET /api/patient-note-sets': [noteSetSummary()],
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
      'PUT /api/charts/8': (_path: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body || '{}'))
        const savedItem = body.checklist_items.find((item: { item_key: string }) => item.item_key === 'attendance_policy_consent')
        return {
          body: {
            ...chartDetail(),
            checklist_items: [
              {
                ...chartDetail().checklist_items[0],
                status: savedItem.status,
                notes: savedItem.notes,
              },
              chartDetail().checklist_items[1],
            ],
          },
        }
      },
    })

    render(<App />)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'manager' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'password-1234' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Review queue' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Review queue' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Criterion review workbench' })).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Mark OK' }))
    fireEvent.change(screen.getByLabelText('Reviewer notes'), {
      target: { value: 'Manager confirmed the consent page manually.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save criterion review changes' }))

    await waitFor(() => expect(screen.getAllByText('Confirmed').length).toBeGreaterThan(0))
  })

  it('shows profile management, admin user management, and forensic logs', async () => {
    let directory = [userPayload('admin'), userPayload('manager')]

    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-d', must_reset_password: false },
      'GET /api/users/me': userPayload('admin'),
      'GET /api/charts': [chartSummary()],
      'GET /api/patient-note-sets': [noteSetSummary()],
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
      'GET /api/users': () => ({ body: directory }),
      'GET /api/settings': appSettingsPayload(),
      'GET /api/emr/profile': emrProfilePayload(),
      'GET /api/system/readiness': readinessPayload(),
      'GET /api/workflow-definitions': workflowDefinitionsPayload(),
      'PATCH /api/settings': (_path: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body || '{}'))
        return {
          body: {
            ...appSettingsPayload(),
            organization_name: body.organization_name,
            llm_enabled: body.llm_enabled,
            llm_provider_name: body.llm_provider_name,
            llm_base_url: body.llm_base_url,
            llm_model: body.llm_model,
            llm_api_key_configured: true,
            emr_api_enabled: body.emr_api_enabled,
            emr_vendor_name: body.emr_vendor_name,
            emr_fhir_base_url: body.emr_fhir_base_url,
            emr_smart_client_id: body.emr_smart_client_id,
            emr_smart_client_secret_configured: Boolean(body.emr_smart_client_secret),
            emr_smart_scopes: body.emr_smart_scopes,
            emr_api_timeout_seconds: body.emr_api_timeout_seconds,
            treatment_plan_loc_change_window_days: body.treatment_plan_loc_change_window_days,
            treatment_plan_loc_change_window_validated: body.treatment_plan_loc_change_window_validated,
          },
        }
      },
      'POST /api/emr/discover': {
        status: 'ok',
        metadata_url: 'https://alleva.example.com/fhir/.well-known/smart-configuration',
        authorization_endpoint_configured: true,
        token_endpoint_configured: true,
        document_reference_supported: true,
        binary_supported: true,
      },
      'GET /api/emr/import-plan': {
        patient_id: 'PAT-001',
        vendor_name: 'Alleva / SMART on FHIR',
        live_import_enabled: false,
        planned_requests: [
          {
            step: 1,
            method: 'GET',
            url: 'DocumentReference?patient=PAT-001&status=current&_sort=-date',
            purpose: 'Find Alleva Document Manager records for the patient.',
          },
        ],
        local_export_guidance: ['Export Custom Forms, Uploaded Documents, and Portal Documents from Alleva Document Manager.'],
        required_scopes: ['patient/Patient.rs', 'patient/DocumentReference.rs', 'patient/Binary.rs'],
        alleva_notes: ['Map Alleva Document Manager sections into import buckets.'],
        supported_export_formats: ['PDF', 'DOCX', 'TXT', 'CSV', 'RTF', 'JPG', 'PNG', 'ZIP'],
        document_manager_sections: emrProfilePayload().document_manager_sections,
        attachment_handling: 'Fetch Binary URLs with the same SMART bearer token.',
      },
      'POST /api/users': (_path: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body || '{}'))
        const created = {
          ...userPayload('counselor'),
          id: 7,
          username: body.username,
          full_name: body.full_name,
          role: body.role,
          must_reset_password: true,
        }
        directory = [...directory, created]
        return { body: created }
      },
      'PATCH /api/users/me': { ...userPayload('admin'), full_name: 'System Administrator Updated' },
      'GET /api/audit/logs': [
        {
          event_id: 'evt-1',
          timestamp_utc: '2026-03-08T13:00:00Z',
          actor_username: 'admin',
          actor_role: 'admin',
          actor_type: 'human',
          source_ip: '127.0.0.1',
          request_id: 'req-1',
          event_category: 'workflow',
          action: 'chart.system_evaluated',
          patient_id: 'PAT-001',
          message: 'Automated evaluation completed for chart 8.',
          details: '{}',
          outcome_status: 'success',
          severity: 'info',
        },
      ],
    })

    render(<App />)
    signIn()

    await waitFor(() => expect(screen.getAllByRole('button', { name: 'My account' }).length).toBeGreaterThan(0))
    fireEvent.click(screen.getAllByRole('button', { name: 'My account' })[0])
    await waitFor(() => expect(screen.getByRole('heading', { name: 'User profile' })).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'System Administrator Updated' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save profile' }))

    await waitFor(() => expect(screen.getByText('Your profile has been updated.')).toBeInTheDocument())
    fireEvent.click(screen.getAllByRole('button', { name: 'User management' })[0])
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Create user' })).toBeInTheDocument())
    const createUserSection = screen.getByRole('heading', { name: 'Create user' }).closest('section')
    expect(createUserSection).not.toBeNull()
    const createUserScope = within(createUserSection as HTMLElement)
    fireEvent.change(createUserScope.getByLabelText('Username'), { target: { value: 'counselor-02' } })
    fireEvent.change(createUserScope.getByLabelText('Full name'), { target: { value: 'Counselor Two' } })
    fireEvent.change(createUserScope.getByLabelText('Temporary password'), { target: { value: 'temporary-pass-1234' } })
    fireEvent.click(createUserScope.getByRole('button', { name: 'Create user' }))

    await waitFor(() => expect(screen.getByText('User counselor-02 created successfully.')).toBeInTheDocument())
    expect(screen.getAllByText('Counselor Two').length).toBeGreaterThan(0)
    expect(screen.getAllByText('counselor-02').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: 'Settings' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Application settings' })).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: 'Alleva import profile' })).toBeInTheDocument()
    expect(screen.getByText('alleva-smart-fhir-document-manager')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Workflow profiles' })).toBeInTheDocument()
    expect(screen.getByText('treatment_plan_followup')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Organization name'), { target: { value: 'R3 Recovery Services QA' } })
    fireEvent.click(screen.getByLabelText('Enable LLM-assisted analysis'))
    fireEvent.change(screen.getByLabelText('LLM API key'), { target: { value: 'sk-test-123' } })
    fireEvent.change(screen.getByLabelText('FHIR base URL'), { target: { value: 'https://alleva.example.com/fhir' } })
    fireEvent.click(screen.getByRole('button', { name: 'Check SMART discovery' }))
    await waitFor(() => expect(screen.getByText(/Discovery: ok/i)).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Import plan patient ID'), { target: { value: 'PAT-001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Build import plan' }))
    await waitFor(() => expect(screen.getByText(/DocumentReference\?patient=PAT-001/i)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }))
    await waitFor(() => expect(screen.getByText('Application settings have been updated.')).toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: 'Forensic logs' }))
    await waitFor(() => expect(screen.getByText('chart.system_evaluated')).toBeInTheDocument())
  })

  it('lets an admin edit and delete a selected managed user', async () => {
    let directory = [userPayload('admin'), userPayload('manager')]

    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-edit-delete', must_reset_password: false },
      'GET /api/users/me': userPayload('admin'),
      'GET /api/charts': [chartSummary()],
      'GET /api/patient-note-sets': [noteSetSummary()],
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
      'GET /api/users': () => ({ body: directory }),
      'GET /api/settings': appSettingsPayload(),
      'GET /api/emr/profile': emrProfilePayload(),
      'GET /api/system/readiness': readinessPayload(),
      'GET /api/workflow-definitions': workflowDefinitionsPayload(),
      'PATCH /api/users/2': (_path: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body || '{}'))
        directory = directory.map((entry) =>
          entry.id === 2
            ? {
                ...entry,
                full_name: body.full_name,
                role: body.role,
                is_active: body.is_active,
                is_locked: body.is_locked,
                must_reset_password: body.must_reset_password,
              }
            : entry,
        )
        return { body: directory.find((entry) => entry.id === 2) }
      },
      'DELETE /api/users/2': () => {
        directory = directory.filter((entry) => entry.id !== 2)
        return { body: { status: 'deleted' } }
      },
    })

    render(<App />)
    signIn()

    await waitFor(() => expect(screen.getAllByRole('button', { name: 'User management' }).length).toBeGreaterThan(0))
    fireEvent.click(screen.getAllByRole('button', { name: 'User management' })[0])
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Manage selected user' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /Office Manager/i }))

    const manageSection = screen.getByRole('heading', { name: 'Manage selected user' }).closest('section')
    expect(manageSection).not.toBeNull()
    const manageScope = within(manageSection as HTMLElement)

    fireEvent.change(manageScope.getByLabelText('Full name'), { target: { value: 'Office Manager Updated' } })
    fireEvent.click(manageScope.getByLabelText('Locked'))
    fireEvent.click(manageScope.getByRole('button', { name: 'Save selected user' }))

    await waitFor(() => expect(screen.getByText('Updated user manager.')).toBeInTheDocument())
    expect(screen.getAllByText('Office Manager Updated').length).toBeGreaterThan(0)

    fireEvent.change(manageScope.getByLabelText('Type username to confirm'), { target: { value: 'manager' } })
    fireEvent.click(manageScope.getByRole('button', { name: 'Delete user' }))

    await waitFor(() => expect(screen.getByText('Deleted user manager.')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /Office Manager Updated/i })).not.toBeInTheDocument()
  })

  it('completes a required password reset before loading the workspace', async () => {
    let meCalls = 0
    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-e', must_reset_password: true },
      'GET /api/users/me': () => {
        meCalls += 1
        return { body: userPayload('counselor', meCalls === 1) }
      },
      'POST /api/auth/reset-password': { status: 'ok' },
      'GET /api/charts': [],
      'GET /api/patient-note-sets': [],
    })

    render(<App />)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'counselor' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'password-1234' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(screen.getByText('Password reset required')).toBeInTheDocument())
    fireEvent.change(screen.getByPlaceholderText('New password (min 12 chars)'), {
      target: { value: 'new-password-1234' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Reset password' }))

    await waitFor(() => expect(screen.getByRole('button', { name: 'Chart audit' })).toBeInTheDocument())
  })
})
