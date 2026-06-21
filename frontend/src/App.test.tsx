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

function blobText(blob: Blob) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(reader.error)
    reader.readAsText(blob)
  })
}

function installFetchMock(routes: Record<string, unknown | RouteHandler>) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const rawUrl = typeof input === 'string' ? input : input.toString()
    const url = new URL(rawUrl, 'http://localhost')
    const key = `${(init?.method || 'GET').toUpperCase()} ${url.pathname}`
    const route = routes[key]
    if (!route) {
      if (key === 'GET /api/review-source-discovery') {
        return jsonResponse(200, reviewSourceDiscoveryPayload())
      }
      if (key === 'GET /api/users') {
        return jsonResponse(200, [userPayload('admin'), userPayload('manager'), userPayload('counselor')])
      }
      if (key === 'GET /api/workflow-definitions') {
        return jsonResponse(200, workflowDefinitionsPayload())
      }
      if (key === 'GET /api/emr/profiles') {
        return jsonResponse(200, emrEndpointProfilesPayload())
      }
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
    emr_vendor_name: 'Alleva REST API',
    api_client_id: '',
    api_client_secret_configured: false,
    api_oauth_token_url: 'https://authorization.allevasoft.com/connect/token',
    api_token_auth_style: 'body',
    emr_api_timeout_seconds: 10,
    emr_periodic_check_enabled: false,
    emr_periodic_check_interval_minutes: 1440,
    emr_last_check_at: null,
    emr_last_check_status: '',
    emr_last_check_message: '',
    emr_last_successful_check_at: null,
    emr_last_failure_at: null,
    alleva_api_base_url: 'https://api.allevasoft.com',
    alleva_openapi_url: 'https://api.allevasoft.com/swagger/v1/swagger.json',
    alleva_api_version: '1.0',
    alleva_treatment_plan_sync_enabled: false,
    alleva_treatment_plan_sync_on_startup: false,
    alleva_treatment_plan_sync_approved: false,
    alleva_treatment_plan_endpoint_mapping_validated: false,
    alleva_treatment_plan_sync_limit: 250,
    alleva_treatment_plan_sync_last_at: null,
    alleva_treatment_plan_sync_last_status: '',
    alleva_treatment_plan_sync_last_message: '',
    alleva_treatment_plan_sync_last_success_at: null,
    alleva_treatment_plan_sync_last_failure_at: null,
    treatment_plan_loc_change_window_days: 7,
    treatment_plan_loc_change_window_validated: false,
    updated_by_id: 1,
    updated_at: '2026-03-08T13:00:00Z',
  }
}

function emrProfilePayload() {
  return {
    vendor_name: 'Alleva REST API',
    adapter_key: 'alleva-rest-api',
    live_import_status: 'readiness_only_pending_approval_and_endpoint_mapping',
    enabled: false,
    api_base_url: 'https://api.allevasoft.com',
    openapi_url: 'https://api.allevasoft.com/swagger/v1/swagger.json',
    oauth_token_url_configured: true,
    client_id_configured: false,
    client_secret_configured: false,
    standards: ['Alleva REST API', 'OpenAPI operation discovery', 'HL7/API readiness'],
    supported_export_formats: ['PDF', 'DOCX', 'TXT', 'CSV', 'RTF', 'JPG', 'PNG', 'ZIP'],
    document_manager_sections: [
      { key: 'custom_forms', label: 'Custom Forms', expected_content: ['Admission packets', 'signed client forms'] },
      { key: 'uploaded_documents', label: 'Uploaded Documents', expected_content: ['External PDFs', 'Word documents'] },
      { key: 'portal_documents', label: 'Portal Documents', expected_content: ['Client-uploaded portal documents'] },
    ],
    required_vendor_inputs: ['R3/Alleva live-sync approval', 'OAuth token URL', 'API client ID', 'API client secret'],
  }
}

