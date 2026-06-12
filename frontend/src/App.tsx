import { ChangeEvent, FormEvent, MouseEvent, useEffect, useMemo, useRef, useState } from 'react'
import './app.css'

const API = import.meta.env.VITE_API_URL || '/api'

type Role = 'admin' | 'counselor' | 'manager'
type WorkflowState =
  | 'Draft'
  | 'Awaiting Office Manager Review'
  | 'Returned to Counselor'
  | 'Approved by Office Manager'
type ComplianceStatus = 'pending' | 'yes' | 'no' | 'na'
type NoteSetStatus = 'active' | 'superseded'
type NoteSetUploadMode = 'initial' | 'update'
type AllevaBucket = 'custom_forms' | 'uploaded_documents' | 'portal_documents' | 'labs' | 'medications' | 'notes' | 'other'
type DocumentCompletionStatus = 'completed' | 'incomplete' | 'draft'
type AppView = 'dashboard' | 'reviews' | 'timeliness' | 'checklist' | 'uploads' | 'profile' | 'users' | 'logs' | 'settings'

type VersionInfo = {
  app_name: string
  version: string
  build: string
  release_channel: string
  release_date: string
  version_name: string
  environment: string
  git_commit: string
  git_branch: string
  git_dirty: boolean
}

type User = {
  id: number
  username: string
  full_name: string
  role: Role
  is_active: boolean
  is_locked: boolean
  must_reset_password: boolean
  last_login_at: string | null
  created_at: string | null
}

type AuditItem = {
  item_key: string
  step: number
  section: string
  label: string
  timeframe: string
  instructions: string
  evidence_hint: string
  policy_note: string | null
  status: ComplianceStatus
  notes: string
  evidence_location: string
  evidence_date: string
  expiration_date: string
}

type ChartSummary = {
  id: number
  source_note_set_id: number | null
  patient_id: string
  client_name: string
  level_of_care: string
  admission_date: string
  discharge_date: string
  primary_clinician: string
  auditor_name: string
  other_details: string
  counselor_id: number
  state: WorkflowState
  system_score: number
  system_summary: string
  manager_comment: string
  reviewed_by_id: number | null
  system_generated_at: string | null
  reviewed_at: string | null
  created_at: string | null
  notes: string
  pending_items: number
  passed_items: number
  failed_items: number
  not_applicable_items: number
}

type ChartDetail = ChartSummary & {
  checklist_items: AuditItem[]
}

type PatientNoteDocument = {
  id: number
  document_label: string
  original_filename: string
  content_type: string
  size_bytes: number
  sha256: string
  alleva_bucket: AllevaBucket
  document_type: string
  completion_status: DocumentCompletionStatus
  client_signed: boolean
  staff_signed: boolean
  document_date: string
  description: string
  source_document_id: string
  source_document_reference_id: string
  source_attachment_url: string
  source_author: string
  source_custodian: string
  source_security_label: string
  source_provenance_id: string
  created_at: string
}

type PatientNoteSetSummary = {
  id: number
  patient_id: string
  review_chart_id: number | null
  version: number
  status: NoteSetStatus
  upload_mode: NoteSetUploadMode
  source_system: string
  primary_clinician: string
  level_of_care: string
  admission_date: string
  discharge_date: string
  upload_notes: string
  source_export_id: string
  source_patient_resource_id: string
  created_at: string
  file_count: number
}

type PatientNoteSetDetail = PatientNoteSetSummary & {
  documents: PatientNoteDocument[]
}

type AuditLogRecord = {
  event_id: string
  timestamp_utc: string
  timestamp_local?: string
  effective_timezone?: string
  actor_username: string | null
  actor_role: string | null
  actor_type: string
  source_ip: string | null
  request_id: string
  event_category: string
  action: string
  patient_id: string | null
  message: string
  details: string
  outcome_status: string
  severity: string
}

type TimelinessStatus =
  | 'Overdue'
  | 'Urgent'
  | 'Due Soon'
  | 'Returned for Correction'
  | 'Needs Review'
  | 'Missing Data'
  | 'Conflicting Evidence'
  | 'Unable to Evaluate'
  | 'Compliant'
  | 'Approved'
type TimelinessFilter = 'All' | TimelinessStatus

type TimelinessClientSummary = {
  id: number
  patient_id: string
  permitted_name: string
  current_level_of_care: string
  counselor_name: string
  admission_date: string
  last_valid_review_date: string | null
  next_due_date: string | null
  days_until_due: number | null
  status: TimelinessStatus
  rule_used: string
  evidence_summary: string
  evidence_completeness_percent: number
  missing_evidence_fields: string[]
  last_checked_at: string
  last_imported_at: string | null
}

type TimelinessDashboard = {
  total_active_clients: number
  compliant: number
  due_soon: number
  urgent: number
  overdue: number
  returned: number
  needs_review: number
  missing_data: number
  conflicting_evidence: number
  unable_to_evaluate: number
  approved: number
  compliance_percentage: number
  loc_change_window_days: number | null
  loc_change_window_validated: boolean
  items: TimelinessClientSummary[]
}

type TimelinessRuleResult = {
  rule_id: string
  label: string
  due_date: string | null
  status: TimelinessStatus
  evidence_summary: string
}

type TimelinessLevelOfCare = {
  id: number
  level_of_care: string
  facility: string
  effective_date: string
  discharge_date: string
  interval_days: number | null
  is_current: boolean
  source_evidence: string
}

type TimelinessTreatmentPlan = {
  id: number
  plan_kind: string
  document_date: string
  staff_signature_date: string
  client_signature_date: string
  reviewer_signature_date: string
  displayed_next_due_date: string
  source_evidence: string
  source_section: string
  source_document_id: string
  is_valid: boolean
  conflict_note: string
}

type TimelinessOverride = {
  id: number
  field_name: string
  original_value: string
  new_value: string
  reason: string
  affected_rule: string
  created_by_id: number
  created_at: string
}

type TimelinessEvidenceComparison = {
  document_next_due_date: string | null
  signature_anchor_due_date: string | null
  loc_anchor_due_date: string | null
  final_status: TimelinessStatus
  conflict_explanation: string
  source_evidence: string
  staff_signature_date: string | null
  loc_effective_date: string | null
  interval_days: number | null
  loc_change_window_days: number | null
  loc_change_rule_validated: boolean
}

type TimelinessClientDetail = TimelinessClientSummary & {
  is_active: boolean
  source_evidence: string
  evidence_comparison: TimelinessEvidenceComparison
  rule_results: TimelinessRuleResult[]
  level_of_care_history: TimelinessLevelOfCare[]
  treatment_plans: TimelinessTreatmentPlan[]
  overrides: TimelinessOverride[]
  audit_history: AuditLogRecord[]
}

type AppSettings = {
  organization_name: string
  access_intel_enabled: boolean
  access_geo_lookup_url: string
  access_reputation_url: string
  access_reputation_api_key_configured: boolean
  access_lookup_timeout_seconds: number
  llm_enabled: boolean
  llm_provider_name: string
  llm_base_url: string
  llm_model: string
  llm_api_key_configured: boolean
  llm_use_for_access_review: boolean
  llm_use_for_evaluation_gap_analysis: boolean
  llm_analysis_instructions: string
  emr_api_enabled: boolean
  emr_vendor_name: string
  emr_fhir_base_url: string
  emr_smart_client_id: string
  emr_smart_client_secret_configured: boolean
  emr_smart_token_url: string
  emr_smart_scopes: string
  emr_api_timeout_seconds: number
  facility_timezone: string
  effective_timezone: string
  effective_timezone_label: string
  treatment_plan_loc_change_window_days: number | null
  treatment_plan_loc_change_window_validated: boolean
  updated_by_id: number | null
  updated_at: string | null
}

type AppSettingsForm = {
  organization_name: string
  access_intel_enabled: boolean
  access_geo_lookup_url: string
  access_reputation_url: string
  access_reputation_api_key: string
  clear_access_reputation_api_key: boolean
  access_lookup_timeout_seconds: number
  llm_enabled: boolean
  llm_provider_name: string
  llm_base_url: string
  llm_model: string
  llm_api_key: string
  clear_llm_api_key: boolean
  llm_use_for_access_review: boolean
  llm_use_for_evaluation_gap_analysis: boolean
  llm_analysis_instructions: string
  emr_api_enabled: boolean
  emr_vendor_name: string
  emr_fhir_base_url: string
  emr_smart_client_id: string
  emr_smart_client_secret: string
  clear_emr_smart_client_secret: boolean
  emr_smart_token_url: string
  emr_smart_scopes: string
  emr_api_timeout_seconds: number
  facility_timezone: string
  treatment_plan_loc_change_window_days: number | null
  treatment_plan_loc_change_window_validated: boolean
}

type WorkflowDefinitionVersionStatus = 'draft' | 'published' | 'archived'

type WorkflowDefinitionVersion = {
  id: number
  workflow_definition_id: number
  version: number
  status: WorkflowDefinitionVersionStatus
  definition_snapshot: Record<string, unknown>
  transition_rules: Record<string, unknown>[]
  version_notes: string
  created_by_id: number
  published_by_id: number | null
  archived_by_id: number | null
  created_at: string
  published_at: string | null
  archived_at: string | null
}

type WorkflowDefinition = {
  id: number
  workflow_key: string
  display_name: string
  description: string
  category: string
  is_active: boolean
  current_version_id: number | null
  created_by_id: number
  updated_by_id: number | null
  created_at: string
  updated_at: string
  current_version: WorkflowDefinitionVersion | null
  versions: WorkflowDefinitionVersion[]
}

type WorkflowDefinitionForm = {
  workflow_key: string
  display_name: string
  description: string
  category: string
  version_notes: string
  definition_snapshot_text: string
  transition_rules_text: string
}

type WorkflowVersionForm = {
  version_notes: string
  definition_snapshot_text: string
  transition_rules_text: string
}

type UploadEntry = {
  file: File
  document_label: string
  alleva_bucket: AllevaBucket
  document_type: string
  completion_status: DocumentCompletionStatus
  client_signed: boolean
  staff_signed: boolean
  document_date: string
  description: string
  source_document_id: string
  source_document_reference_id: string
  source_attachment_url: string
  source_author: string
  source_custodian: string
  source_security_label: string
  source_provenance_id: string
}

type TransitionAction = {
  toState: WorkflowState
  label: string
  commentLabel: string
  requiresComment?: boolean
}

type ApiError = {
  detail?: string | { msg?: string }
}

type UploadFormState = {
  patient_id: string
  client_name: string
  upload_mode: NoteSetUploadMode
  level_of_care: string
  admission_date: string
  discharge_date: string
  primary_clinician: string
  upload_notes: string
  entries: UploadEntry[]
}

type TimelinessOverrideForm = {
  field_name: string
  original_value: string
  new_value: string
  reason: string
  affected_rule: string
}

type PatientIdDetection = {
  patient_id: string | null
  confidence: string
  source_filename: string | null
  source_kind: string | null
  match_text: string | null
  reason: string
  was_autofilled: boolean
}

type ManagedUserForm = {
  full_name: string
  role: Role
  is_active: boolean
  is_locked: boolean
  must_reset_password: boolean
}

type CreateUserForm = {
  username: string
  full_name: string
  password: string
  role: Role
}

type LogFilters = {
  patient_id: string
  action: string
  event_category: string
}

type UserFilters = {
  query: string
  role: 'all' | Role
}

type ProfileForm = {
  full_name: string
}

type PasswordChangeForm = {
  current_password: string
  new_password: string
}

type EvidencePreviewField = {
  label: string
  value: string
  emphasis?: boolean
}

type EvidencePreview = {
  title: string
  subtitle: string
  fields: EvidencePreviewField[]
  note: string
}

type AppDialog = {
  title: string
  message: string
}

type TrendPoint = {
  label: string
  count: number
}

type RuntimeReadiness = {
  status: 'ok' | 'warn' | 'fail'
  failed: number
  warnings: number
  checks: { name: string; status: string; message: string; detail: string }[]
}

type EmrProfile = {
  adapter_key: string
  live_import_status: string
  supported_export_formats: string[]
  document_manager_sections: { key: string; label: string; source_description: string }[]
  required_vendor_inputs: string[]
}

type EmrDiscovery = {
  status: string
  smart_configuration_url: string
  authorization_endpoint_configured: boolean
  token_endpoint_configured: boolean
  capabilities: string[]
  message: string
}

type EmrImportPlan = {
  patient_id: string
  planned_requests: { step: string; purpose: string; method: string; url: string }[]
  alleva_notes: string[]
  attachment_handling: string
}

type TreatmentPlanChecklistAcronym = {
  term: string
  definition: string
  validation_status: string
}

type TreatmentPlanChecklistStatus = {
  key: string
  label: string
  description: string
}

type TreatmentPlanChecklistStep = {
  step: number
  key: string
  title: string
  source_modes: string[]
  objective: string
  required_metadata: string[]
  required_documents: string[]
  checks: string[]
  finding_examples: string[]
  remediation_suggestions: string[]
  evidence_fields: string[]
  automation_level: string
  severity_default: string
  status_options: string[]
  reviewer_actions: string[]
  manual_override: boolean
  override_reason_required: boolean
  audit_event: string
  export_fields: string[]
}

type TreatmentPlanChecklist = {
  checklist_id: string
  version: string
  display_name: string
  organization: string
  status: string
  last_updated: string
  source_of_truth: string
  review_owner_roles: string[]
  viewer_roles: string[]
  acronyms: TreatmentPlanChecklistAcronym[]
  review_statuses: TreatmentPlanChecklistStatus[]
  loc_change_blocker: { status: string; owner: string; message: string }
  steps: TreatmentPlanChecklistStep[]
}

type ReviewSourceItem = {
  source_type: string
  source_item_id: string
  patient_id: string
  display_name: string
  document_type: string
  source_system_or_file: string
  review_status: string
  status_reason: string
  service_date: string
  plan_date: string
  provider_staff: string
  program_location: string
  last_changed_at: string
  review_chart_id: number | null
  timeliness_client_id: number | null
}

type ReviewSourceDiscovery = {
  checklist_id: string
  checklist_version: string
  last_refreshed_at: string
  last_refresh_at: string
  next_refresh_at: string
  live_import_enabled: boolean
  live_import_status: string
  api_configured: boolean
  api_mode: string
  api_mode_label: string
  daily_monitoring_enabled: boolean
  refresh_mode: string
  last_successful_check_at: string
  last_failure_at: string
  last_check_mode: string
  changed_item_count: number
  error_count: number
  notification_badge_count: number
  manual_review_cadence: string
  manual_mode_message: string
  plain_english_status: string
  status_counts: Record<string, number>
  items: ReviewSourceItem[]
}

// Keep the browser-side upload gate aligned with backend ALLOWED_EXTENSIONS.
const ACCEPTED_UPLOAD_TYPES = '.pdf,.doc,.docx,.txt,.csv,.rtf,.jpg,.jpeg,.png,.zip'
const MAX_UPLOAD_FILE_BYTES = 50 * 1024 * 1024
const MAX_UPLOAD_TOTAL_BYTES = 250 * 1024 * 1024

const STATUS_LABELS: Record<ComplianceStatus, string> = {
  pending: 'Needs manual confirmation',
  yes: 'Confirmed',
  no: 'Missing or incorrect',
  na: 'Not applicable',
}

const NOTE_SET_STATUS_LABELS: Record<NoteSetStatus, string> = {
  active: 'Current binder',
  superseded: 'Superseded',
}

const TIMELINESS_FILTERS: TimelinessFilter[] = [
  'All',
  'Overdue',
  'Urgent',
  'Due Soon',
  'Returned for Correction',
  'Needs Review',
  'Missing Data',
  'Conflicting Evidence',
  'Unable to Evaluate',
  'Compliant',
  'Approved',
]
const TIMELINESS_TASK_STATUSES = new Set<TimelinessStatus>([
  'Overdue',
  'Urgent',
  'Due Soon',
  'Returned for Correction',
  'Needs Review',
  'Missing Data',
  'Conflicting Evidence',
  'Unable to Evaluate',
])

const VIEW_LABELS: Record<AppView, string> = {
  dashboard: 'Chart audit',
  reviews: 'Review queue',
  uploads: 'Manual upload',
  timeliness: 'Treatment plans',
  checklist: 'Checklist',
  profile: 'My account',
  users: 'User management',
  logs: 'Forensic logs',
  settings: 'Settings',
}

const TRANSITIONS: Record<Role, Partial<Record<WorkflowState, TransitionAction[]>>> = {
  admin: {
    'Awaiting Office Manager Review': [
      { toState: 'Approved by Office Manager', label: 'Approve', commentLabel: 'Approval note' },
      { toState: 'Returned to Counselor', label: 'Return to counselor', commentLabel: 'What needs to be fixed', requiresComment: true },
    ],
  },
  manager: {
    'Awaiting Office Manager Review': [
      { toState: 'Approved by Office Manager', label: 'Approve', commentLabel: 'Approval note' },
      { toState: 'Returned to Counselor', label: 'Return to counselor', commentLabel: 'What needs to be fixed', requiresComment: true },
    ],
  },
  counselor: {},
}

function readErrorMessage(status: number, payload: ApiError | null) {
  const detail = payload?.detail
  if (typeof detail === 'string' && detail.trim()) return `HTTP ${status}: ${detail}`
  if (detail && typeof detail === 'object' && typeof detail.msg === 'string') return `HTTP ${status}: ${detail.msg}`
  return `HTTP ${status}: request failed`
}

function groupedChecklist(items: AuditItem[]) {
  const groups = new Map<string, AuditItem[]>()
  items.forEach((item) => {
    const existing = groups.get(item.section) || []
    existing.push(item)
    groups.set(item.section, existing)
  })
  return Array.from(groups.entries())
}

function createUploadForm(overrides?: Partial<Omit<UploadFormState, 'entries'>>) {
  return {
    patient_id: '',
    client_name: '',
    upload_mode: 'initial' as NoteSetUploadMode,
    level_of_care: '',
    admission_date: '',
    discharge_date: '',
    primary_clinician: '',
    upload_notes: '',
    entries: [],
    ...overrides,
  }
}

function viewFromUrl(): AppView {
  if (typeof window === 'undefined') return 'dashboard'
  const requested = new URLSearchParams(window.location.search).get('view') || window.location.hash.replace(/^#\/?/, '')
  return ['dashboard', 'reviews', 'timeliness', 'checklist', 'uploads', 'profile', 'users', 'logs', 'settings'].includes(requested) ? (requested as AppView) : 'dashboard'
}

function createSettingsForm(settings: AppSettings): AppSettingsForm {
  return {
    organization_name: settings.organization_name,
    access_intel_enabled: settings.access_intel_enabled,
    access_geo_lookup_url: settings.access_geo_lookup_url,
    access_reputation_url: settings.access_reputation_url,
    access_reputation_api_key: '',
    clear_access_reputation_api_key: false,
    access_lookup_timeout_seconds: settings.access_lookup_timeout_seconds,
    llm_enabled: settings.llm_enabled,
    llm_provider_name: settings.llm_provider_name,
    llm_base_url: settings.llm_base_url,
    llm_model: settings.llm_model,
    llm_api_key: '',
    clear_llm_api_key: false,
    llm_use_for_access_review: settings.llm_use_for_access_review,
    llm_use_for_evaluation_gap_analysis: settings.llm_use_for_evaluation_gap_analysis,
    llm_analysis_instructions: settings.llm_analysis_instructions,
    emr_api_enabled: settings.emr_api_enabled,
    emr_vendor_name: settings.emr_vendor_name,
    emr_fhir_base_url: settings.emr_fhir_base_url,
    emr_smart_client_id: settings.emr_smart_client_id,
    emr_smart_client_secret: '',
    clear_emr_smart_client_secret: false,
    emr_smart_token_url: settings.emr_smart_token_url || 'https://authorization.allevasoft.com/connect/token',
    emr_smart_scopes: settings.emr_smart_scopes,
    emr_api_timeout_seconds: settings.emr_api_timeout_seconds,
    facility_timezone: settings.facility_timezone || 'local_machine',
    treatment_plan_loc_change_window_days: settings.treatment_plan_loc_change_window_days,
    treatment_plan_loc_change_window_validated: settings.treatment_plan_loc_change_window_validated,
  }
}

function createWorkflowDefinitionForm(): WorkflowDefinitionForm {
  return {
    workflow_key: '',
    display_name: '',
    description: '',
    category: 'clinical_review',
    version_notes: '',
    definition_snapshot_text: JSON.stringify({ steps: [], owner_roles: ['admin', 'manager'] }, null, 2),
    transition_rules_text: JSON.stringify([], null, 2),
  }
}

function createWorkflowVersionForm(definition?: WorkflowDefinition | null): WorkflowVersionForm {
  return {
    version_notes: '',
    definition_snapshot_text: JSON.stringify(definition?.current_version?.definition_snapshot || { steps: [], owner_roles: ['admin', 'manager'] }, null, 2),
    transition_rules_text: JSON.stringify(definition?.current_version?.transition_rules || [], null, 2),
  }
}

function workflowSnapshotFromChecklist(checklist: TreatmentPlanChecklist) {
  return {
    checklist_id: checklist.checklist_id,
    checklist_version: checklist.version,
    display_name: checklist.display_name,
    source_of_truth: checklist.source_of_truth,
    loc_change_blocker: checklist.loc_change_blocker,
    owner_roles: checklist.review_owner_roles,
    viewer_roles: checklist.viewer_roles,
    steps: checklist.steps.map((step) => ({
      key: step.key,
      label: step.title,
      step: step.step,
      source_modes: step.source_modes,
      automation_level: step.automation_level,
      severity_default: step.severity_default,
      status_options: step.status_options,
      reviewer_actions: step.reviewer_actions,
      manual_override: step.manual_override,
      override_reason_required: step.override_reason_required,
      audit_event: step.audit_event,
      export_fields: step.export_fields,
    })),
  }
}

function defaultWorkflowTransitionsFromChecklist() {
  return [
    { from: 'not_reviewed', to: 'ready_for_review', roles: ['admin', 'manager'] },
    { from: 'ready_for_review', to: 'in_review', roles: ['admin', 'manager'] },
    { from: 'in_review', to: 'current_compliant', roles: ['admin', 'manager'] },
    { from: 'in_review', to: 'due_soon', roles: ['admin', 'manager'] },
    { from: 'in_review', to: 'urgent', roles: ['admin', 'manager'] },
    { from: 'in_review', to: 'overdue', roles: ['admin', 'manager'] },
    { from: 'in_review', to: 'needs_review', roles: ['admin', 'manager'] },
    { from: 'in_review', to: 'missing_data', roles: ['admin', 'manager'] },
    { from: 'in_review', to: 'conflicting_evidence', roles: ['admin', 'manager'] },
    { from: 'in_review', to: 'unable_to_evaluate', roles: ['admin', 'manager'] },
    { from: 'in_review', to: 'returned_for_correction', roles: ['admin', 'manager'], reason_required: true },
    { from: 'current_compliant', to: 'approved_finalized', roles: ['admin', 'manager'] },
    { from: 'due_soon', to: 'approved_finalized', roles: ['admin', 'manager'] },
    { from: 'urgent', to: 'approved_finalized', roles: ['admin', 'manager'] },
    { from: 'overdue', to: 'returned_for_correction', roles: ['admin', 'manager'], reason_required: true },
    { from: 'needs_review', to: 'returned_for_correction', roles: ['admin', 'manager'], reason_required: true },
    { from: 'missing_data', to: 'returned_for_correction', roles: ['admin', 'manager'], reason_required: true },
    { from: 'conflicting_evidence', to: 'returned_for_correction', roles: ['admin', 'manager'], reason_required: true },
    { from: 'unable_to_evaluate', to: 'returned_for_correction', roles: ['admin', 'manager'], reason_required: true },
    { from: 'returned_for_correction', to: 'ready_for_review', roles: ['admin', 'manager'] },
    { from: 'approved_finalized', to: 'ready_for_review', roles: ['admin'], reason_required: true },
  ]
}

function parseWorkflowVersionInput(form: WorkflowDefinitionForm | WorkflowVersionForm) {
  const definitionSnapshot = JSON.parse(form.definition_snapshot_text || '{}')
  const transitionRules = JSON.parse(form.transition_rules_text || '[]')
  if (!definitionSnapshot || Array.isArray(definitionSnapshot) || typeof definitionSnapshot !== 'object') {
    throw new Error('Workflow definition JSON must be an object.')
  }
  if (!Array.isArray(transitionRules)) {
    throw new Error('Transition rules JSON must be an array.')
  }
  return {
    definition_snapshot: definitionSnapshot as Record<string, unknown>,
    transition_rules: transitionRules as Record<string, unknown>[],
    version_notes: form.version_notes,
  }
}

function workflowVersionTone(status: WorkflowDefinitionVersionStatus) {
  if (status === 'published') return 'success'
  if (status === 'draft') return 'warning'
  return 'neutral'
}

function createTimelinessOverrideForm(detail?: TimelinessClientDetail | null): TimelinessOverrideForm {
  return {
    field_name: 'status',
    original_value: detail?.status || '',
    new_value: 'Needs Review',
    reason: '',
    affected_rule: detail?.rule_used || '',
  }
}

function buildUploadEntry(file: File): UploadEntry {
  const label = file.name.replace(/\.[^.]+$/, '')
  return {
    file,
    document_label: label || file.name,
    alleva_bucket: 'custom_forms',
    document_type: 'clinical_note',
    completion_status: 'completed',
    client_signed: false,
    staff_signed: false,
    document_date: '',
    description: '',
    source_document_id: '',
    source_document_reference_id: '',
    source_attachment_url: '',
    source_author: '',
    source_custodian: '',
    source_security_label: '',
    source_provenance_id: '',
  }
}

function formatDateTime(value: string | null | undefined) {
  if (!value) return 'Not recorded'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function deviceTimezone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'local_machine'
  } catch {
    return 'local_machine'
  }
}