function emrEndpointProfilesPayload() {
  return [
    {
      id: 91,
      profile_key: 'alleva-default',
      display_name: 'Alleva Default',
      vendor_name: 'Alleva REST API',
      adapter_key: 'alleva-rest-api',
      api_base_url: 'https://api.allevasoft.com',
      openapi_url: 'https://api.allevasoft.com/swagger/v1/swagger.json',
      token_url: 'https://authorization.allevasoft.com/connect/token',
      token_auth_style: 'body',
      client_id: 'synthetic-client',
      client_id_configured: true,
      client_secret_configured: true,
      timeout_seconds: 10,
      is_active: true,
      is_default: true,
      notes: 'Synthetic Alleva endpoint profile.',
      created_by_id: 1,
      updated_by_id: 1,
      created_at: '2026-03-08T13:00:00Z',
      updated_at: '2026-03-08T13:00:00Z',
    },
  ]
}

function readinessPayload() {
  return {
    status: 'ok',
    failed: 0,
    warnings: 0,
    checks: [{ name: 'python', status: 'ok', message: 'Python 3.11 or newer is required.', detail: '3.14.4' }],
  }
}

function reviewSourceDiscoveryPayload() {
  return {
    checklist_id: 'treatment-plan-v1',
    checklist_version: '1.2.0',
    last_refreshed_at: '2026-06-11T12:00:00Z',
    last_refresh_at: '2026-06-11T12:00:00Z',
    next_refresh_at: '2026-06-12T12:00:00Z',
    live_import_enabled: false,
    live_import_status: 'disabled_until_vendor_credentials_mapping_and_compliance_approval',
    api_configured: false,
    api_mode: 'mock_stub',
    api_mode_label: 'Mock/stub mode',
    daily_monitoring_enabled: false,
    refresh_mode: 'daily_mock_simulation',
    changed_item_count: 2,
    error_count: 0,
    notification_badge_count: 2,
    manual_review_cadence: 'monthly_compliance_check',
    manual_mode_message:
      'Manual upload reflects only the uploaded documents as of upload time. For 60+ active charts, use a monthly compliance-check batch when API automation is unavailable.',
    plain_english_status:
      'Live Alleva import is still blocked. The app can simulate daily monitoring and run safe connectivity tests without pulling live patient charts.',
    status_counts: {
      'Not Reviewed': 0,
      'Ready for Review': 1,
      'In Review': 0,
      'Needs Human Review': 2,
      Passed: 0,
      Failed: 0,
      'Missing Required Data': 0,
      Error: 0,
      Finalized: 0,
    },
    items: [
      {
        source_type: 'api',
        source_item_id: 'mock-api-treatment-plan-001',
        patient_id: 'SYNTH-API-001',
        display_name: 'Synthetic API Treatment Plan',
        document_type: 'treatment_plan',
        source_system_or_file: 'Mock EMR/API source',
        review_status: 'Ready for Review',
        status_reason: 'Synthetic mock item available because live EMR import is not approved.',
        service_date: '2026-06-01',
        plan_date: '2026-06-01',
        provider_staff: 'Synthetic Provider',
        program_location: 'IOP-5',
        last_changed_at: '2026-06-11T12:00:00Z',
        review_chart_id: null,
        timeliness_client_id: null,
      },
      {
        source_type: 'upload',
        source_item_id: 'note-set-5',
        patient_id: 'PAT-001',
        display_name: 'Uploaded binder v1',
        document_type: 'clinical_note_binder',
        source_system_or_file: 'Alleva EMR',
        review_status: 'Needs Human Review',
        status_reason: 'Status is derived from the latest linked chart review.',
        service_date: '04/01/2025',
        plan_date: '',
        provider_staff: 'Marleigh Johnson',
        program_location: 'Residential',
        last_changed_at: '2026-03-08T12:00:00Z',
        review_chart_id: 8,
        timeliness_client_id: null,
      },
    ],
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
    version: '1.2.0',
    display_name: 'Treatment Plan Checklist Version 1 - 42 Step PRD',
    organization: 'R3 Recovery Services',
    status: 'version_1_ready_with_42_steps_and_loc_change_blocker',
    last_updated: '2026-06-11',
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
    steps: Array.from({ length: 42 }, (_unused, index) => ({
      step: index + 1,
      key:
        index === 0
          ? 'confirm_correct_client_chart'
          : index === 33
            ? 'require_manual_override_reason'
            : index === 41
              ? 'use_synthetic_or_approved_non_phi_data'
              : `step_${index + 1}`,
      title:
        index === 0
          ? 'Confirm this is the correct client chart'
          : index === 33
            ? 'Require a reason for manual overrides'
            : index === 41
              ? 'Use synthetic or approved non-PHI data for validation until production handling is approved'
              : `Checklist step ${index + 1}`,
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
      status_options: ['Confirmed', 'Needs Review', 'Missing Data', 'Overridden'],
      reviewer_actions: ['Confirm', 'Override', 'Return for Correction'],
      manual_override: true,
      override_reason_required: true,
      audit_event: `treatment_plan.checklist.step_${String(index + 1).padStart(2, '0')}.reviewed`,
      export_fields: ['status', 'source_evidence', 'finding_message', 'severity', 'reviewer_action', 'override_reason'],
    })),
  }
}