function formatLogDateTime(log: AuditLogRecord) {
  return log.timestamp_local || formatDateTime(log.timestamp_utc)
}

function parseLogDetails(details: string) {
  try {
    const parsed = JSON.parse(details)
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : {}
  } catch {
    return {}
  }
}

function shortHash(value: string) {
  return value.length > 12 ? `${value.slice(0, 12)}...` : value
}

function csvCell(value: unknown) {
  const raw = value == null ? '' : String(value)
  return `"${raw.replace(/"/g, '""')}"`
}

function downloadTextFile(filename: string, content: string, contentType: string) {
  const blob = new Blob([content], { type: contentType })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function timelinessTaskItems(items: TimelinessClientSummary[]) {
  return items.filter((item) => TIMELINESS_TASK_STATUSES.has(item.status))
}

function buildTimelinessTaskList(items: TimelinessClientSummary[]) {
  const header = ['client_label', 'due_date', 'status', 'current_loc', 'primary_clinician', 'reason']
  const rows = timelinessTaskItems(items).map((item) =>
    [
      item.permitted_name || item.patient_id,
      item.next_due_date || 'Not calculated',
      item.status,
      item.current_level_of_care || 'Missing',
      item.counselor_name || 'Unassigned',
      item.evidence_summary || item.rule_used,
    ]
      .map(csvCell)
      .join(','),
  )
  return [header.map(csvCell).join(','), ...rows].join('\n')
}

function workflowTone(state: string) {
  if (state === 'Approved by Office Manager') return 'success'
  if (state === 'Returned to Counselor') return 'danger'
  return 'neutral'
}

function timelinessTone(status: string) {
  if (status === 'Compliant') return 'success'
  if (status === 'Approved') return 'success'
  if (status === 'Overdue') return 'danger'
  if (status === 'Returned for Correction') return 'danger'
  if (status === 'Needs Review' || status === 'Conflicting Evidence') return 'attention'
  if (status === 'Urgent' || status === 'Due Soon') return 'warning'
  if (status === 'Missing Data' || status === 'Unable to Evaluate') return 'muted'
  return 'neutral'
}

function timelinessFilterCount(dashboard: TimelinessDashboard | null, filter: TimelinessFilter) {
  if (!dashboard) return 0
  if (filter === 'All') return dashboard.items.length
  return dashboard.items.filter((item) => item.status === filter).length
}

function planKindLabel(kind: string) {
  if (kind === 'initial') return 'Initial'
  if (kind === 'master') return 'Master'
  if (kind === 'review') return 'Review'
  if (kind === 'loc_update') return 'LOC update'
  return kind || 'Plan'
}

function planKindTone(kind: string) {
  if (kind === 'initial') return 'success'
  if (kind === 'master') return 'neutral'
  if (kind === 'review') return 'attention'
  if (kind === 'loc_update') return 'warning'
  return 'muted'
}

function displayDate(value: string | null | undefined) {
  return value || 'Not recorded'
}

function signedLabel(value: string) {
  return value ? value : 'Missing'
}

function checklistTone(status: ComplianceStatus) {
  if (status === 'yes') return 'success'
  if (status === 'no') return 'danger'
  if (status === 'na') return 'muted'
  return 'warning'
}

function copyChartDetail(detail: ChartDetail): ChartDetail {
  return {
    ...detail,
    checklist_items: detail.checklist_items.map((item) => ({ ...item })),
  }
}

function toChartUpdatePayload(detail: ChartDetail) {
  return {
    patient_id: detail.patient_id,
    client_name: detail.client_name,
    level_of_care: detail.level_of_care,
    admission_date: detail.admission_date,
    discharge_date: detail.discharge_date,
    primary_clinician: detail.primary_clinician,
    auditor_name: detail.auditor_name,
    other_details: detail.other_details,
    notes: detail.notes,
    checklist_items: detail.checklist_items.map((item) => ({
      item_key: item.item_key,
      status: item.status,
      notes: item.notes,
      evidence_location: item.evidence_location,
      evidence_date: item.evidence_date,
      expiration_date: item.expiration_date,
    })),
  }
}

function isBootstrapAdmin(user: User | null) {
  return user?.username === 'admin'
}

function userStatusLabel(candidate: Pick<User, 'is_active' | 'is_locked'>) {
  if (!candidate.is_active) return 'Inactive'
  if (candidate.is_locked) return 'Locked'
  return 'Active'
}

function userStatusTone(candidate: Pick<User, 'is_active' | 'is_locked'>) {
  if (!candidate.is_active || candidate.is_locked) return 'danger'
  return 'success'
}

function validateCreateUserForm(form: CreateUserForm) {
  if (!form.username.trim()) return 'Username is required.'
  if (form.password.trim().length < 12) return 'Temporary password must be at least 12 characters.'
  return ''
}

function validateUploadFiles(files: File[]) {
  // Validate locally first so non-technical users get immediate, plain feedback.
  const allowed = new Set(ACCEPTED_UPLOAD_TYPES.split(','))
  let totalBytes = 0
  for (const file of files) {
    const suffix = file.name.includes('.') ? `.${file.name.split('.').pop()?.toLowerCase()}` : ''
    if (!allowed.has(suffix)) return `${file.name} is not an accepted clinical-note file type.`
    if (file.size > MAX_UPLOAD_FILE_BYTES) return `${file.name} is larger than the 50 MB file limit.`
    totalBytes += file.size
  }
  if (totalBytes > MAX_UPLOAD_TOTAL_BYTES) return 'The selected binder is larger than the 250 MB total upload limit.'
  return ''
}

function buildTrend(points: (string | null | undefined)[], lookbackDays = 7): TrendPoint[] {
  const now = new Date()
  const dayKeys: string[] = []
  const counts = new Map<string, number>()

  for (let offset = lookbackDays - 1; offset >= 0; offset -= 1) {
    const day = new Date(now)
    day.setHours(0, 0, 0, 0)
    day.setDate(now.getDate() - offset)
    const key = day.toISOString().slice(0, 10)
    dayKeys.push(key)
    counts.set(key, 0)
  }

  points.forEach((raw) => {
    if (!raw) return
    const day = new Date(raw)
    if (Number.isNaN(day.getTime())) return
    const key = day.toISOString().slice(0, 10)
    if (!counts.has(key)) return
    counts.set(key, (counts.get(key) || 0) + 1)
  })

  return dayKeys.map((key) => {
    const day = new Date(`${key}T00:00:00`)
    return {
      label: day.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
      count: counts.get(key) || 0,
    }
  })
}

async function readJson(response: Response) {
  const text = await response.text()
  if (!text) return null
  return JSON.parse(text)
}

export function App() {
  const [token, setToken] = useState('')
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState('Sign in to upload notes, review findings, and manage approvals.')
  const [error, setError] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [mustResetPassword, setMustResetPassword] = useState(false)
  const [activeView, setActiveView] = useState<AppView>(viewFromUrl)
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null)

  const [loginForm, setLoginForm] = useState({ username: '', password: '' })
  const [resetForm, setResetForm] = useState({ newPassword: '' })
  const [decisionComment, setDecisionComment] = useState('')
  const [reviewDirty, setReviewDirty] = useState(false)
  const [selectedFindingKey, setSelectedFindingKey] = useState('')

  const [charts, setCharts] = useState<ChartSummary[]>([])
  const [selectedChartId, setSelectedChartId] = useState<number | null>(null)
  const [selectedChart, setSelectedChart] = useState<ChartDetail | null>(null)

  const [noteSets, setNoteSets] = useState<PatientNoteSetSummary[]>([])
  const [selectedNoteSetId, setSelectedNoteSetId] = useState<number | null>(null)
  const [selectedNoteSet, setSelectedNoteSet] = useState<PatientNoteSetDetail | null>(null)
  const [timelinessDashboard, setTimelinessDashboard] = useState<TimelinessDashboard | null>(null)
  const [selectedTimelinessClientId, setSelectedTimelinessClientId] = useState<number | null>(null)
  const [selectedTimelinessClient, setSelectedTimelinessClient] = useState<TimelinessClientDetail | null>(null)
  const [timelinessEvaluationDate, setTimelinessEvaluationDate] = useState('')
  const [timelinessStatusFilter, setTimelinessStatusFilter] = useState<TimelinessFilter>('All')
  const [timelinessSearch, setTimelinessSearch] = useState('')
  const [timelinessOverrideForm, setTimelinessOverrideForm] = useState<TimelinessOverrideForm>(createTimelinessOverrideForm())
  const [evidencePreview, setEvidencePreview] = useState<EvidencePreview | null>(null)
  const [appDialog, setAppDialog] = useState<AppDialog | null>(null)
  const [uploadForm, setUploadForm] = useState<UploadFormState>(createUploadForm())
  const [patientIdDetection, setPatientIdDetection] = useState<PatientIdDetection | null>(null)
  const [patientIdTouched, setPatientIdTouched] = useState(false)
  const [lastAutoFilledPatientId, setLastAutoFilledPatientId] = useState('')
  const uploadPatientIdRef = useRef('')
  const patientIdTouchedRef = useRef(false)
  const lastAutoFilledPatientIdRef = useRef('')
  const criterionWorkbenchRef = useRef<HTMLDivElement | null>(null)

  const [users, setUsers] = useState<User[]>([])
  const [selectedManagedUserId, setSelectedManagedUserId] = useState<number | null>(null)
  const [managedUserForm, setManagedUserForm] = useState<ManagedUserForm | null>(null)
  const [newUserForm, setNewUserForm] = useState<CreateUserForm>({
    username: '',
    full_name: '',
    password: '',
    role: 'counselor',
  })
  const [adminPasswordReset, setAdminPasswordReset] = useState('')
  const [deleteUserConfirmation, setDeleteUserConfirmation] = useState('')
  const [userFilters, setUserFilters] = useState<UserFilters>({ query: '', role: 'all' })

  const [logs, setLogs] = useState<AuditLogRecord[]>([])
  const [logFilters, setLogFilters] = useState<LogFilters>({ patient_id: '', action: '', event_category: '' })
  const [appSettings, setAppSettings] = useState<AppSettings | null>(null)
  const [settingsForm, setSettingsForm] = useState<AppSettingsForm | null>(null)
  const [readiness, setReadiness] = useState<RuntimeReadiness | null>(null)
  const [emrProfile, setEmrProfile] = useState<EmrProfile | null>(null)
  const [emrDiscovery, setEmrDiscovery] = useState<EmrDiscovery | null>(null)
  const [emrPlanPatientId, setEmrPlanPatientId] = useState('')
  const [emrImportPlan, setEmrImportPlan] = useState<EmrImportPlan | null>(null)
  const [treatmentPlanChecklist, setTreatmentPlanChecklist] = useState<TreatmentPlanChecklist | null>(null)
  const [reviewSourceDiscovery, setReviewSourceDiscovery] = useState<ReviewSourceDiscovery | null>(null)
  const [workflowDefinitions, setWorkflowDefinitions] = useState<WorkflowDefinition[]>([])
  const [selectedWorkflowDefinitionId, setSelectedWorkflowDefinitionId] = useState<number | null>(null)
  const [workflowDefinitionForm, setWorkflowDefinitionForm] = useState<WorkflowDefinitionForm>(createWorkflowDefinitionForm())
  const [workflowVersionForm, setWorkflowVersionForm] = useState<WorkflowVersionForm>(createWorkflowVersionForm())

  const [profileForm, setProfileForm] = useState<ProfileForm>({ full_name: '' })
  const [passwordChangeForm, setPasswordChangeForm] = useState<PasswordChangeForm>({ current_password: '', new_password: '' })

  const groupedFindings = useMemo(() => groupedChecklist(selectedChart?.checklist_items || []), [selectedChart])
  const openItems = useMemo(
    () => (selectedChart?.checklist_items || []).filter((item) => item.status === 'no' || item.status === 'pending'),
    [selectedChart],
  )
  const pendingManagerQueue = useMemo(
    () => charts.filter((chart) => chart.state === 'Awaiting Office Manager Review'),
    [charts],
  )
  const transitionActions = useMemo(() => {
    if (!user || !selectedChart) return []
    return TRANSITIONS[user.role]?.[selectedChart.state] || []
  }, [selectedChart, user])
  const canEditCriteria = user?.role === 'admin' || user?.role === 'manager'
  const canOverrideTimeliness = user?.role === 'admin' || user?.role === 'manager'

  const selectedManagedUser = useMemo(
    () => users.find((candidate) => candidate.id === selectedManagedUserId) || null,
    [users, selectedManagedUserId],
  )
  const selectedWorkflowDefinition = useMemo(
    () => workflowDefinitions.find((definition) => definition.id === selectedWorkflowDefinitionId) || workflowDefinitions[0] || null,
    [selectedWorkflowDefinitionId, workflowDefinitions],
  )
  const selectedWorkflowDefinitionCanDelete = Boolean(
    selectedWorkflowDefinition &&
      selectedWorkflowDefinition.current_version_id == null &&
      selectedWorkflowDefinition.versions.every((version) => version.status === 'draft'),
  )
  const selectedManagedUserIsBootstrap = isBootstrapAdmin(selectedManagedUser)
  const selectedManagedUserIsCurrentUser = selectedManagedUser?.id === user?.id
  const selectedManagedUserCanDelete = Boolean(selectedManagedUser && !selectedManagedUserIsBootstrap && !selectedManagedUserIsCurrentUser)

  const filteredUsers = useMemo(() => {
    const query = userFilters.query.trim().toLowerCase()
    return users.filter((candidate) => {
      const matchesRole = userFilters.role === 'all' || candidate.role === userFilters.role
      const matchesQuery =
        !query ||
        candidate.username.toLowerCase().includes(query) ||
        candidate.full_name.toLowerCase().includes(query)
      return matchesRole && matchesQuery
    })
  }, [userFilters, users])

  const accessAttemptLogs = useMemo(() => logs.filter((entry) => entry.event_category === 'access_attempt'), [logs])

  const filteredTimelinessItems = useMemo(() => {
    const query = timelinessSearch.trim().toLowerCase()
    const items = timelinessDashboard?.items || []
    return items.filter((item) => {
      const matchesStatus = timelinessStatusFilter === 'All' || item.status === timelinessStatusFilter
      const matchesQuery =
        !query ||
        item.patient_id.toLowerCase().includes(query) ||
        item.permitted_name.toLowerCase().includes(query) ||
        item.current_level_of_care.toLowerCase().includes(query) ||
        item.counselor_name.toLowerCase().includes(query)
      return matchesStatus && matchesQuery
    })
  }, [timelinessDashboard, timelinessSearch, timelinessStatusFilter])

  const exportableTimelinessTaskCount = useMemo(
    () => timelinessTaskItems(timelinessDashboard?.items || []).length,
    [timelinessDashboard],
  )

  const versionLabel = versionInfo
    ? `v${versionInfo.version}${versionInfo.environment ? ` · ${versionInfo.environment}` : ''}${versionInfo.git_commit && versionInfo.git_commit !== 'unknown' ? ` · ${versionInfo.git_commit}` : ''}`
    : 'Version unavailable'
  const timelinessBuildLabel = versionInfo?.version ? `v${versionInfo.version}` : 'current build'

  useEffect(() => {
    if (typeof window === 'undefined') return
    const current = new URL(window.location.href)
    current.searchParams.set('view', activeView)
    window.history.replaceState(null, '', `${current.pathname}?${current.searchParams.toString()}`)
  }, [activeView])

  useEffect(() => {
    if (error) {
      setAppDialog({ title: 'Action could not be completed', message: error })
    }
  }, [error])

  useEffect(() => {
    let isMounted = true
    fetch(`${API}/version`, { headers: { Accept: 'application/json' } })
      .then((response) => (response.ok ? readJson(response) : null))
      .then((payload) => {
        if (isMounted && payload) setVersionInfo(payload as VersionInfo)
      })
      .catch(() => {
        if (isMounted) setVersionInfo(null)
      })
    return () => {
      isMounted = false
    }
  }, [])

  const selectedCriterion = useMemo(() => {
    if (!selectedChart) return null
    return selectedChart.checklist_items.find((item) => item.item_key === selectedFindingKey) || selectedChart.checklist_items[0] || null
  }, [selectedChart, selectedFindingKey])

  const totalOpen = useMemo(
    () => charts.filter((chart) => chart.state !== 'Approved by Office Manager').length,
    [charts],
  )
  const totalAwaiting = pendingManagerQueue.length
  const totalWaitingReverification = useMemo(
    () => charts.filter((chart) => chart.state === 'Returned to Counselor').length,
    [charts],
  )
  const totalApproved = useMemo(
    () => charts.filter((chart) => chart.state === 'Approved by Office Manager').length,
    [charts],
  )
  const activeBinders = useMemo(() => noteSets.filter((noteSet) => noteSet.status === 'active').length, [noteSets])
  const reviewSourceApiItems = useMemo(
    () => reviewSourceDiscovery?.items.filter((item) => item.source_type === 'api').length ?? 0,
    [reviewSourceDiscovery],
  )
  const reviewSourceUploadItems = useMemo(
    () => reviewSourceDiscovery?.items.filter((item) => item.source_type === 'upload').length ?? 0,
    [reviewSourceDiscovery],
  )
  const activeUserCount = useMemo(() => users.filter((entry) => entry.is_active).length, [users])
  const lockedUserCount = useMemo(() => users.filter((entry) => entry.is_locked).length, [users])
  const resetRequiredCount = useMemo(() => users.filter((entry) => entry.must_reset_password).length, [users])
  const activeWorkflowDefinitionCount = useMemo(() => workflowDefinitions.filter((definition) => definition.is_active).length, [workflowDefinitions])
  const draftWorkflowVersionCount = useMemo(
    () => workflowDefinitions.reduce((total, definition) => total + definition.versions.filter((version) => version.status === 'draft').length, 0),
    [workflowDefinitions],
  )

  const newEvaluationTrend = useMemo(
    () => buildTrend(charts.map((chart) => chart.system_generated_at || chart.created_at)),
    [charts],
  )
  const approvalTrend = useMemo(
    () => buildTrend(charts.filter((chart) => chart.state === 'Approved by Office Manager').map((chart) => chart.reviewed_at)),
    [charts],
  )
  const reverificationTrend = useMemo(
    () => buildTrend(charts.filter((chart) => chart.state === 'Returned to Counselor').map((chart) => chart.reviewed_at)),
    [charts],
  )
  const uploadTrend = useMemo(
    () => buildTrend(noteSets.map((noteSet) => noteSet.created_at)),
    [noteSets],
  )

  const linkedNoteSet =
    selectedChart?.source_note_set_id != null ? noteSets.find((noteSet) => noteSet.id === selectedChart.source_note_set_id) || null : null

  async function apiRequest<T>(path: string, init?: RequestInit, includeAuth = true): Promise<T> {
    const headers = new Headers(init?.headers)
    if (includeAuth && token) headers.set('Authorization', `Bearer ${token}`)
    const response = await fetch(`${API}${path}`, { ...init, headers })
    const payload = (await readJson(response)) as ApiError | T | null
    if (!response.ok) {
      throw new Error(readErrorMessage(response.status, payload as ApiError | null))
    }
    return payload as T
  }

  function safeButtonLabel(value: string) {
    return value
      .replace(/\s+/g, ' ')
      .replace(/\b(PAT|SYNTH|MRN|CLIENT|ID)[-_:A-Z0-9]{2,}\b/gi, '[id]')
      .trim()
      .slice(0, 120)
  }

  function recordButtonAction(screen: string, actionName: string, result = 'clicked', context: Record<string, string | boolean | number> = {}) {
    if (!token || !actionName.trim()) return
    const headers = new Headers({ 'Content-Type': 'application/json', Authorization: `Bearer ${token}` })
    void fetch(`${API}/ui-events`, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        screen,
        action_name: safeButtonLabel(actionName),
        result,
        context: {
          ...context,
          button_text: safeButtonLabel(String(context.button_text || actionName)),
          view: screen,
        },
      }),
    }).catch(() => undefined)
  }

  function handleButtonAuditCapture(event: MouseEvent<HTMLElement>) {
    const target = event.target as HTMLElement | null
    const button = target?.closest('button') as HTMLButtonElement | null
    if (!button || button.dataset.auditSkip === 'true') return
    const label = button.dataset.auditLabel || button.getAttribute('aria-label') || button.textContent || 'Button'
    recordButtonAction(activeView, label, button.disabled ? 'blocked' : 'clicked', {
      button_type: button.type || 'button',
      disabled: button.disabled,
    })
  }

  function syncSelectedManagedUser(nextUsers: User[], preferredId?: number | null) {
    const selectedId = preferredId ?? selectedManagedUserId ?? nextUsers[0]?.id ?? null
    setSelectedManagedUserId(selectedId)
    const selected = nextUsers.find((candidate) => candidate.id === selectedId) || null
    setManagedUserForm(
      selected
        ? {
            full_name: selected.full_name,
            role: selected.role,
            is_active: selected.is_active,
            is_locked: selected.is_locked,
            must_reset_password: selected.must_reset_password,
          }
        : null,
    )
    setDeleteUserConfirmation('')
  }

  function syncWorkflowDefinitions(nextDefinitions: WorkflowDefinition[], preferredId?: number | null) {
    setWorkflowDefinitions(nextDefinitions)
    const selectedId = preferredId ?? selectedWorkflowDefinitionId ?? nextDefinitions[0]?.id ?? null
    const selected = nextDefinitions.find((definition) => definition.id === selectedId) || nextDefinitions[0] || null
    setSelectedWorkflowDefinitionId(selected?.id ?? null)
    setWorkflowVersionForm(createWorkflowVersionForm(selected))
  }

  async function loadWorkflowDefinitions(preferredId?: number | null) {
    if (user?.role !== 'admin') return
    const payload = await apiRequest<WorkflowDefinition[]>('/workflow-definitions?include_archived=true')
    syncWorkflowDefinitions(payload, preferredId)
  }

  async function loadTreatmentPlanChecklist() {
    const payload = await apiRequest<TreatmentPlanChecklist>('/treatment-plan-checklist')
    setTreatmentPlanChecklist(payload)
  }

  async function loadReviewSourceDiscovery() {
    const payload = await apiRequest<ReviewSourceDiscovery>('/review-source-discovery')
    setReviewSourceDiscovery(payload)
  }

  async function runDailyReviewSourceCheck() {
    setIsBusy(true)
    setError('')
    setStatus('Running the safe daily review-source check...')
    try {
      const payload = await apiRequest<ReviewSourceDiscovery>('/review-source-discovery/run-daily-check', { method: 'POST' })
      setReviewSourceDiscovery(payload)
      setStatus(`Daily review-source check completed in ${payload.last_check_mode || payload.refresh_mode}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to run daily review-source check')
    } finally {
      setIsBusy(false)
    }
  }

  async function loadChartDetail(chartId: number) {
    if (reviewDirty && selectedChartId !== chartId && !window.confirm('Discard unsaved criterion review changes?')) return
    const detail = copyChartDetail(await apiRequest<ChartDetail>(`/charts/${chartId}`))
    setSelectedChart(detail)
    setSelectedChartId(detail.id)
    setSelectedFindingKey((current) => {
      if (current && detail.checklist_items.some((item) => item.item_key === current)) return current
      return detail.checklist_items[0]?.item_key || ''
    })
    setReviewDirty(false)

    if (detail.source_note_set_id) {
      setSelectedNoteSetId(detail.source_note_set_id)
      try {
        const noteSetDetail = await apiRequest<PatientNoteSetDetail>(`/patient-note-sets/${detail.source_note_set_id}`)
        setSelectedNoteSet(noteSetDetail)
      } catch {
        setSelectedNoteSet(null)
      }
    }
  }

  async function loadNoteSetDetail(noteSetId: number) {
    const detail = await apiRequest<PatientNoteSetDetail>(`/patient-note-sets/${noteSetId}`)
    setSelectedNoteSet(detail)
    setSelectedNoteSetId(detail.id)
  }

  function timelinessQueryString() {
    const params = new URLSearchParams()
    if (timelinessEvaluationDate.trim()) params.set('evaluation_date', timelinessEvaluationDate.trim())
    const query = params.toString()
    return query ? `?${query}` : ''
  }

  async function loadTimelinessClientDetail(clientId: number) {
    const detail = await apiRequest<TimelinessClientDetail>(`/timeliness/clients/${clientId}${timelinessQueryString()}`)
    setSelectedTimelinessClient(detail)
    setSelectedTimelinessClientId(detail.id)
    setTimelinessOverrideForm(createTimelinessOverrideForm(detail))
  }

  async function loadTimelinessDashboard(preferredId?: number | null) {
    const payload = await apiRequest<TimelinessDashboard>(`/timeliness/dashboard${timelinessQueryString()}`)
    setTimelinessDashboard(payload)
    const preferred = preferredId ?? selectedTimelinessClientId
    const nextId = preferred && payload.items.some((item) => item.id === preferred) ? preferred : payload.items[0]?.id ?? null
    if (nextId) {
      await loadTimelinessClientDetail(nextId)
    } else {
      setSelectedTimelinessClient(null)
      setSelectedTimelinessClientId(null)
      setTimelinessOverrideForm(createTimelinessOverrideForm())
    }
  }

  async function loadUsers(preferredId?: number | null) {
    if (user?.role !== 'admin') return
    const nextUsers = await apiRequest<User[]>('/users')
    setUsers(nextUsers)
    syncSelectedManagedUser(nextUsers, preferredId)
  }

  async function loadSettings() {
    if (user?.role !== 'admin') return
    const [payload, profile, definitions] = await Promise.all([
      apiRequest<AppSettings>('/settings'),
      apiRequest<EmrProfile>('/emr/profile'),
      apiRequest<WorkflowDefinition[]>('/workflow-definitions?include_archived=true'),
    ])
    setAppSettings(payload)
    setSettingsForm(createSettingsForm(payload))
    setEmrProfile(profile)
    syncWorkflowDefinitions(definitions)
  }

  async function loadReadiness() {
    if (user?.role !== 'admin') return
    const payload = await apiRequest<RuntimeReadiness>('/system/readiness')
    setReadiness(payload)
  }

  async function loadLogs() {
    if (user?.role !== 'admin') return
    const params = new URLSearchParams()
    params.set('limit', '200')
    if (logFilters.patient_id.trim()) params.set('patient_id', logFilters.patient_id.trim())
    if (logFilters.action.trim()) params.set('action', logFilters.action.trim())
    if (logFilters.event_category.trim()) params.set('event_category', logFilters.event_category.trim())
    const payload = await apiRequest<AuditLogRecord[]>(`/audit/logs?${params.toString()}`)
    setLogs(payload)
  }

  async function loadWorkspace() {
    if (!token) return
    setIsBusy(true)
    setError('')
    try {
      const [profile, chartList, noteSetList, sourceDiscovery] = await Promise.all([
        apiRequest<User>('/users/me'),
        apiRequest<ChartSummary[]>('/charts'),
        apiRequest<PatientNoteSetSummary[]>('/patient-note-sets'),
        apiRequest<ReviewSourceDiscovery>('/review-source-discovery'),
      ])

      setUser(profile)
      setProfileForm({ full_name: profile.full_name })
      setCharts(chartList)
      setNoteSets(noteSetList)
      setReviewSourceDiscovery(sourceDiscovery)

      if (profile.role === 'admin') {
        const [directory, configuredSettings, runtimeReadiness, configuredEmrProfile, definitions] = await Promise.all([
          apiRequest<User[]>('/users'),
          apiRequest<AppSettings>('/settings'),
          apiRequest<RuntimeReadiness>('/system/readiness'),
          apiRequest<EmrProfile>('/emr/profile'),
          apiRequest<WorkflowDefinition[]>('/workflow-definitions?include_archived=true'),
        ])
        setUsers(directory)
        syncSelectedManagedUser(directory, selectedManagedUserId)
        setAppSettings(configuredSettings)
        setSettingsForm(createSettingsForm(configuredSettings))
        setReadiness(runtimeReadiness)
        setEmrProfile(configuredEmrProfile)
        syncWorkflowDefinitions(definitions, selectedWorkflowDefinitionId)
      } else {
        setUsers([])
        setSelectedManagedUserId(null)
        setManagedUserForm(null)
        setAppSettings(null)
        setSettingsForm(null)
        setReadiness(null)
        setEmrProfile(null)
        setEmrDiscovery(null)
        setEmrImportPlan(null)
        syncWorkflowDefinitions([])
        setDeleteUserConfirmation('')
      }

      const firstChartId = selectedChartId && chartList.some((chart) => chart.id === selectedChartId) ? selectedChartId : chartList[0]?.id ?? null
      const firstNoteSetId =
        selectedNoteSetId && noteSetList.some((noteSet) => noteSet.id === selectedNoteSetId) ? selectedNoteSetId : noteSetList[0]?.id ?? null

      if (firstChartId) {
        await loadChartDetail(firstChartId)
      } else {
        setSelectedChart(null)
        setSelectedChartId(null)
        setSelectedFindingKey('')
      }

      if (!firstChartId && firstNoteSetId) {
        await loadNoteSetDetail(firstNoteSetId)
      } else if (!firstNoteSetId) {
        setSelectedNoteSet(null)
        setSelectedNoteSetId(null)
      }

      setUploadForm((current) =>
        createUploadForm({
          patient_id: current.patient_id,
          client_name: current.client_name,
          upload_mode: current.upload_mode,
          level_of_care: current.level_of_care,
          admission_date: current.admission_date,
          discharge_date: current.discharge_date,
          primary_clinician: current.primary_clinician,
          upload_notes: current.upload_notes,
        }),
      )
      setPatientIdDetection(null)
      setPatientIdTouched(false)
      setLastAutoFilledPatientId('')

      setStatus(`Workspace ready for ${profile.full_name || profile.username}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to load workspace')
    } finally {
      setIsBusy(false)
    }
  }

  useEffect(() => {
    if (!token || mustResetPassword) return
    void loadWorkspace()
  }, [token, mustResetPassword])

  useEffect(() => {
    if (activeView === 'logs' && token && user?.role === 'admin' && !mustResetPassword) {
      void loadLogs()
    }
  }, [activeView, token, user, mustResetPassword])

  useEffect(() => {
    if (activeView === 'settings' && token && user?.role === 'admin' && !mustResetPassword) {
      void loadSettings()
    }
  }, [activeView, token, user, mustResetPassword])

  useEffect(() => {
    if (activeView === 'timeliness' && token && user && !mustResetPassword) {
      void loadTimelinessDashboard()
    }
  }, [activeView, token, user, mustResetPassword])

  useEffect(() => {
    if (activeView === 'checklist' && token && user && !mustResetPassword && !treatmentPlanChecklist) {
      void loadTreatmentPlanChecklist().catch((caught) => setError(caught instanceof Error ? caught.message : 'Failed to load Treatment Plan Checklist'))
    }
  }, [activeView, token, user, mustResetPassword, treatmentPlanChecklist])

  useEffect(() => {
    uploadPatientIdRef.current = uploadForm.patient_id
  }, [uploadForm.patient_id])

  useEffect(() => {
    patientIdTouchedRef.current = patientIdTouched
  }, [patientIdTouched])

  useEffect(() => {
    lastAutoFilledPatientIdRef.current = lastAutoFilledPatientId
  }, [lastAutoFilledPatientId])

  async function detectPatientId(entries: UploadEntry[]) {
    try {
      const body = new FormData()
      entries.forEach((entry) => body.append('files', entry.file))
      const detected = await apiRequest<Omit<PatientIdDetection, 'was_autofilled'>>('/patient-note-sets/detect-patient-id', {
        method: 'POST',
        body,
      })

      const shouldApply =
        Boolean(detected.patient_id) &&
        (!uploadPatientIdRef.current.trim() ||
          !patientIdTouchedRef.current ||
          uploadPatientIdRef.current.trim() === lastAutoFilledPatientIdRef.current)

      if (shouldApply && detected.patient_id) {
        setUploadForm((current) => ({ ...current, patient_id: detected.patient_id || current.patient_id }))
        setLastAutoFilledPatientId(detected.patient_id)
      }

      setPatientIdDetection({ ...detected, was_autofilled: shouldApply })
    } catch {
      setPatientIdDetection({
        patient_id: null,
        confidence: 'none',
        source_filename: null,
        source_kind: null,
        match_text: null,
        reason: 'Automatic patient ID detection was unavailable. Enter the patient ID manually.',
        was_autofilled: false,
      })
    }
  }

  function handleFilesSelected(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || [])
    const validationError = validateUploadFiles(files)
    if (validationError) {
      setError(validationError)
      event.target.value = ''
      setUploadForm((current) => ({ ...current, entries: [] }))
      setPatientIdDetection(null)
      return
    }
    setError('')
    const entries = files.map((file) => buildUploadEntry(file))
    setUploadForm((current) => ({
      ...current,
      entries,
    }))
    if (!entries.length) {
      setPatientIdDetection(null)
      return
    }
    void detectPatientId(entries)
  }

  function updateUploadEntry(index: number, field: keyof UploadEntry, value: string | boolean) {
    setUploadForm((current) => ({
      ...current,
      entries: current.entries.map((entry, entryIndex) => {
        if (entryIndex !== index) return entry
        return { ...entry, [field]: value }
      }),
    }))
  }

  function updateSelectedCriterion(patch: Partial<AuditItem>) {
    if (!selectedChart || !selectedCriterion) return
    setSelectedChart((current) => {
      if (!current) return current
      return {
        ...current,
        checklist_items: current.checklist_items.map((item) => (item.item_key === selectedCriterion.item_key ? { ...item, ...patch } : item)),
      }
    })
    setReviewDirty(true)
  }

  function focusCriterionWorkbench() {
    window.setTimeout(() => {
      criterionWorkbenchRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      criterionWorkbenchRef.current?.focus({ preventScroll: true })
    }, 0)
  }

  function handleDigDeeper(item: AuditItem) {
    setSelectedFindingKey(item.item_key)
    setStatus(`Opened evidence details for Step ${item.step}.`)
    focusCriterionWorkbench()
  }

  function handleCriterionStatusChange(status: ComplianceStatus) {
    if (!canEditCriteria) {
      setAppDialog({
        title: 'Review result is read-only',
        message: 'Only admins and office managers can change criterion results. You can still review the evidence details on this screen.',
      })
      setStatus('Criterion result was not changed because your role has read-only access.')
      recordButtonAction(activeView, `Criterion ${status}`, 'blocked', { blocked_reason: 'role' })
      return
    }
    updateSelectedCriterion({ status })
  }

  async function handleLogin(event: FormEvent) {
    event.preventDefault()
    setIsBusy(true)
    setError('')
    setStatus(`Signing in as ${loginForm.username}...`)
    try {
      const login = await apiRequest<{ access_token: string; must_reset_password: boolean }>(
        '/auth/login',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(loginForm),
        },
        false,
      )
      setToken(login.access_token)
      setMustResetPassword(login.must_reset_password)
      const profile = await apiRequest<User>('/users/me', { headers: { Authorization: `Bearer ${login.access_token}` } }, false)
      setUser(profile)
      setProfileForm({ full_name: profile.full_name })
      if (login.must_reset_password) {
        setStatus('Password reset required before continuing.')
      } else {
        setStatus(`Signed in as ${profile.full_name || profile.username}. Loading workspace...`)
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Login failed')
    } finally {
      setIsBusy(false)
    }
  }

  async function handlePasswordReset(event: FormEvent) {
    event.preventDefault()
    setIsBusy(true)
    setError('')
    try {
      await apiRequest('/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: resetForm.newPassword }),
      })
      setMustResetPassword(false)
      setResetForm({ newPassword: '' })
      setStatus('Password reset complete. Loading workspace...')
      await loadWorkspace()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Password reset failed')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleUpload(event: FormEvent) {
    event.preventDefault()
    if (!uploadForm.entries.length) {
      setError('Add at least one clinical note file before uploading.')
      return
    }

    setIsBusy(true)
    setError('')
    setStatus(`Uploading clinical notes for patient ${uploadForm.patient_id || 'pending'}...`)

    try {
      const body = new FormData()
      body.set('patient_id', uploadForm.patient_id)
      body.set('client_name', uploadForm.client_name)
      body.set('upload_mode', uploadForm.upload_mode)
      body.set('level_of_care', uploadForm.level_of_care)
      body.set('admission_date', uploadForm.admission_date)
      body.set('discharge_date', uploadForm.discharge_date)
      body.set('primary_clinician', uploadForm.primary_clinician)
      body.set('upload_notes', uploadForm.upload_notes)
      body.set(
        'file_manifest',
        JSON.stringify(
          uploadForm.entries.map((entry) => ({
            client_file_name: entry.file.name,
            document_label: entry.document_label,
            alleva_bucket: entry.alleva_bucket,
            document_type: entry.document_type,
            completion_status: entry.completion_status,
            client_signed: entry.client_signed,
            staff_signed: entry.staff_signed,
            document_date: entry.document_date,
            description: entry.description,
            source_document_id: entry.source_document_id,
            source_document_reference_id: entry.source_document_reference_id,
            source_attachment_url: entry.source_attachment_url,
            source_author: entry.source_author,
            source_custodian: entry.source_custodian,
            source_security_label: entry.source_security_label,
            source_provenance_id: entry.source_provenance_id,
          })),
        ),
      )
      uploadForm.entries.forEach((entry) => body.append('files', entry.file))

      const uploaded = await apiRequest<PatientNoteSetDetail>('/patient-note-sets', {
        method: 'POST',
        body,
      })

      setUploadForm(
        createUploadForm({
          patient_id: uploaded.patient_id,
          client_name: uploadForm.client_name,
          upload_mode: 'update',
          level_of_care: uploaded.level_of_care,
          admission_date: uploaded.admission_date,
          discharge_date: uploaded.discharge_date,
          primary_clinician: uploaded.primary_clinician,
          upload_notes: '',
        }),
      )
      setPatientIdDetection(null)
      setPatientIdTouched(false)
      setLastAutoFilledPatientId('')
      setSelectedNoteSet(uploaded)
      setSelectedNoteSetId(uploaded.id)
      setActiveView('reviews')
      await loadWorkspace()
      if (uploaded.review_chart_id) {
        await loadChartDetail(uploaded.review_chart_id)
      }
      setStatus(`Clinical notes uploaded for patient ${uploaded.patient_id}. The system review is ready for office-manager disposition.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Upload failed')
    } finally {
      setIsBusy(false)
    }
  }

  async function downloadDocument(noteSetId: number, document: PatientNoteDocument) {
    setIsBusy(true)
    setError('')
    try {
      const response = await fetch(`${API}/patient-note-sets/${noteSetId}/documents/${document.id}/download`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) {
        const payload = (await readJson(response)) as ApiError | null
        throw new Error(readErrorMessage(response.status, payload))
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const anchor = window.document.createElement('a')
      anchor.href = url
      anchor.download = document.original_filename
      anchor.click()
      URL.revokeObjectURL(url)
      setStatus(`Downloaded ${document.original_filename}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Document download failed')
    } finally {
      setIsBusy(false)
    }
  }

  function exportSelectedChart(format: 'json' | 'csv') {
    if (!selectedChart) {
      setError('Select a review before exporting a report.')
      return
    }
    const safePatientId = selectedChart.patient_id.replace(/[^a-z0-9_-]+/gi, '-')
    const checklistVersion = treatmentPlanChecklist?.version || '1.1.0'
    if (format === 'json') {
      downloadTextFile(
        `review-report-${safePatientId}.json`,
        JSON.stringify(
          {
            report_type: 'chart_review',
            checklist_id: treatmentPlanChecklist?.checklist_id || 'treatment-plan-v1',
            checklist_version: checklistVersion,
            generated_at: new Date().toISOString(),
            chart: selectedChart,
          },
          null,
          2,
        ),
        'application/json',
      )
    } else {
      const header = ['step', 'section', 'label', 'status', 'notes', 'evidence_location', 'evidence_date', 'expiration_date', 'instructions']
      const rows = selectedChart.checklist_items.map((item) =>
        [item.step, item.section, item.label, STATUS_LABELS[item.status], item.notes, item.evidence_location, item.evidence_date, item.expiration_date, item.instructions]
          .map(csvCell)
          .join(','),
      )
      downloadTextFile(`review-report-${safePatientId}.csv`, [header.map(csvCell).join(','), ...rows].join('\n'), 'text/csv')
    }
    setStatus(`Exported review report for patient ${selectedChart.patient_id}.`)
  }

  function exportSelectedTimeliness(format: 'json' | 'csv') {
    if (!selectedTimelinessClient) {
      setError('Select a treatment-plan item before exporting a report.')
      return
    }
    const safePatientId = selectedTimelinessClient.patient_id.replace(/[^a-z0-9_-]+/gi, '-')
    const checklistVersion = treatmentPlanChecklist?.version || '1.1.0'
    if (format === 'json') {
      downloadTextFile(
        `treatment-plan-report-${safePatientId}.json`,
        JSON.stringify(
          {
            report_type: 'treatment_plan_timeliness',
            checklist_id: treatmentPlanChecklist?.checklist_id || 'treatment-plan-v1',
            checklist_version: checklistVersion,
            generated_at: new Date().toISOString(),
            client: selectedTimelinessClient,
          },
          null,
          2,
        ),
        'application/json',
      )
    } else {
      const header = ['rule_id', 'label', 'status', 'due_date', 'evidence_summary']
      const rows = selectedTimelinessClient.rule_results.map((result) =>
        [result.rule_id, result.label, result.status, result.due_date || '', result.evidence_summary].map(csvCell).join(','),
      )
      downloadTextFile(`treatment-plan-report-${safePatientId}.csv`, [header.map(csvCell).join(','), ...rows].join('\n'), 'text/csv')
    }
    setStatus(`Exported treatment-plan report for patient ${selectedTimelinessClient.patient_id}.`)
  }

  function exportTimelinessTaskList() {
    const items = timelinessDashboard?.items || []
    const taskCount = timelinessTaskItems(items).length
    if (!taskCount) {
      setAppDialog({
        title: 'No task rows to export',
        message: 'There are no overdue, urgent, due soon, needs review, or missing data treatment-plan items in the current queue.',
      })
      return
    }
    downloadTextFile('treatment-plan-task-list.csv', buildTimelinessTaskList(items), 'text/csv')
    setStatus(`Exported ${taskCount} treatment-plan task rows for manual tracking.`)
  }

  async function copyTimelinessTaskList() {
    const items = timelinessDashboard?.items || []
    const taskCount = timelinessTaskItems(items).length
    if (!taskCount) {
      setAppDialog({
        title: 'No task rows to copy',
        message: 'There are no overdue, urgent, due soon, needs review, or missing data treatment-plan items in the current queue.',
      })
      return
    }
    const taskList = buildTimelinessTaskList(items)
    try {
      if (!navigator.clipboard?.writeText) {
        downloadTextFile('treatment-plan-task-list.csv', taskList, 'text/csv')
        setAppDialog({
          title: 'Clipboard unavailable',
          message: 'The browser clipboard is not available, so the task list was exported as a CSV file instead.',
        })
        return
      }
      await navigator.clipboard.writeText(taskList)
      setStatus(`Copied ${taskCount} treatment-plan task rows for manual tracking.`)
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'The browser could not copy the task list.'
      setAppDialog({ title: 'Copy task list failed', message })
    }
  }

  function openComparisonEvidence() {
    if (!selectedTimelinessClient) return
    const comparison = selectedTimelinessClient.evidence_comparison
    setEvidencePreview({
      title: 'Review due-date evidence',
      subtitle: selectedTimelinessClient.permitted_name || selectedTimelinessClient.patient_id,
      fields: [
        { label: 'Source-document Next Review Due', value: displayDate(comparison.document_next_due_date), emphasis: true },
        { label: 'Staff signature date', value: displayDate(comparison.staff_signature_date), emphasis: true },
        { label: 'Staff signature + LOC cadence', value: displayDate(comparison.signature_anchor_due_date) },
        { label: 'Current LOC effective date', value: displayDate(comparison.loc_effective_date), emphasis: true },
        { label: 'LOC effective date + cadence', value: displayDate(comparison.loc_anchor_due_date) },
        { label: 'Cadence interval', value: comparison.interval_days == null ? 'Not configured' : `${comparison.interval_days} days` },
        { label: 'Source evidence', value: comparison.source_evidence || selectedTimelinessClient.source_evidence || 'Not recorded' },
      ],
      note: comparison.conflict_explanation || 'No due-date comparison detail is available.',
    })
  }

  function openPlanEvidence(plan: TimelinessTreatmentPlan) {
    setEvidencePreview({
      title: `${planKindLabel(plan.plan_kind)} treatment-plan evidence`,
      subtitle: plan.source_section || plan.source_evidence || 'Treatment plan source',
      fields: [
        { label: 'Document date', value: displayDate(plan.document_date) },
        { label: 'Staff / therapist signature', value: signedLabel(plan.staff_signature_date), emphasis: true },
        { label: 'Client signature', value: plan.client_signature_date || (plan.plan_kind === 'review' ? 'Optional for ongoing reviews' : 'Missing') },
        { label: 'Reviewer signature', value: displayDate(plan.reviewer_signature_date) },
        { label: 'Displayed Next Review Due', value: displayDate(plan.displayed_next_due_date), emphasis: Boolean(plan.displayed_next_due_date) },
        { label: 'Source document ID', value: plan.source_document_id || 'Not recorded' },
        { label: 'Source evidence', value: plan.source_evidence || 'Not recorded' },
      ],
      note: plan.conflict_note || 'Evidence preview shows date/signature metadata only; raw clinical document text is not displayed here.',
    })
  }

  function openLocEvidence(entry: TimelinessLevelOfCare) {
    setEvidencePreview({
      title: 'Level-of-care evidence',
      subtitle: entry.source_evidence || entry.level_of_care || 'LOC source',
      fields: [
        { label: 'Level of care', value: entry.level_of_care || 'Missing', emphasis: true },
        { label: 'Facility', value: entry.facility || 'Not recorded' },
        { label: 'Effective / admission date', value: displayDate(entry.effective_date), emphasis: true },
        { label: 'Discharge / stepdown date', value: displayDate(entry.discharge_date) },
        { label: 'Cadence interval', value: entry.interval_days == null ? 'Not configured' : `${entry.interval_days} days` },
        { label: 'State', value: entry.is_current ? 'Current' : 'Ended' },
        { label: 'Source evidence', value: entry.source_evidence || 'Not recorded' },
      ],
      note: entry.is_current ? 'This is treated as the current LOC row because it has no discharge/stepdown date.' : 'Ended LOC rows explain historical cadence windows.',
    })
  }

  async function handleSaveReviewChanges() {
    if (!selectedChart || !canEditCriteria) return
    setIsBusy(true)
    setError('')
    setStatus(`Saving criterion review changes for patient ${selectedChart.patient_id}...`)
    try {
      const updated = await apiRequest<ChartDetail>(`/charts/${selectedChart.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(toChartUpdatePayload(selectedChart)),
      })
      setSelectedChart(copyChartDetail(updated))
      setReviewDirty(false)
      await loadWorkspace()
      setStatus(`Criterion review changes saved for patient ${updated.patient_id}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to save review changes')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleTransition(action: TransitionAction) {
    if (!selectedChart) return
    if (action.requiresComment && !decisionComment.trim()) {
      setError('Enter a manager comment before returning a chart to the counselor.')
      return
    }
    if (action.toState === 'Approved by Office Manager' && openItems.length > 0 && !decisionComment.trim()) {
      setError('Add an approval note before approving a chart that still has open or missing criteria.')
      return
    }

    setIsBusy(true)
    setError('')
    setStatus(`${action.label} in progress for patient ${selectedChart.patient_id}...`)
    try {
      const updated = await apiRequest<ChartDetail>(`/charts/${selectedChart.id}/transition`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to_state: action.toState, comment: decisionComment }),
      })
      setSelectedChart(copyChartDetail(updated))
      setDecisionComment('')
      setReviewDirty(false)
      await loadWorkspace()
      setStatus(`Office-manager decision recorded for patient ${updated.patient_id}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Transition failed')
    } finally {
      setIsBusy(false)
    }
  }

  function handleTransitionButton(action: TransitionAction) {
    if (reviewDirty) {
      setAppDialog({
        title: 'Save criterion changes first',
        message: 'There are unsaved criterion review changes. Save them before recording the office-manager disposition.',
      })
      setStatus('Office-manager decision was not recorded because criterion changes are unsaved.')
      recordButtonAction(activeView, action.label, 'blocked', { blocked_reason: 'unsaved_review_changes' })
      return
    }
    void handleTransition(action)
  }

  async function handleCreateUser(event: FormEvent) {
    event.preventDefault()
    const validationError = validateCreateUserForm(newUserForm)
    if (validationError) {
      setError(validationError)
      return
    }
    setIsBusy(true)
    setError('')
    try {
      const created = await apiRequest<User>('/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newUserForm),
      })
      setNewUserForm({ username: '', full_name: '', password: '', role: 'counselor' })
      setUserFilters({ query: '', role: 'all' })
      setAdminPasswordReset('')
      await loadUsers(created.id)
      setStatus(`User ${created.username} created successfully.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to create user')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleSaveManagedUser(event: FormEvent) {
    event.preventDefault()
    if (!selectedManagedUser || !managedUserForm) return
    setIsBusy(true)
    setError('')
    try {
      const updated = await apiRequest<User>(`/users/${selectedManagedUser.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(managedUserForm),
      })
      await loadUsers(updated.id)
      setStatus(`Updated user ${updated.username}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to update user')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleAdminPasswordReset(event: FormEvent) {
    event.preventDefault()
    if (!selectedManagedUser || !adminPasswordReset.trim()) return
    setIsBusy(true)
    setError('')
    try {
      await apiRequest<User>(`/users/${selectedManagedUser.id}/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_password: adminPasswordReset, require_reset_on_login: true }),
      })
      setAdminPasswordReset('')
      await loadUsers(selectedManagedUser.id)
      setStatus(`Password reset staged for ${selectedManagedUser.username}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to reset password')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleDeleteManagedUser(event: FormEvent) {
    event.preventDefault()
    if (!selectedManagedUser) return
    if (deleteUserConfirmation.trim() !== selectedManagedUser.username) {
      setError(`Type ${selectedManagedUser.username} exactly to confirm deletion.`)
      return
    }

    const username = selectedManagedUser.username
    setIsBusy(true)
    setError('')
    try {
      await apiRequest<{ status: string }>(`/users/${selectedManagedUser.id}`, {
        method: 'DELETE',
      })
      setDeleteUserConfirmation('')
      await loadUsers()
      setStatus(`Deleted user ${username}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to delete user')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleProfileSave(event: FormEvent) {
    event.preventDefault()
    setIsBusy(true)
    setError('')
    try {
      const updated = await apiRequest<User>('/users/me', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profileForm),
      })
      setUser(updated)
      setProfileForm({ full_name: updated.full_name })
      setStatus('Your profile has been updated.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to update profile')
    } finally {
      setIsBusy(false)
    }
  }

  async function handlePasswordChange(event: FormEvent) {
    event.preventDefault()
    setIsBusy(true)
    setError('')
    try {
      await apiRequest('/users/me/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(passwordChangeForm),
      })
      setPasswordChangeForm({ current_password: '', new_password: '' })
      setStatus('Your password has been updated.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to change password')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleSettingsSave(event: FormEvent) {
    event.preventDefault()
    if (!settingsForm) return
    setIsBusy(true)
    setError('')
    try {
      const payload = await apiRequest<AppSettings>('/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settingsForm),
      })
      setAppSettings(payload)
      setSettingsForm(createSettingsForm(payload))
      setEmrProfile(await apiRequest<EmrProfile>('/emr/profile'))
      setStatus('Application settings have been updated.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to update application settings')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleWorkflowDefinitionCreate(event: FormEvent) {
    event.preventDefault()
    setIsBusy(true)
    setError('')
    try {
      const versionPayload = parseWorkflowVersionInput(workflowDefinitionForm)
      const created = await apiRequest<WorkflowDefinition>('/workflow-definitions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workflow_key: workflowDefinitionForm.workflow_key.trim(),
          display_name: workflowDefinitionForm.display_name.trim(),
          description: workflowDefinitionForm.description.trim(),
          category: workflowDefinitionForm.category.trim() || 'clinical_review',
          initial_version: versionPayload,
        }),
      })
      setWorkflowDefinitionForm(createWorkflowDefinitionForm())
      await loadWorkflowDefinitions(created.id)
      setStatus(`Workflow profile ${created.workflow_key} created.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to create workflow profile')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleWorkflowVersionCreate(event: FormEvent) {
    event.preventDefault()
    if (!selectedWorkflowDefinition) return
    setIsBusy(true)
    setError('')
    try {
      const versionPayload = parseWorkflowVersionInput(workflowVersionForm)
      await apiRequest<WorkflowDefinitionVersion>(`/workflow-definitions/${selectedWorkflowDefinition.id}/versions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(versionPayload),
      })
      await loadWorkflowDefinitions(selectedWorkflowDefinition.id)
      setStatus(`Draft workflow version created for ${selectedWorkflowDefinition.workflow_key}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to create workflow version')
    } finally {
      setIsBusy(false)
    }
  }

  async function seedWorkflowDraftFromCanonicalChecklist() {
    if (!selectedWorkflowDefinition) return
    setIsBusy(true)
    setError('')
    try {
      const checklist = treatmentPlanChecklist || (await apiRequest<TreatmentPlanChecklist>('/treatment-plan-checklist'))
      setTreatmentPlanChecklist(checklist)
      setWorkflowVersionForm({
        version_notes: `Admin-editable draft seeded from ${checklist.display_name} v${checklist.version}.`,
        definition_snapshot_text: JSON.stringify(workflowSnapshotFromChecklist(checklist), null, 2),
        transition_rules_text: JSON.stringify(defaultWorkflowTransitionsFromChecklist(), null, 2),
      })
      setStatus('Canonical 42-step checklist loaded into the workflow draft editor. Review, edit, create draft, then publish when ready.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to load canonical checklist into workflow editor')
    } finally {
      setIsBusy(false)
    }
  }

  async function publishWorkflowVersion(versionId: number) {
    if (!selectedWorkflowDefinition) return
    setIsBusy(true)
    setError('')
    try {
      await apiRequest<WorkflowDefinition>(`/workflow-definitions/${selectedWorkflowDefinition.id}/versions/${versionId}/publish`, {
        method: 'POST',
      })
      await loadWorkflowDefinitions(selectedWorkflowDefinition.id)
      setStatus(`Workflow version published for ${selectedWorkflowDefinition.workflow_key}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to publish workflow version')
    } finally {
      setIsBusy(false)
    }
  }

  async function archiveWorkflowDefinition() {
    if (!selectedWorkflowDefinition) return
    setIsBusy(true)
    setError('')
    try {
      await apiRequest<WorkflowDefinition>(`/workflow-definitions/${selectedWorkflowDefinition.id}/archive`, {
        method: 'POST',
      })
      await loadWorkflowDefinitions(selectedWorkflowDefinition.id)
      setStatus(`Workflow profile ${selectedWorkflowDefinition.workflow_key} archived.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to archive workflow profile')
    } finally {
      setIsBusy(false)
    }
  }

  async function deleteWorkflowDefinition() {
    if (!selectedWorkflowDefinition || !selectedWorkflowDefinitionCanDelete) return
    setIsBusy(true)
    setError('')
    try {
      await apiRequest<{ status: string; workflow_key: string }>(`/workflow-definitions/${selectedWorkflowDefinition.id}`, {
        method: 'DELETE',
      })
      await loadWorkflowDefinitions(null)
      setStatus(`Workflow profile ${selectedWorkflowDefinition.workflow_key} deleted.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to delete workflow profile')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleTimelinessOverride(event: FormEvent) {
    event.preventDefault()
    if (!selectedTimelinessClient || !canOverrideTimeliness) return
    if (!timelinessOverrideForm.reason.trim()) {
      setError('Enter an override reason before saving.')
      return
    }

    setIsBusy(true)
    setError('')
    try {
      await apiRequest<TimelinessOverride>(`/timeliness/clients/${selectedTimelinessClient.id}/overrides`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(timelinessOverrideForm),
      })
      await loadTimelinessDashboard(selectedTimelinessClient.id)
      setStatus(`Treatment plan override recorded for patient ${selectedTimelinessClient.patient_id}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to save timeliness override')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleEmrDiscovery() {
    const fhirBaseUrl = settingsForm?.emr_fhir_base_url.trim() || ''
    if (!fhirBaseUrl) {
      setError('Enter the Alleva FHIR base URL before running discovery.')
      return
    }
    setIsBusy(true)
    setError('')
    try {
      const payload = await apiRequest<EmrDiscovery>('/emr/discover', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fhir_base_url: fhirBaseUrl }),
      })
      setEmrDiscovery(payload)
      setStatus('EMR discovery completed.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'EMR discovery failed')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleEmrImportPlan() {
    const patientId = emrPlanPatientId.trim()
    if (!patientId) {
      setError('Enter a patient ID or MRN before building an EMR import plan.')
      return
    }
    setIsBusy(true)
    setError('')
    try {
      const payload = await apiRequest<EmrImportPlan>(`/emr/import-plan?patient_id=${encodeURIComponent(patientId)}`)
      setEmrImportPlan(payload)
      setStatus('EMR import plan is ready.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to build EMR import plan')
    } finally {
      setIsBusy(false)
    }
  }

  function openRejectedPatientUpload(chart: ChartDetail) {
    setActiveView('uploads')
    setUploadForm(
      createUploadForm({
        patient_id: chart.patient_id,
        client_name: chart.client_name,
        upload_mode: 'update',
        level_of_care: chart.level_of_care,
        admission_date: chart.admission_date,
        discharge_date: chart.discharge_date,
        primary_clinician: chart.primary_clinician,
        upload_notes: chart.manager_comment ? `Manager follow-up: ${chart.manager_comment}` : '',
      }),
    )
  }

  function handleSignOut() {
    setToken('')
    setUser(null)
    setMustResetPassword(false)
    setCharts([])
    setNoteSets([])
    setSelectedChart(null)
    setSelectedChartId(null)
    setSelectedNoteSet(null)
    setSelectedNoteSetId(null)
    setTimelinessDashboard(null)
    setSelectedTimelinessClient(null)
    setSelectedTimelinessClientId(null)
    setTimelinessStatusFilter('All')
    setTimelinessSearch('')
    setTimelinessOverrideForm(createTimelinessOverrideForm())
    setEvidencePreview(null)
    setAppDialog(null)
    setReadiness(null)
    setStatus('Signed out. Sign in to continue.')
    setError('')
  }

  function handleSelectManagedUser(nextId: number) {
    setSelectedManagedUserId(nextId)
    const next = users.find((candidate) => candidate.id === nextId) || null
    setManagedUserForm(
      next
        ? {
            full_name: next.full_name,
            role: next.role,
            is_active: next.is_active,
            is_locked: next.is_locked,
            must_reset_password: next.must_reset_password,
          }
        : null,
    )
    setAdminPasswordReset('')
    setDeleteUserConfirmation('')
  }

  function renderTrendCard(title: string, points: TrendPoint[]) {
    const max = Math.max(1, ...points.map((point) => point.count))
    return (
      <article className='trend-card'>
        <div className='trend-card__header'>
          <strong>{title}</strong>
          <span>Last 7 days</span>
        </div>
        <div className='trend-strip'>
          {points.map((point) => (
            <div key={`${title}-${point.label}`} className='trend-strip__point'>
              <span className='trend-strip__count'>{point.count}</span>
              <div className='trend-strip__bar'>
                <div className='trend-strip__fill' style={{ height: `${(point.count / max) * 100}%` }} />
              </div>
              <span className='trend-strip__label'>{point.label}</span>
            </div>
          ))}
        </div>
      </article>
    )
  }

  return (
    <main className='shell' onClickCapture={handleButtonAuditCapture}>
      <section className='hero'>
        <div>
          <p className='eyebrow'>R3 Recovery Services Chart Audit</p>
          <h1>Clinical notes completeness review</h1>
          <p className='hero-copy'>
            Upload a patient binder, review each chart-audit criterion, and route final approval through the office manager.
          </p>
        </div>
        <div className='status-card'>
          <h2>Current status</h2>
          <p>{status}</p>
          {error ? <p className='error-text'>{error}</p> : null}
          {user ? (
            <div className='status-meta'>
              <span>{user.full_name || user.username}</span>
              <span>{user.role}</span>
            </div>
          ) : null}
        </div>
      </section>

      {!token ? (
        <section className='auth-grid'>
          <form className='panel form-panel' onSubmit={handleLogin}>
            <h2>Sign in</h2>
            <label>
              Username
              <input
                required
                autoComplete='username'
                value={loginForm.username}
                onChange={(event) => setLoginForm((current) => ({ ...current, username: event.target.value }))}
              />
            </label>
            <label>
              Password
              <input
                type='password'
                required
                autoComplete='current-password'
                value={loginForm.password}
                onChange={(event) => setLoginForm((current) => ({ ...current, password: event.target.value }))}
              />
            </label>
            <button type='submit' disabled={isBusy}>
              {isBusy ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
          <div className='panel info-panel'>
            <h2>Workflow</h2>
            <ol>
              <li>Counselor uploads a patient note binder using patient ID and client name when available.</li>
              <li>The app runs an automatic clinical-note checklist evaluation.</li>
              <li>The reviewer can drill into any criterion and mark it ok or not ok.</li>
              <li>The office manager approves or returns the chart for correction.</li>
              <li>Every read, write, approval, and change is written to the forensic log.</li>
            </ol>
          </div>
        </section>
      ) : mustResetPassword ? (
        <section className='panel form-panel narrow'>
          <h2>Password reset required</h2>
          <p>This applies to managed user accounts. The bootstrap admin password is fixed outside the app.</p>
          <form onSubmit={handlePasswordReset}>
            <label>
              New password
              <input
                type='password'
                placeholder='New password (min 12 chars)'
                value={resetForm.newPassword}
                onChange={(event) => setResetForm({ newPassword: event.target.value })}
              />
            </label>
            <button type='submit' disabled={isBusy}>
              {isBusy ? 'Saving...' : 'Reset password'}
            </button>
          </form>
        </section>
      ) : (
        <>
          <section className='metrics'>
            <article className='metric-card'>
              <span>Current open</span>
              <strong>{totalOpen}</strong>
            </article>
            <article className='metric-card'>
              <span>Awaiting approval</span>
              <strong>{totalAwaiting}</strong>
            </article>
            <article className='metric-card'>
              <span>Waiting re-verification</span>
              <strong>{totalWaitingReverification}</strong>
            </article>
            <article className='metric-card'>
              <span>Approved</span>
              <strong>{totalApproved}</strong>
            </article>
          </section>

          <nav className='view-tabs'>
            {(['dashboard', 'reviews', 'timeliness', 'checklist', 'uploads', 'profile'] as AppView[]).map((view) => (
              <button
                key={view}
                className={activeView === view ? 'tab-button tab-button--active' : 'tab-button'}
                onClick={() => setActiveView(view)}
                type='button'
              >
                {VIEW_LABELS[view]}
              </button>
            ))}
            {user?.role === 'admin'
              ? (['users', 'logs', 'settings'] as AppView[]).map((view) => (
                  <button
                    key={view}
                    className={activeView === view ? 'tab-button tab-button--active' : 'tab-button'}
                    onClick={() => setActiveView(view)}
                    type='button'
                  >
                    {VIEW_LABELS[view]}
                  </button>
                ))
              : null}
            <button className='tab-button' onClick={handleSignOut} type='button'>
              Sign out
            </button>
          </nav>

	          {activeView === 'dashboard' ? (
	            <section className='dashboard-grid'>
              <section className='panel detail-panel'>
                <div className='panel-heading'>
                  <div>
                    <h2>Summary dashboard</h2>
                    <p>Queue health, recent throughput, and approval trends for the current workspace.</p>
                  </div>
                  <button type='button' className='ghost-button' onClick={() => void loadWorkspace()} disabled={isBusy}>
                    Refresh
                  </button>
                </div>

                <div className='dashboard-metrics'>
                  <article className='mini-card'>
                    <span>Active binders</span>
                    <strong>{activeBinders}</strong>
                  </article>
                  <article className='mini-card'>
                    <span>Manager queue</span>
                    <strong>{totalAwaiting}</strong>
                  </article>
                  <article className='mini-card'>
                    <span>Returned for correction</span>
                    <strong>{totalWaitingReverification}</strong>
                  </article>
                  <article className='mini-card'>
                    <span>Current user</span>
                    <strong>{user?.full_name || user?.username}</strong>
                  </article>
                  <article className='mini-card'>
                    <span>Checklist</span>
                    <strong>v{treatmentPlanChecklist?.version || '1.1.0'}</strong>
                  </article>
                </div>

                <div className='trend-grid'>
                  {renderTrendCard('New evaluations', newEvaluationTrend)}
                  {renderTrendCard('Approvals', approvalTrend)}
                  {renderTrendCard('Re-verification queue', reverificationTrend)}
                  {renderTrendCard('Binder uploads', uploadTrend)}
                </div>

                <section className='panel-subsection'>
                  <h3>Review source</h3>
                  <div className='source-choice-grid'>
                    <article className='finding-card source-mode-card'>
                      <div className='finding-card__header'>
                        <strong>EMR/API access</strong>
                        <span className='pill pill--warning'>{reviewSourceDiscovery?.api_mode_label || 'Mock/stub mode'}</span>
                      </div>
                      <p>{reviewSourceDiscovery?.plain_english_status || 'API discovery stays in mock/readiness mode until vendor credentials, endpoint mapping, and compliance approval are complete.'}</p>
                      <dl className='source-mode-facts'>
                        <div>
                          <dt>Daily monitoring</dt>
                          <dd>{reviewSourceDiscovery?.daily_monitoring_enabled ? 'Readiness schedule available' : 'Simulated until live approval'}</dd>
                        </div>
                        <div>
                          <dt>Last refresh</dt>
                          <dd>{reviewSourceDiscovery ? formatDateTime(reviewSourceDiscovery.last_refresh_at) : 'Not run'}</dd>
                        </div>
                        <div>
                          <dt>Last safe check</dt>
                          <dd>{reviewSourceDiscovery?.last_successful_check_at ? formatDateTime(reviewSourceDiscovery.last_successful_check_at) : 'Not run'}</dd>
                        </div>
                        <div>
                          <dt>Next refresh</dt>
                          <dd>{reviewSourceDiscovery ? formatDateTime(reviewSourceDiscovery.next_refresh_at) : 'After configuration'}</dd>
                        </div>
                        <div>
                          <dt>Needs follow-up</dt>
                          <dd>{reviewSourceDiscovery?.notification_badge_count ?? reviewSourceApiItems}</dd>
                        </div>
                      </dl>
                      <div className='decision-actions'>
                        <button type='button' className='ghost-button' onClick={() => setActiveView('timeliness')}>
                          View Details
                        </button>
                        {user?.role === 'admin' || user?.role === 'manager' ? (
                          <button type='button' className='ghost-button' onClick={() => void runDailyReviewSourceCheck()} disabled={isBusy}>
                            Run daily check
                          </button>
                        ) : null}
                        {user?.role === 'admin' ? (
                          <button type='button' className='ghost-button' onClick={() => setActiveView('settings')}>
                            API settings
                          </button>
                        ) : null}
                      </div>
                    </article>
                    <article className='finding-card source-mode-card'>
                      <div className='finding-card__header'>
                        <strong>Manual upload</strong>
                        <span className='pill pill--success'>Available</span>
                      </div>
                      <p>{reviewSourceDiscovery?.manual_mode_message || 'Upload exported treatment plans and clinical note binders, then review findings using the same checklist workflow.'}</p>
                      <dl className='source-mode-facts'>
                        <div>
                          <dt>Cadence</dt>
                          <dd>Monthly compliance-check fallback</dd>
                        </div>
                        <div>
                          <dt>Active uploads</dt>
                          <dd>{activeBinders}</dd>
                        </div>
                        <div>
                          <dt>Shared workflow</dt>
                          <dd>{reviewSourceUploadItems} routed item{reviewSourceUploadItems === 1 ? '' : 's'}</dd>
                        </div>
                        <div>
                          <dt>Snapshot warning</dt>
                          <dd>As of upload time only</dd>
                        </div>
                      </dl>
                      <div className='decision-actions'>
                        <button type='button' className='ghost-button' onClick={() => setActiveView('uploads')}>
                          Upload binder
                        </button>
                        <button type='button' className='ghost-button' onClick={() => setActiveView('reviews')}>
                          View Details
                        </button>
                      </div>
                    </article>
                  </div>
                </section>
              </section>

              <aside className='panel queue-panel'>
                <section className='panel-subsection'>
                  <h3>Quick actions</h3>
                  <div className='quick-actions'>
                    <button type='button' onClick={() => setActiveView('uploads')}>
                      Upload binder
                    </button>
                    <button type='button' className='ghost-button' onClick={() => setActiveView('reviews')}>
                      Open review queue
                    </button>
                    <button type='button' className='ghost-button' onClick={() => setActiveView('timeliness')}>
                      Treatment plans
                    </button>
                    <button type='button' className='ghost-button' onClick={() => setActiveView('checklist')}>
                      Checklist v1
                    </button>
                    <button type='button' className='ghost-button' onClick={() => setActiveView('profile')}>
                      My account
                    </button>
                    {user?.role === 'admin' ? (
                      <>
                        <button type='button' className='ghost-button' onClick={() => setActiveView('users')}>
                          User management
                        </button>
                        <button type='button' className='ghost-button' onClick={() => setActiveView('logs')}>
                          Forensic logs
                        </button>
                        <button type='button' className='ghost-button' onClick={() => setActiveView('settings')}>
                          Settings
                        </button>
                      </>
                    ) : null}
                  </div>
                </section>

                <section className='panel-subsection'>
                  <h3>Current queue</h3>
                  {charts.length ? (
                    <ul className='queue-list'>
                      {charts.slice(0, 5).map((chart) => (
                        <li key={chart.id}>
                          <button type='button' className='queue-item' data-audit-label='Open dashboard queue chart' onClick={() => void loadChartDetail(chart.id)}>
                            <div>
                              <strong>{chart.patient_id}</strong>
                              <span>{chart.primary_clinician || 'Clinician pending'}</span>
                            </div>
                            <div className='queue-item-meta'>
                              <span className={`pill pill--${workflowTone(chart.state)}`}>{chart.state}</span>
                              <span>{chart.system_score}%</span>
                            </div>
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className='empty-state'>No automated reviews are in the queue yet.</p>
                  )}
                </section>

                {user?.role === 'admin' ? (
                  <section className='panel-subsection admin-banner'>
                    <h3>Administrator controls</h3>
                    <p>
                      User management and forensic log review are available only to the administrator. Active: {activeUserCount}, locked:{' '}
                      {lockedUserCount}, password reset required: {resetRequiredCount}.
                    </p>
                    {readiness ? (
                      <p>
                        Runtime readiness: {readiness.status}. Failed checks: {readiness.failed}. Warnings: {readiness.warnings}.
                      </p>
                    ) : null}
                  </section>
                ) : null}
              </aside>
	            </section>
	          ) : null}

	          {activeView === 'timeliness' ? (
	            <section className='timeliness-workspace'>
	              <aside className='panel queue-panel timeliness-queue-panel'>
	                <div className='panel-heading'>
	                  <div>
	                    <h2>Treatment plan timeliness</h2>
	                    <p>Evidence-first work queue updated in {timelinessBuildLabel}; compare source due dates, staff signatures, and LOC anchors before acting.</p>
	                  </div>
	                  <div className='button-row'>
	                    <button type='button' className='ghost-button' onClick={() => void copyTimelinessTaskList()} disabled={isBusy}>
	                      Copy task list
	                    </button>
	                    <button type='button' className='ghost-button' onClick={exportTimelinessTaskList} disabled={isBusy}>
	                      Export task list
	                    </button>
	                    <button type='button' className='ghost-button' onClick={() => void loadTimelinessDashboard()} disabled={isBusy}>
	                      Refresh
	                    </button>
	                  </div>
	                </div>

	                <section className='timeliness-release-banner' role='status' aria-label='Treatment plan timeliness update status'>
	                  <strong>Updated evidence queue {timelinessBuildLabel}</strong>
	                  <span>Source-document Next Review Due, staff-signature cadence, and LOC-effective cadence are shown side by side in the selected-client detail.</span>
	                </section>

	                <form
	                  className='filter-row timeliness-filter-row'
	                  onSubmit={(event) => {
	                    event.preventDefault()
	                    void loadTimelinessDashboard()
	                  }}
	                >
	                  <label>
	                    Evaluation date
	                    <input type='date' value={timelinessEvaluationDate} onChange={(event) => setTimelinessEvaluationDate(event.target.value)} />
	                  </label>
	                  <label>
	                    Search queue
	                    <input
	                      type='search'
	                      value={timelinessSearch}
	                      onChange={(event) => setTimelinessSearch(event.target.value)}
	                      placeholder='Client, LOC, clinician'
	                    />
	                  </label>
	                  <button type='submit' disabled={isBusy}>
	                    Apply date
	                  </button>
	                </form>

	                <div className='dashboard-metrics timeliness-metrics'>
	                  <article className='mini-card'>
	                    <span>Active clients</span>
	                    <strong>{timelinessDashboard?.total_active_clients ?? 0}</strong>
	                  </article>
	                  <article className='mini-card'>
	                    <span>Task rows</span>
	                    <strong>{exportableTimelinessTaskCount}</strong>
	                  </article>
	                  <article className='mini-card mini-card--danger'>
	                    <span>Overdue</span>
	                    <strong>{timelinessDashboard?.overdue ?? 0}</strong>
	                  </article>
	                  <article className='mini-card mini-card--warning'>
	                    <span>Urgent</span>
	                    <strong>{timelinessDashboard?.urgent ?? 0}</strong>
	                  </article>
	                  <article className='mini-card mini-card--attention'>
	                    <span>Needs review</span>
	                    <strong>{timelinessDashboard?.needs_review ?? 0}</strong>
	                  </article>
	                  <article className='mini-card mini-card--muted'>
	                    <span>Missing data</span>
	                    <strong>{timelinessDashboard?.missing_data ?? 0}</strong>
	                  </article>
	                </div>

	                {timelinessDashboard && !timelinessDashboard.loc_change_window_validated ? (
	                  <section className='panel-subsection admin-banner timeliness-loc-warning'>
	                    <h3>Unvalidated LOC-change rule</h3>
	                    <p>
	                      The level-of-care change anchor/window is still unvalidated by R3/Marleigh. Current setting:{' '}
	                      {timelinessDashboard.loc_change_window_days == null ? 'not set' : `${timelinessDashboard.loc_change_window_days} days`}.
	                    </p>
	                  </section>
	                ) : null}

	                <div className='timeliness-filter-strip' aria-label='Timeliness status filters'>
	                  {TIMELINESS_FILTERS.map((filter) => (
	                    <button
	                      key={filter}
	                      type='button'
	                      className={timelinessStatusFilter === filter ? 'status-filter status-filter--active' : 'status-filter'}
	                      aria-pressed={timelinessStatusFilter === filter}
	                      onClick={() => setTimelinessStatusFilter(filter)}
	                    >
	                      <span>{filter}</span>
	                      <strong>{timelinessFilterCount(timelinessDashboard, filter)}</strong>
	                    </button>
	                  ))}
	                </div>

	                {timelinessDashboard?.items.length ? (
	                  <div className='timeliness-queue-table' role='table' aria-label='Treatment plan timeliness queue'>
	                    <div className='timeliness-queue-table__head' role='row'>
	                      <span>Client</span>
	                      <span>Status</span>
	                      <span>Next due</span>
	                      <span>LOC</span>
	                      <span>Evidence</span>
	                    </div>
	                    {filteredTimelinessItems.length ? (
	                      filteredTimelinessItems.map((item) => (
	                        <button
	                          type='button'
	                          key={item.id}
	                          className={
	                            selectedTimelinessClientId === item.id
	                              ? 'timeliness-queue-table__row timeliness-queue-table__row--active'
	                              : 'timeliness-queue-table__row'
	                          }
                          data-audit-label='Open treatment-plan evidence'
	                          onClick={() => void loadTimelinessClientDetail(item.id)}
	                          aria-label={`Open ${item.permitted_name || item.patient_id} treatment plan evidence`}
	                        >
	                          <span>
	                            <strong>{item.permitted_name || item.patient_id}</strong>
	                            <small>{item.patient_id}</small>
	                            <small>{item.counselor_name || 'Primary clinician pending'}</small>
	                          </span>
	                          <span>
	                            <span className={`pill pill--${timelinessTone(item.status)}`}>{item.status}</span>
	                          </span>
	                          <span>
	                            <strong>{item.next_due_date || 'Missing'}</strong>
	                            <small>{item.days_until_due == null ? 'days n/a' : `${item.days_until_due} days`}</small>
	                          </span>
	                          <span>{item.current_level_of_care || 'Missing'}</span>
	                          <span>
	                            <strong>{item.evidence_completeness_percent}%</strong>
	                            <small>{item.rule_used}</small>
	                          </span>
	                        </button>
	                      ))
	                    ) : (
	                      <p className='empty-state'>No treatment-plan clients match the current filter.</p>
	                    )}
	                  </div>
	                ) : (
	                  <p className='empty-state'>No active treatment-plan clients are loaded.</p>
	                )}
	              </aside>

	              <section className='panel detail-panel timeliness-detail-panel'>
	                {selectedTimelinessClient ? (
	                  <>
	                    <div className='panel-heading'>
	                      <div>
	                        <h2>{selectedTimelinessClient.permitted_name || selectedTimelinessClient.patient_id}</h2>
	                        <p>{selectedTimelinessClient.patient_id}</p>
	                      </div>
	                      <div className='button-row'>
	                        <button type='button' className='ghost-button' onClick={() => exportSelectedTimeliness('csv')}>
	                          Export CSV
	                        </button>
	                        <button type='button' className='ghost-button' onClick={() => exportSelectedTimeliness('json')}>
	                          Export JSON
	                        </button>
	                        <span className={`pill pill--${timelinessTone(selectedTimelinessClient.status)}`}>{selectedTimelinessClient.status}</span>
	                      </div>
	                    </div>

	                    <section className='timeliness-client-summary' aria-label='Selected treatment plan client summary'>
	                      <div>
	                        <span>Next review due</span>
	                        <strong>{selectedTimelinessClient.next_due_date || 'Missing'}</strong>
	                        <small>{selectedTimelinessClient.days_until_due == null ? 'No day count' : `${selectedTimelinessClient.days_until_due} days from evaluation date`}</small>
	                      </div>
	                      <dl>
	                        <div>
	                          <dt>Admission date</dt>
	                          <dd>{selectedTimelinessClient.admission_date || 'Missing'}</dd>
	                        </div>
	                        <div>
	                          <dt>Current LOC</dt>
	                          <dd>{selectedTimelinessClient.current_level_of_care || 'Missing'}</dd>
	                        </div>
	                        <div>
	                          <dt>Primary clinician</dt>
	                          <dd>{selectedTimelinessClient.counselor_name || 'Not recorded'}</dd>
	                        </div>
	                        <div>
	                          <dt>Evidence completeness</dt>
	                          <dd>
	                            <span className='evidence-meter' aria-label={`Evidence completeness ${selectedTimelinessClient.evidence_completeness_percent}%`}>
	                              <span style={{ width: `${selectedTimelinessClient.evidence_completeness_percent}%` }} />
	                            </span>
	                            {selectedTimelinessClient.evidence_completeness_percent}%
	                          </dd>
	                        </div>
	                      </dl>
	                      {selectedTimelinessClient.missing_evidence_fields.length ? (
	                        <p>Missing: {selectedTimelinessClient.missing_evidence_fields.join(', ')}</p>
	                      ) : (
	                        <p>Required evidence fields are present for this calculation.</p>
	                      )}
	                    </section>

	                    <section className='panel-subsection evidence-comparison-panel'>
	                      <div className='panel-heading'>
	                        <div>
	                          <h3>Evidence comparison</h3>
	                          <p>Document due date, signature calculation, and LOC-anchor calculation are shown together.</p>
	                        </div>
	                        <button type='button' className='ghost-button' onClick={openComparisonEvidence}>
	                          View evidence
	                        </button>
	                      </div>
	                      <div className='comparison-grid'>
	                        <article>
	                          <span>Source-document Next Review Due</span>
	                          <strong>{displayDate(selectedTimelinessClient.evidence_comparison.document_next_due_date)}</strong>
	                        </article>
	                        <article>
	                          <span>Staff signature + LOC interval</span>
	                          <strong>{displayDate(selectedTimelinessClient.evidence_comparison.signature_anchor_due_date)}</strong>
	                          <small>{displayDate(selectedTimelinessClient.evidence_comparison.staff_signature_date)} staff signature</small>
	                        </article>
	                        <article>
	                          <span>Current LOC effective date + interval</span>
	                          <strong>{displayDate(selectedTimelinessClient.evidence_comparison.loc_anchor_due_date)}</strong>
	                          <small>{displayDate(selectedTimelinessClient.evidence_comparison.loc_effective_date)} LOC effective</small>
	                        </article>
	                        <article>
	                          <span>Final status</span>
	                          <strong>{selectedTimelinessClient.evidence_comparison.final_status}</strong>
	                          <small>{selectedTimelinessClient.rule_used}</small>
	                        </article>
	                      </div>
	                      <div className='rule-alert'>
	                        <strong>
	                          {selectedTimelinessClient.evidence_comparison.loc_change_rule_validated
	                            ? 'Validated LOC-change setting'
	                            : 'Unvalidated LOC-change rule'}
	                        </strong>
	                        <p>{selectedTimelinessClient.evidence_comparison.conflict_explanation}</p>
	                      </div>
	                    </section>

	                    <section className='panel-subsection'>
	                      <h3>Rule results</h3>
	                      <div className='finding-list'>
	                        {selectedTimelinessClient.rule_results.map((result) => (
	                          <article key={result.rule_id} className='finding-card finding-card--compact'>
	                            <div className='finding-card__header'>
	                              <div>
	                                <strong>{result.label}</strong>
	                                <p>{result.rule_id}</p>
	                              </div>
	                              <span className={`pill pill--${timelinessTone(result.status)}`}>{result.status}</span>
	                            </div>
	                            <dl>
	                              <div>
	                                <dt>Due date</dt>
	                                <dd>{result.due_date || 'Not calculated'}</dd>
	                              </div>
	                              <div>
	                                <dt>Evidence</dt>
	                                <dd>{result.evidence_summary}</dd>
	                              </div>
	                            </dl>
	                          </article>
	                        ))}
	                      </div>
	                    </section>

	                    <section className='panel-subsection'>
	                      <h3>Level-of-care history</h3>
	                      {selectedTimelinessClient.level_of_care_history.length ? (
	                        <div className='timeliness-table timeliness-table--loc'>
	                          <div className='timeliness-table__head'>
	                            <span>LOC</span>
	                            <span>Facility</span>
	                            <span>Effective</span>
	                            <span>Discharge</span>
	                            <span>Cadence</span>
	                            <span>State</span>
	                            <span>Evidence</span>
	                          </div>
	                          {selectedTimelinessClient.level_of_care_history.map((entry) => (
	                            <div key={entry.id} className='timeliness-table__row'>
	                              <span>{entry.level_of_care}</span>
	                              <span>{entry.facility || 'Not recorded'}</span>
	                              <span>{entry.effective_date || 'Missing'}</span>
	                              <span>{entry.discharge_date || 'Current'}</span>
	                              <span>{entry.interval_days == null ? 'Not configured' : `${entry.interval_days} days`}</span>
	                              <span>
	                                <span className={`pill pill--${entry.is_current ? 'success' : 'neutral'}`}>{entry.is_current ? 'Current' : 'Ended'}</span>
	                              </span>
	                              <span>
	                                <button type='button' className='table-action-button' onClick={() => openLocEvidence(entry)}>
	                                  View
	                                </button>
	                              </span>
	                            </div>
	                          ))}
	                        </div>
	                      ) : (
	                        <p className='empty-state'>No level-of-care history is loaded.</p>
	                      )}
	                    </section>

	                    <section className='panel-subsection'>
	                      <h3>Treatment plan evidence</h3>
	                      {selectedTimelinessClient.treatment_plans.length ? (
	                        <div className='timeliness-table timeliness-table--evidence'>
	                          <div className='timeliness-table__head'>
	                            <span>Type</span>
	                            <span>Source</span>
	                            <span>Document</span>
	                            <span>Staff</span>
	                            <span>Client</span>
	                            <span>Next due</span>
	                            <span>Status</span>
	                            <span>Evidence</span>
	                          </div>
	                          {selectedTimelinessClient.treatment_plans.map((plan) => (
	                            <div key={plan.id} className='timeliness-table__row'>
	                              <span>
	                                <span className={`pill pill--${planKindTone(plan.plan_kind)}`}>{planKindLabel(plan.plan_kind)}</span>
	                              </span>
	                              <span>{plan.source_section || plan.source_evidence || 'Not recorded'}</span>
	                              <span>{plan.document_date || 'Missing'}</span>
	                              <span>{signedLabel(plan.staff_signature_date)}</span>
	                              <span>{plan.client_signature_date || (plan.plan_kind === 'review' ? 'Optional' : 'Missing')}</span>
	                              <span>{plan.displayed_next_due_date || 'Not recorded'}</span>
	                              <span>{plan.is_valid && !plan.conflict_note ? 'Valid' : plan.conflict_note || 'Needs review'}</span>
	                              <span>
	                                <button type='button' className='table-action-button' onClick={() => openPlanEvidence(plan)}>
	                                  View
	                                </button>
	                              </span>
	                            </div>
	                          ))}
	                        </div>
	                      ) : (
	                        <p className='empty-state'>No treatment plan records are loaded.</p>
	                      )}
	                    </section>

	                    {canOverrideTimeliness ? (
	                      <section className='panel-subsection'>
	                        <h3>Manual override</h3>
	                        <form className='form-grid' onSubmit={handleTimelinessOverride}>
	                          <label>
	                            Field
	                            <select
	                              value={timelinessOverrideForm.field_name}
	                              onChange={(event) =>
	                                setTimelinessOverrideForm((current) => ({ ...current, field_name: event.target.value }))
	                              }
	                            >
	                              <option value='status'>Status</option>
	                              <option value='next_due_date'>Next due date</option>
	                              <option value='rule_used'>Rule used</option>
	                            </select>
	                          </label>
	                          <label>
	                            Original value
	                            <input
	                              value={timelinessOverrideForm.original_value}
	                              onChange={(event) => setTimelinessOverrideForm((current) => ({ ...current, original_value: event.target.value }))}
	                            />
	                          </label>
	                          <label>
	                            New value
	                            <input
	                              value={timelinessOverrideForm.new_value}
	                              onChange={(event) => setTimelinessOverrideForm((current) => ({ ...current, new_value: event.target.value }))}
	                            />
	                          </label>
	                          <label>
	                            Affected rule
	                            <input
	                              value={timelinessOverrideForm.affected_rule}
	                              onChange={(event) => setTimelinessOverrideForm((current) => ({ ...current, affected_rule: event.target.value }))}
	                            />
	                          </label>
	                          <label className='full-width'>
	                            Reason
	                            <textarea
	                              value={timelinessOverrideForm.reason}
	                              onChange={(event) => setTimelinessOverrideForm((current) => ({ ...current, reason: event.target.value }))}
	                            />
	                          </label>
	                          <div className='full-width form-actions'>
	                            <button type='submit' disabled={isBusy}>
	                              Save override
	                            </button>
	                          </div>
	                        </form>
	                      </section>
	                    ) : null}

	                    <section className='panel-subsection'>
	                      <h3>Overrides</h3>
	                      {selectedTimelinessClient.overrides.length ? (
	                        <div className='finding-list'>
	                          {selectedTimelinessClient.overrides.map((override) => (
	                            <article key={override.id} className='finding-card'>
	                              <div className='finding-card__header'>
	                                <strong>{override.field_name}</strong>
	                                <span>{formatDateTime(override.created_at)}</span>
	                              </div>
	                              <p>
	                                {override.original_value || 'blank'} to {override.new_value || 'blank'}; {override.reason}
	                              </p>
	                            </article>
	                          ))}
	                        </div>
	                      ) : (
	                        <p className='empty-state'>No manual overrides are recorded.</p>
	                      )}
	                    </section>

	                    <section className='panel-subsection'>
	                      <h3>Audit history</h3>
	                      {selectedTimelinessClient.audit_history.length ? (
	                        <div className='log-table'>
	                          {selectedTimelinessClient.audit_history.slice(0, 6).map((entry) => (
	                            <article key={entry.event_id} className='log-row'>
	                              <div className='log-row__meta'>
	                                <strong>{entry.action}</strong>
	                                <span>{formatDateTime(entry.timestamp_utc)}</span>
	                              </div>
	                              <p>{entry.message}</p>
	                            </article>
	                          ))}
	                        </div>
	                      ) : (
	                        <p className='empty-state'>No timeliness audit history is loaded.</p>
	                      )}
	                    </section>
	                  </>
	                ) : (
	                  <p className='empty-state-block'>Select a treatment-plan client to review rule results, source evidence, and overrides.</p>
	                )}
	              </section>
	            </section>
	          ) : null}

          {activeView === 'checklist' ? (
            <section className='panel detail-panel'>
              <div className='panel-heading'>
                <div>
                  <h2>{treatmentPlanChecklist?.display_name || 'Treatment Plan Checklist Version 1'}</h2>
                  <p>
                    {treatmentPlanChecklist
                      ? `Version ${treatmentPlanChecklist.version} from ${treatmentPlanChecklist.source_of_truth}`
                      : 'Loading canonical checklist...'}
                  </p>
                </div>
                <div className='button-row'>
                  {user?.role === 'admin' ? (
                    <button type='button' className='ghost-button' onClick={() => setActiveView('settings')}>
                      Manage Workflow
                    </button>
                  ) : null}
                  <button type='button' className='ghost-button' onClick={() => void loadTreatmentPlanChecklist()} disabled={isBusy}>
                    Refresh
                  </button>
                </div>
              </div>

              {treatmentPlanChecklist ? (
                <>
                  <section className='panel-subsection'>
                    <h3>Acronym definitions</h3>
                    <div className='acronym-grid'>
                      {treatmentPlanChecklist.acronyms.map((item) => (
                        <article key={item.term} className='mini-card'>
                          <span>{item.term}</span>
                          <strong>{item.definition}</strong>
                          <small>{item.validation_status.replace(/_/g, ' ')}</small>
                        </article>
                      ))}
                    </div>
                  </section>

                  <section className='panel-subsection admin-banner'>
                    <h3>LOC-change blocker</h3>
                    <p>{treatmentPlanChecklist.loc_change_blocker.message}</p>
                  </section>

                  <section className='panel-subsection'>
                    <h3>Review statuses</h3>
                    <div className='status-vocabulary'>
                      {treatmentPlanChecklist.review_statuses.map((status) => (
                        <article key={status.key} className='finding-card'>
                          <div className='finding-card__header'>
                            <strong>{status.label}</strong>
                          </div>
                          <p>{status.description}</p>
                        </article>
                      ))}
                    </div>
                  </section>

                  <section className='panel-subsection'>
                    <h3>Checklist steps</h3>
                    <div className='finding-list'>
                      {treatmentPlanChecklist.steps.map((step) => (
                        <article key={step.key} className='finding-card checklist-step-card'>
                          <div className='finding-card__header'>
                            <div>
                              <strong>
                                Step {step.step}. {step.title}
                              </strong>
                              <p>{step.key}</p>
                            </div>
                            <span className='pill pill--neutral'>{step.severity_default}</span>
                          </div>
                          <p>{step.objective}</p>
                          <dl>
                            <div>
                              <dt>Source modes</dt>
                              <dd>{step.source_modes.join(', ')}</dd>
                            </div>
                            <div>
                              <dt>Automation</dt>
                              <dd>{step.automation_level.replace(/_/g, ' ')}</dd>
                            </div>
                            <div>
                              <dt>Metadata</dt>
                              <dd>{step.required_metadata.length ? step.required_metadata.join(', ') : 'None'}</dd>
                            </div>
                            <div>
                              <dt>Documents</dt>
                              <dd>{step.required_documents.length ? step.required_documents.join(', ') : 'None'}</dd>
                            </div>
                            <div>
                              <dt>Status options</dt>
                              <dd>{step.status_options.join(', ')}</dd>
                            </div>
                            <div>
                              <dt>Reviewer actions</dt>
                              <dd>{step.reviewer_actions.join(', ')}</dd>
                            </div>
                            <div>
                              <dt>Override rule</dt>
                              <dd>{step.manual_override ? 'Manual override allowed; reason required' : 'Manual override not allowed'}</dd>
                            </div>
                            <div>
                              <dt>Audit / export</dt>
                              <dd>
                                {step.audit_event}; exports {step.export_fields.join(', ')}
                              </dd>
                            </div>
                          </dl>
                          <ul className='compact-list'>
                            {step.checks.map((check) => (
                              <li key={check}>{check}</li>
                            ))}
                          </ul>
                        </article>
                      ))}
                    </div>
                  </section>
                </>
              ) : (
                <p className='empty-state-block'>Treatment Plan Checklist Version 1 is loading.</p>
              )}
            </section>
          ) : null}

	          {activeView === 'reviews' ? (
            <section className='workspace-grid'>
              <aside className='panel queue-panel'>
                <div className='panel-heading'>
                  <h2>Automated review queue</h2>
                  <button type='button' className='ghost-button' onClick={() => void loadWorkspace()} disabled={isBusy}>
                    Refresh
                  </button>
                </div>
                {charts.length ? (
                  <ul className='queue-list'>
                    {charts.map((chart) => (
                      <li key={chart.id}>
                        <button
                          type='button'
                          className={selectedChartId === chart.id ? 'queue-item queue-item--active' : 'queue-item'}
                          data-audit-label='Open review queue chart'
                          onClick={() => void loadChartDetail(chart.id)}
                        >
                          <div>
                            <strong>{chart.patient_id}</strong>
                            <span>{chart.primary_clinician || 'Clinician pending'}</span>
                          </div>
                          <div className='queue-item-meta'>
                            <span className={`pill pill--${workflowTone(chart.state)}`}>{chart.state}</span>
                            <span>{chart.system_score}% ready</span>
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className='empty-state'>No review charts yet. Upload a clinical note binder to generate the first automated review.</p>
                )}
              </aside>

              <section className='panel detail-panel'>
                {selectedChart ? (
                  <>
                    <div className='panel-heading'>
                      <div>
                        <h2>Patient {selectedChart.patient_id}</h2>
                        <p>{selectedChart.system_summary}</p>
                      </div>
                      <div className='button-row'>
                        <button type='button' className='ghost-button' onClick={() => exportSelectedChart('csv')}>
                          Export CSV
                        </button>
                        <button type='button' className='ghost-button' onClick={() => exportSelectedChart('json')}>
                          Export JSON
                        </button>
                        <span className={`pill pill--${workflowTone(selectedChart.state)}`}>{selectedChart.state}</span>
                      </div>
                    </div>

                    <div className='detail-grid'>
                      <article className='mini-card'>
                        <span>Primary clinician</span>
                        <strong>{selectedChart.primary_clinician || 'Missing'}</strong>
                      </article>
                      <article className='mini-card'>
                        <span>Level of care</span>
                        <strong>{selectedChart.level_of_care || 'Missing'}</strong>
                      </article>
                      <article className='mini-card'>
                        <span>Admission</span>
                        <strong>{selectedChart.admission_date || 'Missing'}</strong>
                      </article>
                      <article className='mini-card'>
                        <span>System score</span>
                        <strong>{selectedChart.system_score}%</strong>
                      </article>
                    </div>

                    <section className='panel-subsection'>
                      <h3>Open issues</h3>
                      {openItems.length ? (
                        <ul className='issue-list'>
                          {openItems.map((item) => (
                            <li key={item.item_key} className={`issue issue--${checklistTone(item.status)}`}>
                              <div>
                                <strong>{item.label}</strong>
                                <p>{item.notes || item.instructions}</p>
                              </div>
                              <span>{STATUS_LABELS[item.status]}</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className='empty-state'>No open issues detected in the current automated review.</p>
                      )}
                    </section>

                    <section className='panel-subsection'>
                      <h3>Criterion review workbench</h3>
                      <div className='criteria-grid'>
                        <div className='criteria-list'>
                          {selectedChart.checklist_items.map((item) => (
                            <button
                              key={item.item_key}
                              type='button'
                              className={selectedFindingKey === item.item_key ? 'criterion-chip criterion-chip--active' : 'criterion-chip'}
                              onClick={() => setSelectedFindingKey(item.item_key)}
                            >
                              <span>Step {item.step}</span>
                              <strong>{item.label}</strong>
                              <small>{STATUS_LABELS[item.status]}</small>
                            </button>
                          ))}
                        </div>

                        {selectedCriterion ? (
                          <div className='criterion-workbench' ref={criterionWorkbenchRef} tabIndex={-1}>
                            <div className='finding-card__header'>
                              <strong>
                                Step {selectedCriterion.step}. {selectedCriterion.label}
                              </strong>
                              <span className={`pill pill--${checklistTone(selectedCriterion.status)}`}>{STATUS_LABELS[selectedCriterion.status]}</span>
                            </div>
                            <p>{selectedCriterion.instructions}</p>
                            <p className='muted-text'>Evidence hint: {selectedCriterion.evidence_hint}</p>
                            {selectedCriterion.policy_note ? <p className='muted-text'>Policy note: {selectedCriterion.policy_note}</p> : null}

                            <div className='segmented-actions'>
                              <button
                                type='button'
                                className='ghost-button'
                                onClick={() => handleCriterionStatusChange('yes')}
                                aria-disabled={!canEditCriteria}
                              >
                                Mark OK
                              </button>
                              <button
                                type='button'
                                className='ghost-button'
                                onClick={() => handleCriterionStatusChange('no')}
                                aria-disabled={!canEditCriteria}
                              >
                                Mark not OK
                              </button>
                              <button
                                type='button'
                                className='ghost-button'
                                onClick={() => handleCriterionStatusChange('pending')}
                                aria-disabled={!canEditCriteria}
                              >
                                Needs follow-up
                              </button>
                              <button
                                type='button'
                                className='ghost-button'
                                onClick={() => handleCriterionStatusChange('na')}
                                aria-disabled={!canEditCriteria}
                              >
                                N/A
                              </button>
                            </div>

                            <div className='form-grid'>
                              <label className='full-width'>
                                Reviewer notes
                                <textarea
                                  aria-label='Reviewer notes'
                                  value={selectedCriterion.notes}
                                  onChange={(event) => updateSelectedCriterion({ notes: event.target.value })}
                                  disabled={!canEditCriteria}
                                />
                              </label>
                              <label>
                                Evidence location
                                <input
                                  aria-label='Evidence location'
                                  value={selectedCriterion.evidence_location}
                                  onChange={(event) => updateSelectedCriterion({ evidence_location: event.target.value })}
                                  disabled={!canEditCriteria}
                                />
                              </label>
                              <label>
                                Evidence date
                                <input
                                  aria-label='Evidence date'
                                  value={selectedCriterion.evidence_date}
                                  onChange={(event) => updateSelectedCriterion({ evidence_date: event.target.value })}
                                  disabled={!canEditCriteria}
                                />
                              </label>
                              <label>
                                Expiration date
                                <input
                                  aria-label='Expiration date'
                                  value={selectedCriterion.expiration_date}
                                  onChange={(event) => updateSelectedCriterion({ expiration_date: event.target.value })}
                                  disabled={!canEditCriteria}
                                />
                              </label>
                            </div>

                            {canEditCriteria ? (
                              <div className='decision-actions'>
                                <button type='button' onClick={() => void handleSaveReviewChanges()} disabled={isBusy || !reviewDirty}>
                                  Save criterion review changes
                                </button>
                                {reviewDirty ? <span className='muted-text'>Unsaved criterion review changes</span> : null}
                              </div>
                            ) : (
                              <p className='muted-text'>Criterion drill-down is visible to you, but only admins and managers can change the review result.</p>
                            )}
                          </div>
                        ) : null}
                      </div>
                    </section>

                    <section className='panel-subsection'>
                      <h3>Checklist findings</h3>
                      {groupedFindings.map(([section, items]) => (
                        <div key={section} className='finding-group'>
                          <h4>{section}</h4>
                          <div className='finding-list'>
                            {items.map((item) => (
                              <article key={item.item_key} className='finding-card'>
                                <div className='finding-card__header'>
                                  <strong>
                                    Step {item.step}. {item.label}
                                  </strong>
                                  <span className={`pill pill--${checklistTone(item.status)}`}>{STATUS_LABELS[item.status]}</span>
                                </div>
                                <p>{item.notes || item.instructions}</p>
                                <dl>
                                  <div>
                                    <dt>Evidence</dt>
                                    <dd>{item.evidence_location || 'System could not pin a precise location.'}</dd>
                                  </div>
                                  <div>
                                    <dt>Date</dt>
                                    <dd>{item.evidence_date || 'Not detected'}</dd>
                                  </div>
                                  <div>
                                    <dt>Policy note</dt>
                                    <dd>{item.policy_note || 'No extra policy note for this rule.'}</dd>
                                  </div>
                                </dl>
                                <div className='decision-actions'>
                                  <button type='button' className='ghost-button' onClick={() => handleDigDeeper(item)}>
                                    Dig deeper
                                  </button>
                                </div>
                              </article>
                            ))}
                          </div>
                        </div>
                      ))}
                    </section>

                    <section className='panel-subsection'>
                      <h3>Office manager disposition</h3>
                      {selectedChart.manager_comment ? <p className='manager-comment'>{selectedChart.manager_comment}</p> : null}
                      {transitionActions.length ? (
                        <div className='decision-box'>
                          <label>
                            Manager comment
                            <textarea
                              aria-label='Manager comment'
                              value={decisionComment}
                              placeholder='Record final approval context or describe what the counselor needs to fix.'
                              onChange={(event) => setDecisionComment(event.target.value)}
                            />
                          </label>
                          <div className='decision-actions'>
                            {transitionActions.map((action) => (
                              <button key={action.toState} type='button' onClick={() => handleTransitionButton(action)} disabled={isBusy}>
                                {action.label}
                              </button>
                            ))}
                            {reviewDirty ? <span className='muted-text'>Save criterion changes before recording the final decision.</span> : null}
                          </div>
                        </div>
                      ) : user?.role === 'counselor' && selectedChart.state === 'Returned to Counselor' ? (
                        <div className='decision-box'>
                          <p>The office manager returned this chart. Upload a corrected binder version to generate a fresh automated review.</p>
                          <button type='button' onClick={() => openRejectedPatientUpload(selectedChart)}>
                            Upload corrected notes
                          </button>
                        </div>
                      ) : (
                        <p className='empty-state'>No approval action is available for this chart in your current role.</p>
                      )}
                    </section>

                    <section className='panel-subsection'>
                      <h3>Linked note binder</h3>
                      {linkedNoteSet ? (
                        <div className='linked-note'>
                          <p>
                            Version {linkedNoteSet.version} from {formatDateTime(linkedNoteSet.created_at)} with {linkedNoteSet.file_count} file(s).
                          </p>
                          <button type='button' className='ghost-button' onClick={() => void loadNoteSetDetail(linkedNoteSet.id)}>
                            Open binder details
                          </button>
                        </div>
                      ) : (
                        <p className='empty-state'>No uploaded binder is linked to this chart.</p>
                      )}
                    </section>
                  </>
                ) : (
                  <div className='empty-state-block'>
                    <h2>No automated review selected</h2>
                    <p>Upload a binder or choose a chart from the queue to inspect the system findings.</p>
                  </div>
                )}
              </section>
            </section>
          ) : null}

          {activeView === 'uploads' ? (
            <section className='workspace-grid'>
              <section className='panel detail-panel'>
                <h2>Upload clinical notes</h2>
                <p>
                  Manual upload is the primary local workflow. Use the patient ID as the source-of-truth key and add the client name when it is present in the export.
                </p>
                <div className='rule-alert'>
                  <strong>Manual upload is a point-in-time snapshot</strong>
                  <p>
                    Uploaded charts reflect only the files selected here as of upload time. If API automation is unavailable for 60+ active charts, use this as a monthly compliance-check batch workflow rather than a weekly manual refresh expectation.
                  </p>
                </div>
                <form className='form-grid' onSubmit={handleUpload}>
                  <label>
                    Patient ID
                    <input
                      value={uploadForm.patient_id}
                      onChange={(event) => {
                        const nextValue = event.target.value
                        setPatientIdTouched(true)
                        if (nextValue.trim() !== lastAutoFilledPatientId) {
                          setLastAutoFilledPatientId('')
                        }
                        setUploadForm((current) => ({ ...current, patient_id: nextValue }))
                      }}
                    />
                  </label>
                  <label>
                    Client name
                    <input
                      value={uploadForm.client_name}
                      placeholder='Optional, for chart audit context'
                      onChange={(event) => setUploadForm((current) => ({ ...current, client_name: event.target.value }))}
                    />
                  </label>
                  <label>
                    Upload mode
                    <select
                      value={uploadForm.upload_mode}
                      onChange={(event) =>
                        setUploadForm((current) => ({ ...current, upload_mode: event.target.value as NoteSetUploadMode }))
                      }
                    >
                      <option value='initial'>Initial binder</option>
                      <option value='update'>Updated binder</option>
                    </select>
                  </label>
                  <label>
                    Level of care
                    <input value={uploadForm.level_of_care} onChange={(event) => setUploadForm((current) => ({ ...current, level_of_care: event.target.value }))} />
                  </label>
                  <label>
                    Primary clinician
                    <input
                      value={uploadForm.primary_clinician}
                      onChange={(event) => setUploadForm((current) => ({ ...current, primary_clinician: event.target.value }))}
                    />
                  </label>
                  <label>
                    Admission date
                    <input
                      type='date'
                      value={uploadForm.admission_date}
                      onChange={(event) => setUploadForm((current) => ({ ...current, admission_date: event.target.value }))}
                    />
                  </label>
                  <label>
                    Discharge date
                    <input
                      type='date'
                      value={uploadForm.discharge_date}
                      onChange={(event) => setUploadForm((current) => ({ ...current, discharge_date: event.target.value }))}
                    />
                  </label>
                  <label className='full-width'>
                    Upload notes
                    <textarea
                      value={uploadForm.upload_notes}
                      onChange={(event) => setUploadForm((current) => ({ ...current, upload_notes: event.target.value }))}
                    />
                  </label>
                  <label className='full-width'>
                    Clinical note files
                    <input multiple type='file' accept={ACCEPTED_UPLOAD_TYPES} onChange={handleFilesSelected} />
                  </label>
                  {patientIdDetection ? (
                    <div className={`full-width detection-card ${patientIdDetection.patient_id ? 'detection-card--success' : 'detection-card--neutral'}`}>
                      <div>
                        <strong>
                          {patientIdDetection.patient_id
                            ? `Detected patient ID ${patientIdDetection.patient_id}`
                            : 'Patient ID could not be read automatically'}
                        </strong>
                        <p>{patientIdDetection.reason}</p>
                        {patientIdDetection.source_filename ? (
                          <p className='detection-card__meta'>
                            Source: {patientIdDetection.source_filename}
                            {patientIdDetection.confidence !== 'none' ? ` · Confidence: ${patientIdDetection.confidence}` : ''}
                          </p>
                        ) : null}
                      </div>
                      {patientIdDetection.patient_id && uploadForm.patient_id !== patientIdDetection.patient_id ? (
                        <button
                          type='button'
                          className='ghost-button'
                          onClick={() => {
                            setUploadForm((current) => ({ ...current, patient_id: patientIdDetection.patient_id || current.patient_id }))
                            setPatientIdTouched(false)
                            setLastAutoFilledPatientId(patientIdDetection.patient_id || '')
                            setPatientIdDetection((current) => (current ? { ...current, was_autofilled: true } : current))
                          }}
                        >
                          Use detected ID
                        </button>
                      ) : patientIdDetection.was_autofilled ? (
                        <span className='pill pill--success'>Auto-filled</span>
                      ) : null}
                    </div>
                  ) : null}
                  {uploadForm.entries.length ? (
                    <div className='full-width file-editor'>
                      <h3>Binder file metadata</h3>
                      {uploadForm.entries.map((entry, index) => (
                        <article key={`${entry.file.name}-${index}`} className='file-editor-row'>
                          <div className='file-editor-row__title'>
                            <strong>{entry.file.name}</strong>
                            <span>{Math.round(entry.file.size / 1024)} KB</span>
                          </div>
                          <div className='file-editor-row__fields'>
                            <label>
                              Label
                              <input value={entry.document_label} onChange={(event) => updateUploadEntry(index, 'document_label', event.target.value)} />
                            </label>
                            <label>
                              Bucket
                              <select
                                value={entry.alleva_bucket}
                                onChange={(event) => updateUploadEntry(index, 'alleva_bucket', event.target.value as AllevaBucket)}
                              >
                                <option value='custom_forms'>Custom Forms</option>
                                <option value='uploaded_documents'>Uploaded Documents</option>
                                <option value='portal_documents'>Portal Documents</option>
                                <option value='labs'>Labs</option>
                                <option value='medications'>Medications</option>
                                <option value='notes'>Notes</option>
                                <option value='other'>Other</option>
                              </select>
                            </label>
                            <label>
                              Completion
                              <select
                                value={entry.completion_status}
                                onChange={(event) => updateUploadEntry(index, 'completion_status', event.target.value as DocumentCompletionStatus)}
                              >
                                <option value='completed'>Completed</option>
                                <option value='incomplete'>Incomplete</option>
                                <option value='draft'>Draft</option>
                              </select>
                            </label>
                            <label>
                              Document date
                              <input type='date' value={entry.document_date} onChange={(event) => updateUploadEntry(index, 'document_date', event.target.value)} />
                            </label>
                            <label className='checkbox-row'>
                              <input
                                type='checkbox'
                                checked={entry.client_signed}
                                onChange={(event) => updateUploadEntry(index, 'client_signed', event.target.checked)}
                              />
                              Client signed
                            </label>
                            <label className='checkbox-row'>
                              <input
                                type='checkbox'
                                checked={entry.staff_signed}
                                onChange={(event) => updateUploadEntry(index, 'staff_signed', event.target.checked)}
                              />
                              Staff signed
                            </label>
                            <label className='full-width'>
                              Description
                              <input value={entry.description} onChange={(event) => updateUploadEntry(index, 'description', event.target.value)} />
                            </label>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : null}
                  <div className='full-width form-actions'>
                    <button type='submit' disabled={isBusy}>
                      {isBusy ? 'Uploading...' : 'Upload and run automated evaluation'}
                    </button>
                  </div>
                </form>
              </section>

              <aside className='panel queue-panel'>
                <div className='panel-heading'>
                  <h2>Uploaded binders</h2>
                  <button type='button' className='ghost-button' onClick={() => void loadWorkspace()} disabled={isBusy}>
                    Refresh
                  </button>
                </div>
                {noteSets.length ? (
                  <ul className='queue-list'>
                    {noteSets.map((noteSet) => (
                      <li key={noteSet.id}>
                        <button
                          type='button'
                          className={selectedNoteSetId === noteSet.id ? 'queue-item queue-item--active' : 'queue-item'}
                          data-audit-label='Open uploaded binder'
                          onClick={() => void loadNoteSetDetail(noteSet.id)}
                        >
                          <div>
                            <strong>{noteSet.patient_id}</strong>
                            <span>Version {noteSet.version}</span>
                          </div>
                          <div className='queue-item-meta'>
                            <span className='pill pill--neutral'>{NOTE_SET_STATUS_LABELS[noteSet.status]}</span>
                            <span>{noteSet.file_count} files</span>
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className='empty-state'>No clinical note binders have been uploaded yet.</p>
                )}

                {selectedNoteSet ? (
                  <section className='panel-subsection'>
                    <h3>Binder details</h3>
                    <p>
                      Patient {selectedNoteSet.patient_id}, version {selectedNoteSet.version}, uploaded {formatDateTime(selectedNoteSet.created_at)}.
                    </p>
                    <p>{selectedNoteSet.upload_notes || 'No binder notes were entered.'}</p>
                    {selectedNoteSet.review_chart_id ? (
                      <button type='button' onClick={() => void loadChartDetail(selectedNoteSet.review_chart_id!)}>
                        Open automated review
                      </button>
                    ) : null}
                    <div className='document-list'>
                      {selectedNoteSet.documents.map((document) => (
                        <article key={document.id} className='document-card'>
                          <strong>{document.document_label}</strong>
                          <p>{document.original_filename}</p>
                          <p>{document.document_date || 'Date not supplied'}</p>
                          <span>{shortHash(document.sha256)}</span>
                          <button type='button' className='ghost-button' onClick={() => void downloadDocument(selectedNoteSet.id, document)} disabled={isBusy}>
                            Download
                          </button>
                        </article>
                      ))}
                    </div>
                  </section>
                ) : null}
              </aside>
            </section>
          ) : null}

          {activeView === 'profile' ? (
            <section className='workspace-grid'>
              <aside className='panel queue-panel'>
                <section className='panel-subsection'>
                  <h2>My account</h2>
                  <div className='fact-list'>
                    <div>
                      <dt>Username</dt>
                      <dd>{user?.username}</dd>
                    </div>
                    <div>
                      <dt>Role</dt>
                      <dd>{user?.role}</dd>
                    </div>
                    <div>
                      <dt>Last login</dt>
                      <dd>{formatDateTime(user?.last_login_at)}</dd>
                    </div>
                    <div>
                      <dt>Created</dt>
                      <dd>{formatDateTime(user?.created_at)}</dd>
                    </div>
                  </div>
                </section>
              </aside>

              <section className='panel detail-panel'>
                <section className='panel-subsection'>
                  <h2>User profile</h2>
                  <form className='form-grid' onSubmit={handleProfileSave}>
                    <label className='full-width'>
                      Full name
                      <input value={profileForm.full_name} onChange={(event) => setProfileForm({ full_name: event.target.value })} />
                    </label>
                    <div className='full-width form-actions'>
                      <button type='submit' disabled={isBusy}>
                        Save profile
                      </button>
                    </div>
                  </form>
                </section>

                <section className='panel-subsection'>
                  <h3>Change password</h3>
                  {isBootstrapAdmin(user) ? (
                    <p className='muted-text'>The bootstrap admin password is static and managed outside the app.</p>
                  ) : (
                    <form className='form-grid' onSubmit={handlePasswordChange}>
                      <label>
                        Current password
                        <input
                          type='password'
                          value={passwordChangeForm.current_password}
                          onChange={(event) =>
                            setPasswordChangeForm((current) => ({ ...current, current_password: event.target.value }))
                          }
                        />
                      </label>
                      <label>
                        New password
                        <input
                          type='password'
                          value={passwordChangeForm.new_password}
                          onChange={(event) => setPasswordChangeForm((current) => ({ ...current, new_password: event.target.value }))}
                        />
                      </label>
                      <div className='full-width form-actions'>
                        <button type='submit' disabled={isBusy}>
                          Change password
                        </button>
                      </div>
                    </form>
                  )}
                </section>
              </section>
            </section>
          ) : null}

          {activeView === 'users' && user?.role === 'admin' ? (
            <section className='workspace-grid'>
              <aside className='panel queue-panel'>
                <div className='panel-heading'>
                  <div>
                    <h2>User management</h2>
                    <p>Select a user to edit access, reset their password, or delete the account.</p>
                  </div>
                  <button type='button' className='ghost-button' onClick={() => void loadUsers()} disabled={isBusy}>
                    Refresh
                  </button>
                </div>

                <div className='dashboard-metrics'>
                  <article className='mini-card'>
                    <span>Total users</span>
                    <strong>{users.length}</strong>
                  </article>
                  <article className='mini-card'>
                    <span>Active</span>
                    <strong>{activeUserCount}</strong>
                  </article>
                  <article className='mini-card'>
                    <span>Locked</span>
                    <strong>{lockedUserCount}</strong>
                  </article>
                  <article className='mini-card'>
                    <span>Reset required</span>
                    <strong>{resetRequiredCount}</strong>
                  </article>
                </div>

                <div className='filter-row'>
                  <label>
                    Search
                    <input value={userFilters.query} onChange={(event) => setUserFilters((current) => ({ ...current, query: event.target.value }))} />
                  </label>
                  <label>
                    Role
                    <select
                      value={userFilters.role}
                      onChange={(event) => setUserFilters((current) => ({ ...current, role: event.target.value as UserFilters['role'] }))}
                    >
                      <option value='all'>All roles</option>
                      <option value='admin'>Admin</option>
                      <option value='manager'>Office manager</option>
                      <option value='counselor'>Counselor</option>
                    </select>
                  </label>
                </div>

                <ul className='queue-list'>
                  {filteredUsers.map((managedUser) => (
                    <li key={managedUser.id}>
                      <button
                        type='button'
                        className={selectedManagedUserId === managedUser.id ? 'queue-item queue-item--active' : 'queue-item'}
                        data-audit-label='Open managed user'
                        onClick={() => handleSelectManagedUser(managedUser.id)}
                      >
                        <div>
                          <strong>{managedUser.full_name || managedUser.username}</strong>
                          <span>{managedUser.username}</span>
                        </div>
                        <div className='queue-item-meta'>
                          <span className='pill pill--neutral'>{managedUser.role}</span>
                          {managedUser.must_reset_password ? <span className='pill pill--warning'>Reset required</span> : null}
                          <span className={`pill pill--${userStatusTone(managedUser)}`}>{userStatusLabel(managedUser)}</span>
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              </aside>

              <section className='panel detail-panel'>
                <section className='panel-subsection'>
                  <h2>Manage selected user</h2>
                  <p className='muted-text'>The selected user can be edited below. New accounts sign in with the temporary password once, then must choose a new password.</p>

                  {selectedManagedUser && managedUserForm ? (
                    <>
                      <article className='finding-card'>
                        <div className='finding-card__header'>
                          <div>
                            <strong>{selectedManagedUser.full_name || selectedManagedUser.username}</strong>
                            <p>{selectedManagedUser.username}</p>
                          </div>
                          <div className='quick-actions'>
                            <span className='pill pill--neutral'>{selectedManagedUser.role}</span>
                            {selectedManagedUser.must_reset_password ? <span className='pill pill--warning'>Reset required</span> : null}
                            <span className={`pill pill--${userStatusTone(selectedManagedUser)}`}>{userStatusLabel(selectedManagedUser)}</span>
                          </div>
                        </div>
                        <dl className='detail-grid'>
                          <div>
                            <dt>Last login</dt>
                            <dd>{formatDateTime(selectedManagedUser.last_login_at)}</dd>
                          </div>
                          <div>
                            <dt>Created</dt>
                            <dd>{formatDateTime(selectedManagedUser.created_at)}</dd>
                          </div>
                          <div>
                            <dt>Editable role</dt>
                            <dd>{selectedManagedUserIsBootstrap ? 'Bootstrap admin is fixed' : 'Yes'}</dd>
                          </div>
                          <div>
                            <dt>Deletion</dt>
                            <dd>
                              {selectedManagedUserCanDelete
                                ? 'Available when no historical records are attached'
                                : selectedManagedUserIsBootstrap
                                  ? 'Bootstrap admin cannot be deleted'
                                  : 'You cannot delete the signed-in account'}
                            </dd>
                          </div>
                        </dl>
                      </article>

                      <form className='form-grid' onSubmit={handleSaveManagedUser}>
                        <label>
                          Full name
                          <input
                            value={managedUserForm.full_name}
                            onChange={(event) => setManagedUserForm((current) => (current ? { ...current, full_name: event.target.value } : current))}
                          />
                        </label>
                        <label>
                          Role
                          <select
                            value={managedUserForm.role}
                            disabled={isBusy || selectedManagedUserIsBootstrap}
                            onChange={(event) =>
                              setManagedUserForm((current) => (current ? { ...current, role: event.target.value as Role } : current))
                            }
                          >
                            <option value='counselor'>Counselor</option>
                            <option value='manager'>Office manager</option>
                            <option value='admin'>Admin</option>
                          </select>
                        </label>
                        <label className='checkbox-row'>
                          <input
                            type='checkbox'
                            checked={managedUserForm.is_active}
                            disabled={isBusy || selectedManagedUserIsBootstrap}
                            onChange={(event) =>
                              setManagedUserForm((current) => (current ? { ...current, is_active: event.target.checked } : current))
                            }
                          />
                          Active
                        </label>
                        <label className='checkbox-row'>
                          <input
                            type='checkbox'
                            checked={managedUserForm.is_locked}
                            disabled={isBusy || selectedManagedUserIsBootstrap}
                            onChange={(event) =>
                              setManagedUserForm((current) => (current ? { ...current, is_locked: event.target.checked } : current))
                            }
                          />
                          Locked
                        </label>
                        <label className='checkbox-row'>
                          <input
                            type='checkbox'
                            checked={managedUserForm.must_reset_password}
                            disabled={isBusy || selectedManagedUserIsBootstrap}
                            onChange={(event) =>
                              setManagedUserForm((current) => (current ? { ...current, must_reset_password: event.target.checked } : current))
                            }
                          />
                          Force password reset at next login
                        </label>
                        <div className='full-width form-actions'>
                          <button type='submit' disabled={isBusy}>
                            Save selected user
                          </button>
                        </div>
                      </form>

                      <section className='panel-subsection'>
                        <h3>Admin password reset</h3>
                        {selectedManagedUserIsBootstrap ? (
                          <p className='muted-text'>The bootstrap admin password is fixed outside the app.</p>
                        ) : (
                          <form className='form-grid' onSubmit={handleAdminPasswordReset}>
                            <label className='full-width'>
                              New temporary password
                              <input
                                type='password'
                                minLength={12}
                                value={adminPasswordReset}
                                onChange={(event) => setAdminPasswordReset(event.target.value)}
                              />
                            </label>
                            <div className='full-width form-actions'>
                              <button type='submit' disabled={isBusy}>
                                Reset password and require login reset
                              </button>
                            </div>
                          </form>
                        )}
                      </section>

                      <section className='panel-subsection'>
                        <h3>Delete user</h3>
                        {selectedManagedUserCanDelete ? (
                          <form className='form-grid' onSubmit={handleDeleteManagedUser}>
                            <label className='full-width'>
                              Type username to confirm
                              <input
                                value={deleteUserConfirmation}
                                onChange={(event) => setDeleteUserConfirmation(event.target.value)}
                                placeholder={selectedManagedUser.username}
                              />
                            </label>
                            <div className='full-width form-actions'>
                              <button type='submit' className='danger-button' disabled={isBusy || deleteUserConfirmation.trim() !== selectedManagedUser.username}>
                                Delete user
                              </button>
                            </div>
                            <p className='muted-text'>
                              Deletion is permanent and only works when the account has no linked charts, uploads, workflow history, or audit trail.
                            </p>
                          </form>
                        ) : (
                          <p className='muted-text'>
                            {selectedManagedUserIsBootstrap
                              ? 'The bootstrap admin account cannot be deleted.'
                              : 'The signed-in admin account cannot delete itself.'}
                          </p>
                        )}
                      </section>
                    </>
                  ) : (
                    <p className='empty-state'>Select a user to edit details, reset a password, or delete the account.</p>
                  )}
                </section>

                <section className='panel-subsection'>
                  <h2>Create user</h2>
                  <p className='muted-text'>Create a managed user account with a temporary password of at least 12 characters. The user will be prompted to reset it after the first sign-in.</p>
                  <form className='form-grid' onSubmit={handleCreateUser}>
                    <label>
                      Username
                      <input
                        required
                        value={newUserForm.username}
                        onChange={(event) => setNewUserForm((current) => ({ ...current, username: event.target.value }))}
                      />
                    </label>
                    <label>
                      Full name
                      <input
                        value={newUserForm.full_name}
                        onChange={(event) => setNewUserForm((current) => ({ ...current, full_name: event.target.value }))}
                      />
                    </label>
                    <label>
                      Role
                      <select value={newUserForm.role} onChange={(event) => setNewUserForm((current) => ({ ...current, role: event.target.value as Role }))}>
                        <option value='counselor'>Counselor</option>
                        <option value='manager'>Office manager</option>
                        <option value='admin'>Admin</option>
                      </select>
                    </label>
                    <label>
                      Temporary password
                      <input
                        type='password'
                        minLength={12}
                        required
                        autoComplete='new-password'
                        value={newUserForm.password}
                        onChange={(event) => setNewUserForm((current) => ({ ...current, password: event.target.value }))}
                      />
                    </label>
                    <div className='full-width form-actions'>
                      <button type='submit' disabled={isBusy}>
                        Create user
                      </button>
                    </div>
                  </form>
                </section>
              </section>
            </section>
          ) : null}

          {activeView === 'settings' && user?.role === 'admin' ? (
            <section className='workspace-grid'>
              <aside className='panel queue-panel'>
                <div className='panel-heading'>
                  <div>
                    <h2>Application settings</h2>
                    <p>Configure external access intelligence and the LLM used for gap-filling analysis.</p>
                  </div>
                  <button type='button' className='ghost-button' onClick={() => void loadSettings()} disabled={isBusy}>
                    Refresh
                  </button>
                </div>

                <div className='fact-list'>
                  <div>
                    <dt>Organization</dt>
                    <dd>{appSettings?.organization_name || 'Not configured'}</dd>
                  </div>
                  <div>
                    <dt>Timezone</dt>
                    <dd>{appSettings?.effective_timezone_label || 'Local machine timezone'}</dd>
                  </div>
                  <div>
                    <dt>LLM configured</dt>
                    <dd>{appSettings?.llm_api_key_configured ? 'Yes' : 'No'}</dd>
                  </div>
                  <div>
                    <dt>Reputation API configured</dt>
                    <dd>{appSettings?.access_reputation_api_key_configured ? 'Yes' : 'No'}</dd>
                  </div>
                  <div>
                    <dt>Updated</dt>
                    <dd>{formatDateTime(appSettings?.updated_at)}</dd>
                  </div>
                  <div>
                    <dt>EMR API</dt>
                    <dd>{appSettings?.emr_api_enabled ? 'Enabled' : 'Stub configured only'}</dd>
                  </div>
	                  <div>
	                    <dt>Runtime readiness</dt>
	                    <dd>{readiness ? `${readiness.status} (${readiness.failed} failed, ${readiness.warnings} warnings)` : 'Not loaded'}</dd>
	                  </div>
	                  <div>
	                    <dt>LOC-change window</dt>
	                    <dd>
	                      {appSettings?.treatment_plan_loc_change_window_days == null
	                        ? 'Not set'
	                        : `${appSettings.treatment_plan_loc_change_window_days} days`}{' '}
	                      ({appSettings?.treatment_plan_loc_change_window_validated ? 'validated' : 'unvalidated'})
	                    </dd>
	                  </div>
	                </div>
	              </aside>

              <section className='panel detail-panel'>
                {settingsForm ? (
                  <>
                    <form className='form-grid' onSubmit={handleSettingsSave}>
	                    <label className='full-width'>
	                      Organization name
	                      <input
	                        value={settingsForm.organization_name}
	                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, organization_name: event.target.value } : current))}
	                      />
	                    </label>
                    <label>
                      Facility/app timezone
                      <input
                        value={settingsForm.facility_timezone}
                        placeholder='local_machine or America/New_York'
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, facility_timezone: event.target.value } : current))}
                      />
                    </label>
                    <div className='field-action-row'>
                      <button
                        type='button'
                        className='ghost-button'
                        onClick={() => setSettingsForm((current) => (current ? { ...current, facility_timezone: deviceTimezone() } : current))}
                      >
                        Use this device timezone
                      </button>
                      <span className='muted-text'>{appSettings?.effective_timezone_label || 'Local machine timezone'}</span>
                    </div>
	                    <label>
	                      LOC-change update window (days)
	                      <input
	                        type='number'
	                        min={0}
	                        max={365}
	                        value={settingsForm.treatment_plan_loc_change_window_days ?? ''}
	                        onChange={(event) =>
	                          setSettingsForm((current) =>
	                            current
	                              ? {
	                                  ...current,
	                                  treatment_plan_loc_change_window_days: event.target.value === '' ? null : Number(event.target.value),
	                                }
	                              : current,
	                          )
	                        }
	                      />
	                    </label>
	                    <label className='checkbox-row'>
	                      <input
	                        type='checkbox'
	                        checked={settingsForm.treatment_plan_loc_change_window_validated}
	                        onChange={(event) =>
	                          setSettingsForm((current) =>
	                            current ? { ...current, treatment_plan_loc_change_window_validated: event.target.checked } : current
	                          )
	                        }
	                      />
	                      R3/Marleigh validated LOC-change window
	                    </label>
	                    {!settingsForm.treatment_plan_loc_change_window_validated ? (
	                      <p className='muted-text full-width'>LOC-change treatment plan update timing remains unvalidated.</p>
	                    ) : null}
	                    <label className='checkbox-row'>
	                      <input
                        type='checkbox'
                        checked={settingsForm.access_intel_enabled}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, access_intel_enabled: event.target.checked } : current))
                        }
                      />
                      Enable access intelligence lookups
                    </label>
                    <label>
                      Geolocation URL
                      <input
                        value={settingsForm.access_geo_lookup_url}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, access_geo_lookup_url: event.target.value } : current))
                        }
                      />
                    </label>
                    <label>
                      Reputation URL
                      <input
                        value={settingsForm.access_reputation_url}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, access_reputation_url: event.target.value } : current))
                        }
                      />
                    </label>
                    <label>
                      Reputation API key
                      <input
                        type='password'
                        autoComplete='off'
                        value={settingsForm.access_reputation_api_key}
                        placeholder={appSettings?.access_reputation_api_key_configured ? 'Configured. Enter a new key to replace it.' : 'Optional'}
                        onChange={(event) =>
                          setSettingsForm((current) =>
                            current
                              ? {
                                  ...current,
                                  access_reputation_api_key: event.target.value,
                                  clear_access_reputation_api_key: false,
                                }
                              : current,
                          )
                        }
                      />
                    </label>
                    <label className='checkbox-row'>
                      <input
                        type='checkbox'
                        checked={settingsForm.clear_access_reputation_api_key}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, clear_access_reputation_api_key: event.target.checked } : current))
                        }
                      />
                      Clear stored reputation API key
                    </label>
                    <label>
                      Lookup timeout (seconds)
                      <input
                        type='number'
                        min={1}
                        max={30}
                        value={settingsForm.access_lookup_timeout_seconds}
                        onChange={(event) =>
                          setSettingsForm((current) =>
                            current ? { ...current, access_lookup_timeout_seconds: Number(event.target.value || 1) } : current
                          )
                        }
                      />
                    </label>

                    <label className='checkbox-row'>
                      <input
                        type='checkbox'
                        checked={settingsForm.llm_enabled}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, llm_enabled: event.target.checked } : current))}
                      />
                      Enable LLM-assisted analysis
                    </label>
                    <label>
                      LLM provider label
                      <input
                        value={settingsForm.llm_provider_name}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, llm_provider_name: event.target.value } : current))
                        }
                      />
                    </label>
                    <label>
                      LLM base URL
                      <input
                        value={settingsForm.llm_base_url}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, llm_base_url: event.target.value } : current))}
                      />
                    </label>
                    <label>
                      LLM model
                      <input
                        value={settingsForm.llm_model}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, llm_model: event.target.value } : current))}
                      />
                    </label>
                    <label>
                      LLM API key
                      <input
                        type='password'
                        autoComplete='off'
                        value={settingsForm.llm_api_key}
                        placeholder={appSettings?.llm_api_key_configured ? 'Configured. Enter a new key to replace it.' : 'Required to enable LLM analysis'}
                        onChange={(event) =>
                          setSettingsForm((current) =>
                            current
                              ? {
                                  ...current,
                                  llm_api_key: event.target.value,
                                  clear_llm_api_key: false,
                                }
                              : current,
                          )
                        }
                      />
                    </label>
                    <label className='checkbox-row'>
                      <input
                        type='checkbox'
                        checked={settingsForm.clear_llm_api_key}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, clear_llm_api_key: event.target.checked } : current))}
                      />
                      Clear stored LLM API key
                    </label>
                    <label className='checkbox-row'>
                      <input
                        type='checkbox'
                        checked={settingsForm.llm_use_for_access_review}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, llm_use_for_access_review: event.target.checked } : current))
                        }
                      />
                      Use LLM for dangerous-IP access summaries
                    </label>
                    <label className='checkbox-row'>
                      <input
                        type='checkbox'
                        checked={settingsForm.llm_use_for_evaluation_gap_analysis}
                        onChange={(event) =>
                          setSettingsForm((current) =>
                            current ? { ...current, llm_use_for_evaluation_gap_analysis: event.target.checked } : current
                          )
                        }
                      />
                      Use LLM to fill note-analysis gaps
                    </label>
                    <label className='full-width'>
                      Analysis instructions
                      <textarea
                        value={settingsForm.llm_analysis_instructions}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, llm_analysis_instructions: event.target.value } : current))
                        }
                      />
                    </label>
                    <label className='checkbox-row full-width'>
                      <input
                        type='checkbox'
                        checked={settingsForm.emr_api_enabled}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, emr_api_enabled: event.target.checked } : current))}
                      />
                      Enable EMR API connector
                    </label>
                    <label>
                      EMR vendor label
                      <input
                        value={settingsForm.emr_vendor_name}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, emr_vendor_name: event.target.value } : current))}
                      />
                    </label>
                    <label>
                      FHIR base URL
                      <input
                        value={settingsForm.emr_fhir_base_url}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, emr_fhir_base_url: event.target.value } : current))}
                      />
                    </label>
                    <label className='full-width'>
                      SMART token URL
                      <input
                        value={settingsForm.emr_smart_token_url}
                        placeholder='https://authorization.allevasoft.com/connect/token'
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, emr_smart_token_url: event.target.value } : current))}
                      />
                    </label>
                    <label>
                      SMART client ID
                      <input
                        value={settingsForm.emr_smart_client_id}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, emr_smart_client_id: event.target.value } : current))}
                      />
                    </label>
                    <label>
                      SMART client secret
                      <input
                        type='password'
                        autoComplete='off'
                        value={settingsForm.emr_smart_client_secret}
                        placeholder={appSettings?.emr_smart_client_secret_configured ? 'Configured. Enter a new secret to replace it.' : 'Optional until EMR registration'}
                        onChange={(event) =>
                          setSettingsForm((current) =>
                            current
                              ? {
                                  ...current,
                                  emr_smart_client_secret: event.target.value,
                                  clear_emr_smart_client_secret: false,
                                }
                              : current,
                          )
                        }
                      />
                    </label>
                    <label className='checkbox-row'>
                      <input
                        type='checkbox'
                        checked={settingsForm.clear_emr_smart_client_secret}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, clear_emr_smart_client_secret: event.target.checked } : current))
                        }
                      />
                      Clear stored SMART client secret
                    </label>
                    <label className='full-width'>
                      SMART scopes
                      <input
                        value={settingsForm.emr_smart_scopes}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, emr_smart_scopes: event.target.value } : current))}
                      />
                    </label>
                    <label>
                      EMR timeout (seconds)
                      <input
                        type='number'
                        min={1}
                        max={60}
                        value={settingsForm.emr_api_timeout_seconds}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, emr_api_timeout_seconds: Number(event.target.value || 1) } : current))
                        }
                      />
                    </label>
                    <section className='panel-subsection full-width'>
                      <h3>Alleva import profile</h3>
                      <div className='fact-list'>
                        <div>
                          <dt>Adapter</dt>
                          <dd>{emrProfile?.adapter_key || 'Not loaded'}</dd>
                        </div>
                        <div>
                          <dt>Live import</dt>
                          <dd>{emrProfile?.live_import_status || 'Not configured'}</dd>
                        </div>
                        <div>
                          <dt>Export formats</dt>
                          <dd>{emrProfile?.supported_export_formats.join(', ') || 'Not loaded'}</dd>
                        </div>
                        <div>
                          <dt>Document sections</dt>
                          <dd>{emrProfile?.document_manager_sections.map((section) => section.label).join(', ') || 'Not loaded'}</dd>
                        </div>
                      </div>
                      <div className='form-actions'>
                        <button type='button' className='ghost-button' onClick={handleEmrDiscovery} disabled={isBusy}>
                          Check SMART discovery
                        </button>
                      </div>
                      {emrDiscovery ? (
                        <p className='muted-text'>
                          Discovery: {emrDiscovery.status}; auth endpoint {emrDiscovery.authorization_endpoint_configured ? 'found' : 'missing'}, token endpoint{' '}
                          {emrDiscovery.token_endpoint_configured ? 'found' : 'missing'}.
                        </p>
                      ) : null}
                      <div className='filter-row'>
                        <label>
                          Import plan patient ID
                          <input value={emrPlanPatientId} onChange={(event) => setEmrPlanPatientId(event.target.value)} />
                        </label>
                        <button type='button' className='ghost-button' onClick={handleEmrImportPlan} disabled={isBusy}>
                          Build import plan
                        </button>
                      </div>
                      {emrImportPlan ? (
                        <ol className='compact-list'>
                          {emrImportPlan.planned_requests.map((request) => (
                            <li key={request.step}>
                              <strong>{request.method}</strong> {request.url}
                            </li>
                          ))}
                        </ol>
                      ) : null}
                    </section>
                    <div className='full-width form-actions'>
                      <button type='submit' disabled={isBusy}>
                        Save settings
                      </button>
                      <button type='button' className='ghost-button' onClick={() => void loadReadiness()} disabled={isBusy}>
                        Recheck readiness
                      </button>
                    </div>
	                  </form>
                    <section className='panel-subsection workflow-admin-panel'>
                      <div className='panel-heading'>
                        <div>
                          <h3>Workflow profiles</h3>
                          <p>Versioned clinical workflow definitions and transition rules.</p>
                        </div>
                        <button type='button' className='ghost-button' onClick={() => void loadWorkflowDefinitions(selectedWorkflowDefinitionId)} disabled={isBusy}>
                          Refresh profiles
                        </button>
                      </div>

                      <div className='dashboard-metrics'>
                        <article className='mini-card'>
                          <span>Workflow profiles</span>
                          <strong>{workflowDefinitions.length}</strong>
                        </article>
                        <article className='mini-card'>
                          <span>Active profiles</span>
                          <strong>{activeWorkflowDefinitionCount}</strong>
                        </article>
                        <article className='mini-card'>
                          <span>Draft versions</span>
                          <strong>{draftWorkflowVersionCount}</strong>
                        </article>
                      </div>

                      <div className='workflow-admin-grid'>
                        <section className='panel-subsection'>
                          <h4>Profiles</h4>
                          {workflowDefinitions.length ? (
                            <div className='queue-list'>
                              {workflowDefinitions.map((definition) => (
                                <button
                                  type='button'
                                  key={definition.id}
                                  className={selectedWorkflowDefinition?.id === definition.id ? 'queue-item queue-item--active' : 'queue-item'}
                                  data-audit-label='Open workflow profile'
                                  onClick={() => {
                                    setSelectedWorkflowDefinitionId(definition.id)
                                    setWorkflowVersionForm(createWorkflowVersionForm(definition))
                                  }}
                                >
                                  <div>
                                    <strong>{definition.display_name}</strong>
                                    <span>{definition.workflow_key}</span>
                                  </div>
                                  <div className='queue-item-meta'>
                                    <span className={`pill pill--${definition.is_active ? 'success' : 'neutral'}`}>
                                      {definition.is_active ? 'active' : 'archived'}
                                    </span>
                                    <span>{definition.current_version ? `v${definition.current_version.version}` : 'no published version'}</span>
                                  </div>
                                </button>
                              ))}
                            </div>
                          ) : (
                            <p className='empty-state'>No workflow profiles are configured.</p>
                          )}
                        </section>

                        <section className='panel-subsection'>
                          <h4>{selectedWorkflowDefinition?.display_name || 'Selected profile'}</h4>
                          {selectedWorkflowDefinition ? (
                            <>
                              <div className='fact-list'>
                                <div>
                                  <dt>Category</dt>
                                  <dd>{selectedWorkflowDefinition.category}</dd>
                                </div>
                                <div>
                                  <dt>Current version</dt>
                                  <dd>{selectedWorkflowDefinition.current_version ? `Version ${selectedWorkflowDefinition.current_version.version}` : 'Draft only'}</dd>
                                </div>
                                <div>
                                  <dt>Updated</dt>
                                  <dd>{formatDateTime(selectedWorkflowDefinition.updated_at)}</dd>
                                </div>
                              </div>
                              <div className='timeliness-table timeliness-table--workflow'>
                                <div className='timeliness-table__head'>
                                  <span>Version</span>
                                  <span>Status</span>
                                  <span>Notes</span>
                                  <span>Action</span>
                                </div>
                                {selectedWorkflowDefinition.versions.map((version) => (
                                  <div key={version.id} className='timeliness-table__row'>
                                    <span>v{version.version}</span>
                                    <span>
                                      <span className={`pill pill--${workflowVersionTone(version.status)}`}>{version.status}</span>
                                    </span>
                                    <span>{version.version_notes || 'No notes'}</span>
                                    <span>
                                      {version.status === 'draft' ? (
                                        <button type='button' className='ghost-button' onClick={() => void publishWorkflowVersion(version.id)} disabled={isBusy}>
                                          Publish
                                        </button>
                                      ) : (
                                        formatDateTime(version.published_at || version.archived_at)
                                      )}
                                    </span>
                                  </div>
                                ))}
                              </div>
                              <div className='form-actions'>
                                <button type='button' className='danger-button' onClick={() => void archiveWorkflowDefinition()} disabled={isBusy || !selectedWorkflowDefinition.is_active}>
                                  Archive profile
                                </button>
                                <button
                                  type='button'
                                  className='ghost-button'
                                  onClick={() => void deleteWorkflowDefinition()}
                                  disabled={isBusy || !selectedWorkflowDefinitionCanDelete}
                                >
                                  Delete unused draft
                                </button>
                              </div>
                            </>
                          ) : (
                            <p className='empty-state'>Select or create a workflow profile.</p>
                          )}
                        </section>
                      </div>

                      <section className='panel-subsection'>
                        <h4>Create workflow profile</h4>
                        <form className='form-grid' onSubmit={handleWorkflowDefinitionCreate}>
                          <label>
                            Workflow key
                            <input
                              required
                              pattern='[a-z0-9][a-z0-9_-]*'
                              value={workflowDefinitionForm.workflow_key}
                              onChange={(event) => setWorkflowDefinitionForm((current) => ({ ...current, workflow_key: event.target.value }))}
                            />
                          </label>
                          <label>
                            Display name
                            <input
                              required
                              value={workflowDefinitionForm.display_name}
                              onChange={(event) => setWorkflowDefinitionForm((current) => ({ ...current, display_name: event.target.value }))}
                            />
                          </label>
                          <label>
                            Category
                            <input
                              value={workflowDefinitionForm.category}
                              onChange={(event) => setWorkflowDefinitionForm((current) => ({ ...current, category: event.target.value }))}
                            />
                          </label>
                          <label>
                            Version notes
                            <input
                              value={workflowDefinitionForm.version_notes}
                              onChange={(event) => setWorkflowDefinitionForm((current) => ({ ...current, version_notes: event.target.value }))}
                            />
                          </label>
                          <label className='full-width'>
                            Description
                            <textarea
                              value={workflowDefinitionForm.description}
                              onChange={(event) => setWorkflowDefinitionForm((current) => ({ ...current, description: event.target.value }))}
                            />
                          </label>
                          <label className='full-width'>
                            Definition JSON
                            <textarea
                              className='code-textarea'
                              value={workflowDefinitionForm.definition_snapshot_text}
                              onChange={(event) => setWorkflowDefinitionForm((current) => ({ ...current, definition_snapshot_text: event.target.value }))}
                            />
                          </label>
                          <label className='full-width'>
                            Transition rules JSON
                            <textarea
                              className='code-textarea'
                              value={workflowDefinitionForm.transition_rules_text}
                              onChange={(event) => setWorkflowDefinitionForm((current) => ({ ...current, transition_rules_text: event.target.value }))}
                            />
                          </label>
                          <div className='full-width form-actions'>
                            <button type='submit' disabled={isBusy}>
                              Create profile
                            </button>
                          </div>
                        </form>
                      </section>

                      {selectedWorkflowDefinition ? (
                        <section className='panel-subsection'>
                          <h4>Create draft version</h4>
                          <div className='rule-alert'>
                            <strong>Admin-editable checklist workflow</strong>
                            <p>
                              Seed a draft from the canonical 42-step checklist, adjust the workflow JSON for R3 operations, create the draft, then publish it when approved.
                            </p>
                            <div className='form-actions'>
                              <button type='button' className='ghost-button' onClick={() => void seedWorkflowDraftFromCanonicalChecklist()} disabled={isBusy}>
                                Seed draft from 42-step checklist
                              </button>
                            </div>
                          </div>
                          <form className='form-grid' onSubmit={handleWorkflowVersionCreate}>
                            <label className='full-width'>
                              Version notes
                              <input
                                value={workflowVersionForm.version_notes}
                                onChange={(event) => setWorkflowVersionForm((current) => ({ ...current, version_notes: event.target.value }))}
                              />
                            </label>
                            <label className='full-width'>
                              Definition JSON
                              <textarea
                                className='code-textarea'
                                value={workflowVersionForm.definition_snapshot_text}
                                onChange={(event) => setWorkflowVersionForm((current) => ({ ...current, definition_snapshot_text: event.target.value }))}
                              />
                            </label>
                            <label className='full-width'>
                              Transition rules JSON
                              <textarea
                                className='code-textarea'
                                value={workflowVersionForm.transition_rules_text}
                                onChange={(event) => setWorkflowVersionForm((current) => ({ ...current, transition_rules_text: event.target.value }))}
                              />
                            </label>
                            <div className='full-width form-actions'>
                              <button type='submit' disabled={isBusy}>
                                Create draft version
                              </button>
                            </div>
                          </form>
                        </section>
                      ) : null}
                    </section>
                  </>
                ) : (
                  <p className='empty-state'>Settings are loading.</p>
                )}
              </section>
            </section>
          ) : null}

          {activeView === 'logs' && user?.role === 'admin' ? (
            <section className='panel detail-panel'>
              <div className='panel-heading'>
                <div>
                  <h2>Forensic audit logs</h2>
                  <p>Admin-only access to request, data-change, access-attempt, workflow, and upload events.</p>
                </div>
                <button type='button' className='ghost-button' onClick={() => void loadLogs()} disabled={isBusy}>
                  Refresh
                </button>
              </div>

              <div className='dashboard-metrics'>
                <article className='mini-card'>
                  <span>Access attempts loaded</span>
                  <strong>{accessAttemptLogs.length}</strong>
                </article>
                <article className='mini-card'>
                  <span>Total logs loaded</span>
                  <strong>{logs.length}</strong>
                </article>
              </div>

              <form
                className='filter-row'
                onSubmit={(event) => {
                  event.preventDefault()
                  void loadLogs()
                }}
              >
                <label>
                  Patient ID
                  <input value={logFilters.patient_id} onChange={(event) => setLogFilters((current) => ({ ...current, patient_id: event.target.value }))} />
                </label>
                <label>
                  Action
                  <input value={logFilters.action} onChange={(event) => setLogFilters((current) => ({ ...current, action: event.target.value }))} />
                </label>
                <label>
                  Category
                  <select
                    value={logFilters.event_category}
                    onChange={(event) => setLogFilters((current) => ({ ...current, event_category: event.target.value }))}
                  >
                    <option value=''>All categories</option>
                    <option value='access_attempt'>Access attempts</option>
                    <option value='data_change'>Data changes</option>
                    <option value='forensic_access'>Forensic access</option>
                    <option value='http_request'>HTTP requests</option>
                    <option value='workflow'>Workflow</option>
                  </select>
                </label>
                <button type='submit' disabled={isBusy}>
                  Filter logs
                </button>
              </form>

              {logs.length ? (
                <div className='log-table'>
                  {logs.map((log) => {
                    const details = parseLogDetails(log.details)
                    const geolocation = details.geolocation as Record<string, unknown> | undefined
                    return (
                      <article key={log.event_id} className='log-row'>
                        <div className='log-row__meta'>
                          <strong>{log.action}</strong>
                          <span>{formatLogDateTime(log)}</span>
                        </div>
                        <p>{log.message}</p>
                        {log.event_category === 'access_attempt' && typeof details.danger_summary === 'string' ? (
                          <p className='muted-text'>
                            {details.danger_summary}
                            {typeof geolocation?.city === 'string' || typeof geolocation?.country === 'string'
                              ? ` Location: ${[geolocation?.city, geolocation?.region, geolocation?.country].filter(Boolean).join(', ')}.`
                              : ''}
                          </p>
                        ) : null}
                        <div className='log-row__details'>
                          <span>Actor: {log.actor_username || log.actor_type}</span>
                          <span>Patient: {log.patient_id || 'n/a'}</span>
                          <span>IP: {log.source_ip || 'n/a'}</span>
                          <span>Request: {log.request_id}</span>
                          <span>{log.event_category}</span>
                          <span className={`pill pill--${log.outcome_status === 'success' ? 'success' : 'danger'}`}>{log.outcome_status}</span>
                        </div>
                      </article>
                    )
                  })}
                </div>
              ) : (
                <p className='empty-state'>No audit logs matched the current filters.</p>
              )}
            </section>
          ) : null}
        </>
      )}

      {evidencePreview ? (
        <div className='modal-backdrop' role='presentation'>
          <section className='evidence-modal' role='dialog' aria-modal='true' aria-labelledby='evidence-modal-title'>
            <div className='modal-title-row'>
              <div>
                <h2 id='evidence-modal-title'>{evidencePreview.title}</h2>
                <p>{evidencePreview.subtitle}</p>
              </div>
              <button type='button' className='ghost-button' onClick={() => setEvidencePreview(null)}>
                Close
              </button>
            </div>
            <div className='evidence-modal__body'>
              {evidencePreview.fields.map((field) => (
                <div key={field.label} className={field.emphasis ? 'evidence-field evidence-field--emphasis' : 'evidence-field'}>
                  <span>{field.label}</span>
                  <strong>{field.value}</strong>
                </div>
              ))}
            </div>
            <div className='rule-alert'>
              <strong>Source note</strong>
              <p>{evidencePreview.note}</p>
            </div>
          </section>
        </div>
      ) : null}

      {appDialog ? (
        <div className='modal-backdrop' role='presentation'>
          <section className='app-dialog' role='dialog' aria-modal='true' aria-labelledby='app-dialog-title'>
            <h2 id='app-dialog-title'>{appDialog.title}</h2>
            <p>{appDialog.message}</p>
            <div className='form-actions'>
              <button type='button' onClick={() => setAppDialog(null)}>
                OK
              </button>
            </div>
          </section>
        </div>
      ) : null}

      <footer className='app-footer' aria-label='Application version'>
        <span>IZ Clinical Notes Analyzer</span>
        <span>{versionLabel}</span>
      </footer>
    </main>
  )
}

export default App