function versionPayload() {
  return {
    app_name: 'IZ Clinical Notes Analyzer',
    version: '1.4.4-beta.1',
    build: '2026.06.21.1',
    release_channel: 'beta-local-desktop',
    release_date: '2026-06-21',
    stability: 'beta',
    is_prerelease: true,
    version_name: 'Beta 1.4.4-beta.1 treatment-plan checklist detail visibility',
    environment: 'test',
    git_commit: 'abcdef123456',
    git_branch: 'main',
    git_dirty: false,
  }
}

function timelinessChecklistResultsPayload() {
  const representativeSteps: Record<number, { key: string; title: string; status: string; finding_message: string; evidence_fields_used: string[] }> = {
    1: {
      key: 'confirm_correct_client_chart',
      title: 'Confirm this is the correct client chart',
      status: 'Confirmed',
      finding_message: 'Selected treatment-plan client is keyed by patient ID PAT-TP-001.',
      evidence_fields_used: ['patient_id', 'source_evidence'],
    },
    4: {
      key: 'confirm_admission_date',
      title: 'Confirm the admission date',
      status: 'Confirmed',
      finding_message: 'Admission date is 2026-02-26.',
      evidence_fields_used: ['admission_date'],
    },
    6: {
      key: 'confirm_loc_rule_mapping',
      title: 'Confirm the LOC maps to a Version 1 rule category',
      status: 'Confirmed',
      finding_message: 'LOC IOP-5 maps to configured 60-calendar-day review clock.',
      evidence_fields_used: ['current_level_of_care', 'mapped_level_of_care'],
    },
    14: {
      key: 'initial_plan_exists',
      title: 'Check that the Initial Treatment Plan exists',
      status: 'Missing Data',
      finding_message: 'Initial Treatment Plan evidence is missing.',
      evidence_fields_used: ['document_type', 'source_document_id'],
    },
    17: {
      key: 'master_plan_exists',
      title: 'Check that the Master Treatment Plan exists',
      status: 'Missing Data',
      finding_message: 'Master Treatment Plan evidence is missing.',
      evidence_fields_used: ['document_type', 'source_document_id'],
    },
    21: {
      key: 'calculate_next_review_due_date',
      title: 'Calculate the next Treatment Plan Review due date',
      status: 'Due Soon',
      finding_message: 'Date clock due date is 2026-06-01.',
      evidence_fields_used: ['date_clock_anchor_date', 'interval_days', 'next_due_date'],
    },
    31: {
      key: 'loc_change_deadline_unresolved',
      title: 'Hold the LOC-change deadline as unresolved until R3 confirms it',
      status: 'Needs Review',
      finding_message: 'LOC-change window remains unvalidated by R3/Marleigh.',
      evidence_fields_used: ['loc_change_window_days', 'loc_change_rule_validated'],
    },
    32: {
      key: 'flag_missing_data_not_compliance',
      title: 'Flag missing data instead of assuming compliance',
      status: 'Missing Data',
      finding_message: 'Missing evidence fields: Source-document Next Review Due.',
      evidence_fields_used: ['missing_evidence_fields', 'rule_used'],
    },
    34: {
      key: 'require_manual_override_reason',
      title: 'Require a reason for manual overrides',
      status: 'Not Applicable',
      finding_message: 'No manual override is recorded for this selected client.',
      evidence_fields_used: ['override_reason', 'affected_rule'],
    },
    35: {
      key: 'produce_final_checklist_result',
      title: 'Produce a final checklist result for the chart',
      status: 'Due Soon',
      finding_message: 'Final selected-client result is Due Soon.',
      evidence_fields_used: ['overall_status', 'evidence_summary'],
    },
  }
  return Array.from({ length: 42 }, (_unused, index) => {
    const stepNumber = index + 1
    const representative = representativeSteps[stepNumber]
    return {
      step: stepNumber,
      key: representative?.key || `step_${stepNumber}`,
      title: representative?.title || `Checklist step ${stepNumber}`,
      status: representative?.status || 'Needs Review',
      result: representative?.status || 'Needs Review',
      severity: stepNumber === 31 ? 'critical' : 'high',
      source_evidence: 'Synthetic Treatment Plan Review; Synthetic LOC update',
      finding_message: representative?.finding_message || 'Reviewer should confirm this checklist item for the selected client.',
      evidence_fields_used: representative?.evidence_fields_used || ['source_evidence'],
      required_metadata: ['patient_id'],
      required_documents: ['treatment_plan_documents'],
      checks: ['Synthetic deterministic check.'],
      finding_examples: ['Synthetic finding.'],
      remediation_suggestions: ['Synthetic remediation.'],
      reviewer_actions: ['Confirm', 'Override', 'Return for Correction'],
      manual_override_allowed: true,
      override_reason_required: true,
      audit_event: `treatment_plan.checklist.step_${String(stepNumber).padStart(2, '0')}.reviewed`,
      export_fields: ['status', 'source_evidence', 'finding_message', 'severity', 'reviewer_action', 'override_reason'],
    }
  })
}

function timelinessDashboardPayload() {
  return {
    total_active_clients: 1,
    compliant: 0,
    due_soon: 1,
    urgent: 0,
    overdue: 0,
    returned: 0,
    needs_review: 0,
    missing_data: 0,
    conflicting_evidence: 0,
    unable_to_evaluate: 0,
    approved: 0,
    compliance_percentage: 0,
    loc_change_window_days: 7,
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
        current_date: '2026-05-23',
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
    checklist_id: 'treatment-plan-v1',
    checklist_version: '1.2.0',
    evidence_comparison: {
      document_next_due_date: null,
      signature_anchor_due_date: '2026-06-01',
      loc_anchor_due_date: '2026-04-06',
      current_date: '2026-05-23',
      date_clock_anchor_date: '2026-04-02',
      date_clock_anchor_source: 'last valid treatment-plan review/update date',
      date_clock_due_date: '2026-06-01',
      loc_change_due_date: '2026-04-06',
      final_status: 'Due Soon',
      conflict_explanation:
        'source document Next Review Due is not recorded; date clock due date is 2026-06-01 from last valid treatment-plan review/update date 2026-04-02 plus 60 days; LOC-change due date is 2026-04-06 (2026-03-30 + 7 days); LOC-change window is set to 7 calendar days but remains unvalidated by R3/Marleigh.',
      source_evidence: 'Treatment Plan Review synthetic record; Synthetic LOC update',
      staff_signature_date: '2026-04-02',
      loc_effective_date: '2026-03-30',
      interval_days: 60,
      loc_change_window_days: 7,
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
        due_date: '2026-04-06',
        status: 'Needs Review',
        evidence_summary: 'LOC-change update preset is 7 calendar days, but settings still mark the rule unvalidated; manual review is required.',
      },
    ],
    checklist_results: timelinessChecklistResultsPayload(),
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
    next_due_date: '2026-04-06',
    days_until_due: -51,
    current_date: '2026-05-27',
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
      loc_anchor_due_date: '2026-04-06',
      current_date: '2026-05-27',
      date_clock_anchor_date: '2026-04-02',
      date_clock_anchor_source: 'last valid treatment-plan review/update date',
      date_clock_due_date: '2026-06-01',
      loc_change_due_date: '2026-04-06',
      final_status: 'Needs Review',
      conflict_explanation:
        'source document Next Review Due is 2026-05-29; date clock due date is 2026-06-01 from last valid treatment-plan review/update date 2026-04-02 plus 60 days; LOC-change due date is 2026-04-06 (2026-03-30 + 7 days); LOC-change window is set to 7 calendar days but remains unvalidated by R3/Marleigh.',
      source_evidence: 'Treatment Plan Review synthetic record; Synthetic LOC update',
      staff_signature_date: '2026-04-02',
      loc_effective_date: '2026-03-30',
      interval_days: 60,
      loc_change_window_days: 7,
      loc_change_rule_validated: false,
    },
    rule_results: [
      ...timelinessDetailPayload().rule_results,
      {
        rule_id: 'TP-DUE-DATE-CONFLICT',
        label: 'Displayed and calculated due dates',
        due_date: '2026-04-06',
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
    window.sessionStorage.clear()
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
    window.history.replaceState(null, '', '/?view=dashboard')
    installFetchMock({
      'GET /api/version': versionPayload(),
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
    await waitFor(() => expect(screen.getByText(/Beta v1\.4\.4-beta\.1/)).toBeInTheDocument())
    expect(screen.getAllByRole('button', { name: 'User management' }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: 'My account' }).length).toBeGreaterThan(0)
    expect(screen.getByText('Waiting re-verification')).toBeInTheDocument()
    expect(screen.getByText('Mock/stub mode')).toBeInTheDocument()
    expect(screen.getByText('Monthly compliance-check fallback')).toBeInTheDocument()
    expect(screen.getByText('As of upload time only')).toBeInTheDocument()
  })

  it('restores a same-browser session and lands managers on treatment plans', async () => {
    window.sessionStorage.setItem('iz-cna-session-token', 'stored-manager-token')
    const fetchMock = installFetchMock({
      'GET /api/users/me': userPayload('manager'),
      'GET /api/charts': [],
      'GET /api/patient-note-sets': [],
      'GET /api/timeliness/dashboard': timelinessDashboardPayload(),
      'GET /api/timeliness/clients/21': timelinessDetailPayload(),
    })

    render(<App />)

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Treatment plan timeliness' })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'Sign in' })).not.toBeInTheDocument()
    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/api/auth/login'))).toBe(false)
  })

  it('shows the canonical Treatment Plan Checklist Version 1', async () => {
    window.history.replaceState(null, '', '/?view=dashboard')
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

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Treatment Plan Checklist Version 1 - 42 Step PRD' })).toBeInTheDocument())
    expect(screen.getByText('Application Programming Interface')).toBeInTheDocument()
    expect(screen.getByText(/Confirm this is the correct client chart/)).toBeInTheDocument()
    expect(screen.getByText(/Require a reason for manual overrides/)).toBeInTheDocument()
    expect(screen.getByText(/Use synthetic or approved non-PHI data/)).toBeInTheDocument()
    const checklistHeader = screen.getByRole('heading', { name: 'Treatment Plan Checklist Version 1 - 42 Step PRD' }).closest('.panel-heading')
    expect(checklistHeader).not.toBeNull()
    fireEvent.click(within(checklistHeader as HTMLElement).getByRole('button', { name: 'Workflow profiles' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Workflow profiles' })).toBeInTheDocument())
  })

  it('shows manager-scoped user management, workflow profiles, and help without admin-only settings', async () => {
    window.history.replaceState(null, '', '/?view=dashboard')
    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-manager-scope', must_reset_password: false },
      'GET /api/users/me': userPayload('manager'),
      'GET /api/charts': [chartSummary()],
      'GET /api/patient-note-sets': [noteSetSummary()],
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
      'GET /api/users': [userPayload('counselor')],
      'GET /api/workflow-definitions': workflowDefinitionsPayload(),
    })

    render(<App />)
    signIn()

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Summary dashboard' })).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: 'App settings' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Forensic logs' })).not.toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: 'User management' })[0])
    await waitFor(() => expect(screen.getByRole('heading', { name: 'User management' })).toBeInTheDocument())
    expect(screen.getByText(/Office managers can maintain counselor accounts/)).toBeInTheDocument()
    expect(screen.getAllByText('Counselor One').length).toBeGreaterThan(0)
    expect(screen.queryByText('System Administrator')).not.toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: 'Workflow profiles' })[0])
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Workflow profiles' })).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Seed draft from 42-step checklist' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Help' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Role permissions' })).toBeInTheDocument())
    expect(screen.getByText('Office manager')).toBeInTheDocument()
    expect(screen.getByText(/Open App settings, API\/EMR configuration/)).toBeInTheDocument()
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
    expect(evidenceDialog.getByText('Date clock due date')).toBeInTheDocument()
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
      'GET /api/version': versionPayload(),
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
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Patient Details' })).toBeInTheDocument())
    expect(screen.getByText('Patient ID: PAT-001')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }))
    fireEvent.click(screen.getByRole('button', { name: 'Export JSON' }))

    fireEvent.click(screen.getByRole('button', { name: 'Treatment plans' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Treatment plan timeliness' })).toBeInTheDocument())
    await waitFor(() => expect(screen.getByRole('heading', { name: '42-Step Checklist Evaluation' })).toBeInTheDocument())
    expect(screen.getByText('Step 1. Confirm this is the correct client chart')).toBeInTheDocument()
    expect(screen.getByText('Step 31. Hold the LOC-change deadline as unresolved until R3 confirms it')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Export task list' }))
    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }))
    fireEvent.click(screen.getByRole('button', { name: 'Export JSON' }))

    expect(createObjectUrl).toHaveBeenCalledTimes(5)
    expect(anchorClick).toHaveBeenCalledTimes(5)
    expect(revokeObjectUrl).toHaveBeenCalledTimes(5)
    const exportedTexts = await Promise.all(createObjectUrl.mock.calls.map((call) => blobText(call[0] as Blob)))
    expect(exportedTexts.some((text) => text.includes('checklist_result') && text.includes('loc_change_deadline_unresolved'))).toBe(true)
    expect(exportedTexts.some((text) => text.includes('"checklist_results"') && text.includes('produce_final_checklist_result'))).toBe(true)
  })

  it('runs the Alleva treatment-plan sync from the review queue and opens treatment plans', async () => {
    let syncRequested = false
    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-review-sync', must_reset_password: false },
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
      'POST /api/alleva/treatment-plan-sync/run': () => {
        syncRequested = true
        return {
          body: {
            sync_result: {
              status: 'ok',
              message: 'Alleva treatment-plan sync completed; 1 active client(s) loaded, 1 treatment plan record(s), 0 review record(s).',
              upserted_client_count: 1,
              active_client_count: 1,
              treatment_plan_count: 1,
              treatment_review_count: 0,
            },
            settings: appSettingsPayload(),
          },
        }
      },
    })

    render(<App />)
    signIn()

    await waitFor(() => expect(screen.getByRole('button', { name: 'Review queue' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Review queue' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Pull active treatment plans' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Pull active treatment plans' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Treatment plan timeliness' })).toBeInTheDocument())
    expect(screen.getByText(/1 active client\(s\) loaded/)).toBeInTheDocument()
    expect(syncRequested).toBe(true)
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

  it('deletes an uploaded binder and linked review from the manual upload screen', async () => {
    window.history.replaceState(null, '', '/?view=uploads')
    let noteSetList = [noteSetSummary()]
    let chartList = [chartSummary()]

    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-delete-binder', must_reset_password: false },
      'GET /api/users/me': userPayload('admin'),
      'GET /api/charts': () => ({ body: chartList }),
      'GET /api/patient-note-sets': () => ({ body: noteSetList }),
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
      'GET /api/users': [userPayload('admin')],
      'GET /api/settings': appSettingsPayload(),
      'GET /api/emr/profile': emrProfilePayload(),
      'GET /api/system/readiness': readinessPayload(),
      'GET /api/workflow-definitions': workflowDefinitionsPayload(),
      'DELETE /api/patient-note-sets/5': () => {
        noteSetList = []
        chartList = []
        return { body: { status: 'deleted', deleted_note_set_id: 5, deleted_review_chart_ids: [8], deleted_document_count: 1 } }
      },
    })

    render(<App />)
    signIn()

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Uploaded binders' })).toBeInTheDocument())
    fireEvent.change(screen.getByLabelText('Type patient ID to confirm'), { target: { value: 'PAT-001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Delete uploaded binder' }))

    await waitFor(() => expect(screen.getByText('Deleted uploaded binder version 1 for patient PAT-001.')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /PAT-001/i })).not.toBeInTheDocument()
  })

  it('keeps the delete uploaded binder button clickable before confirmation so guidance is shown', async () => {
    window.history.replaceState(null, '', '/?view=uploads')
    let deleteCalls = 0

    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-delete-guidance', must_reset_password: false },
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
      'DELETE /api/patient-note-sets/5': () => {
        deleteCalls += 1
        return { body: { status: 'deleted' } }
      },
    })

    render(<App />)
    signIn()

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Uploaded binders' })).toBeInTheDocument())
    const deleteButton = screen.getByRole('button', { name: 'Delete uploaded binder' })

    expect(deleteButton).toBeEnabled()
    fireEvent.click(deleteButton)

    await waitFor(() =>
      expect(screen.getAllByText('Type the patient ID exactly before deleting this uploaded binder.').length).toBeGreaterThan(0),
    )
    expect(deleteCalls).toBe(0)
  })

  it('opens an existing uploaded binder review from the manual upload screen', async () => {
    window.history.replaceState(null, '', '/?view=uploads')

    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-open-uploaded-review', must_reset_password: false },
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

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Binder details' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Open automated review' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Patient Details' })).toBeInTheDocument())
    expect(screen.getByText('Patient ID: PAT-001')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Criterion review workbench' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Open binder details' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Binder details' })).toBeInTheDocument())
    expect(screen.getByText(/Patient PAT-001, version 1, uploaded/)).toBeInTheDocument()
  })

  it('lets an office manager drill into a criterion and save a decision', async () => {
    window.history.replaceState(null, '', '/?view=reviews')
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
    window.history.replaceState(null, '', '/?view=dashboard')
    let directory = [userPayload('admin'), userPayload('manager')]
    let savedSettings = appSettingsPayload()

    installFetchMock({
      'POST /api/auth/login': { access_token: 'token-d', must_reset_password: false },
      'GET /api/users/me': userPayload('admin'),
      'GET /api/charts': [chartSummary()],
      'GET /api/patient-note-sets': [noteSetSummary()],
      'GET /api/charts/8': chartDetail(),
      'GET /api/patient-note-sets/5': noteSetDetail(),
      'GET /api/users': () => ({ body: directory }),
      'GET /api/settings': () => ({ body: savedSettings }),
      'GET /api/emr/profile': emrProfilePayload(),
      'GET /api/system/readiness': readinessPayload(),
      'GET /api/workflow-definitions': workflowDefinitionsPayload(),
      'PATCH /api/settings': (_path: string, init?: RequestInit) => {
        const body = JSON.parse(String(init?.body || '{}'))
        savedSettings = {
          ...savedSettings,
          organization_name: body.organization_name,
          llm_enabled: body.llm_enabled,
          llm_provider_name: body.llm_provider_name,
          llm_base_url: body.llm_base_url,
          llm_model: body.llm_model,
          llm_api_key_configured: Boolean(body.llm_api_key) || savedSettings.llm_api_key_configured,
          emr_api_enabled: body.emr_api_enabled,
          emr_vendor_name: body.emr_vendor_name,
          api_client_id: body.api_client_id,
          api_client_secret_configured:
            Boolean(body.api_client_secret) || (savedSettings.api_client_secret_configured && !body.clear_api_client_secret),
          api_oauth_token_url: body.api_oauth_token_url,
          api_token_auth_style: body.api_token_auth_style,
          emr_api_timeout_seconds: body.emr_api_timeout_seconds,
          emr_periodic_check_enabled: body.emr_periodic_check_enabled,
          emr_periodic_check_interval_minutes: body.emr_periodic_check_interval_minutes,
          alleva_api_base_url: body.alleva_api_base_url,
          alleva_openapi_url: body.alleva_openapi_url,
          alleva_api_version: body.alleva_api_version,
          alleva_treatment_plan_sync_enabled: body.alleva_treatment_plan_sync_enabled,
          alleva_treatment_plan_sync_on_startup: body.alleva_treatment_plan_sync_on_startup,
          alleva_treatment_plan_sync_approved: body.alleva_treatment_plan_sync_approved,
          alleva_treatment_plan_endpoint_mapping_validated: body.alleva_treatment_plan_endpoint_mapping_validated,
          alleva_treatment_plan_sync_limit: body.alleva_treatment_plan_sync_limit,
          treatment_plan_loc_change_window_days: body.treatment_plan_loc_change_window_days,
          treatment_plan_loc_change_window_validated: body.treatment_plan_loc_change_window_validated,
        }
        return { body: savedSettings }
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

    fireEvent.click(screen.getByRole('button', { name: 'App settings' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Application settings' })).toBeInTheDocument())
    expect(screen.getByRole('heading', { name: 'Active Alleva/API connection' })).toBeInTheDocument()
    expect(screen.getByText(/source of truth for readiness checks/i)).toBeInTheDocument()
    expect(screen.getByText(/pasting the client ID and client secret here is expected/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Alleva REST/OpenAPI readiness' })).toBeInTheDocument()
    expect(screen.getByText('alleva-rest-api')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Use for active API settings' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /discovery/i })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Workflow profiles' })).toBeInTheDocument()
    expect(screen.getByText('treatment_plan_followup')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Seed draft from 42-step checklist' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Organization name'), { target: { value: 'R3 Recovery Services QA' } })
    fireEvent.click(screen.getByLabelText('Enable LLM-assisted analysis'))
    fireEvent.change(screen.getByLabelText('LLM API key'), { target: { value: 'sk-test-123' } })
    fireEvent.change(screen.getByLabelText('API client ID'), { target: { value: 'rest-client' } })
    fireEvent.change(screen.getByLabelText('API client secret'), { target: { value: 'rest-secret' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save settings' }))
    await waitFor(() => expect(screen.getByText('Application settings have been saved and verified.')).toBeInTheDocument())
    expect(savedSettings.api_client_id).toBe('rest-client')
    expect(savedSettings.api_client_secret_configured).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: 'Forensic logs' }))
    await waitFor(() => expect(screen.getByText('chart.system_evaluated')).toBeInTheDocument())
  })

  it('lets an admin edit and delete a selected managed user', async () => {
    window.history.replaceState(null, '', '/?view=users')
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
