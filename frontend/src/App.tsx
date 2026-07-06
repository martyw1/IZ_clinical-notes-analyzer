import { ChangeEvent, FormEvent, MouseEvent, useEffect, useMemo, useRef, useState } from 'react'
import {
  AppDialogModal,
  ConfirmDialogModal,
  UploadProgressPanel,
  type AppDialogState,
  type ConfirmDialogState,
  type UploadProgressState,
} from './components/feedback'
import { DataQualityWarnings } from './components/DataQualityWarnings'
import { TreatmentPlanContentSummary } from './components/TreatmentPlanContentSummary'
import {
  AllevaPatientTreatmentPlanPanel,
  type AllevaPatientCenteredTreatmentPlanHarnessResult,
  type AllevaPatientCenteredTreatmentPlanReport,
  type AllevaPatientPlanPullState,
} from './components/AllevaPatientTreatmentPlanPanel'
import {
  OPERATIONAL_STATUS_CONFIG,
  buildStatusSummaries,
  formatDueDelta,
  groupOperationalQueueItems,
  statusToOperationalStatus,
  type OperationalFilter,
  type OperationalStatus,
  type StatusSummary,
} from './clinicalOperationsModel'
import {
  DateEvidenceTimeline,
  EmptyTreatmentPlanDetail,
  EvidenceLedger,
  RiskStatusStrip,
  SourceComparisonTable,
  SourceReadinessCard,
  type EvidenceLedgerEntry,
  type EvidenceTimelineStep,
  type SourceComparisonRow,
  type SourceReadinessCardModel,
} from './components/ClinicalOperationsWorkbench'
import { contentItemMetadataSummary, safeContentItems, safeContentTree, type TreatmentPlanContentItem } from './treatmentPlanContentSafety'
import './app.css'

const API = import.meta.env.VITE_API_URL || '/api'
const SESSION_TOKEN_KEY = 'iz-cna-session-token'

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
type AppView = 'dashboard' | 'reviews' | 'timeliness' | 'sources' | 'checklist' | 'uploads' | 'profile' | 'users' | 'workflows' | 'logs' | 'settings' | 'help'

type VersionInfo = {
  app_name: string
  version: string
  build: string
  release_channel: string
  release_date: string
  stability: string
  is_prerelease: boolean
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
  source_attachment_url: string
  source_author: string
  source_custodian: string
  source_security_label: string
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
  | OperationalStatus
  | 'Approved'
type TimelinessFilter = OperationalFilter

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
  current_date: string
  status: TimelinessStatus
  rule_used: string
  evidence_summary: string
  evidence_completeness_percent: number
  missing_evidence_fields: string[]
  last_checked_at: string
  last_imported_at: string | null
  discharge_conflict?: boolean
  data_quality_warnings?: string[]
  id_join_confidence?: string
  source_confidence?: string
  source_endpoint_count?: number
  current_plan_record_id?: number | null
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

type TimelinessEvaluatedValue = {
  field: string
  label: string
  value: unknown
  status: string
  source?: string
}

type TimelinessChecklistResult = {
  step: number
  key: string
  title: string
  status: string
  result: string
  severity: string
  source_evidence: string
  finding_message: string
  evidence_fields_used: string[]
  evaluated_values: TimelinessEvaluatedValue[]
  required_metadata: string[]
  required_documents: string[]
  checks: string[]
  finding_examples: string[]
  remediation_suggestions: string[]
  reviewer_actions: string[]
  manual_override_allowed: boolean
  override_reason_required: boolean
  audit_event: string
  export_fields: string[]
  manager_status: string
  manager_comment: string
  manager_updated_by_id: number | null
  manager_updated_at: string | null
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
  plan_field_count?: number
  problem_count?: number
  diagnosis_count?: number
  behavioral_definition_count?: number
  goal_count?: number
  objective_count?: number
  intervention_count?: number
  has_guardian_signature?: boolean
  guardian_signature_date?: string
  alleva_is_active?: boolean
  alleva_is_complete?: boolean
  alleva_is_initial_tp?: boolean
  alleva_start_date?: string
  alleva_end_date?: string
  alleva_last_modified?: string
  detail_fetched?: boolean
  detail_fetched_at?: string | null
  content_source?: string
  content_items?: TreatmentPlanContentItem[]
  content_tree?: Record<string, unknown>
  content_capture_status?: string
  content_capture_warnings?: string
  is_current?: boolean
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
  current_date: string
  date_clock_anchor_date: string | null
  date_clock_anchor_source: string
  date_clock_due_date: string | null
  loc_change_due_date: string | null
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
  checklist_id: string
  checklist_version: string
  evidence_comparison: TimelinessEvidenceComparison
  rule_results: TimelinessRuleResult[]
  checklist_results: TimelinessChecklistResult[]
  level_of_care_history: TimelinessLevelOfCare[]
  treatment_plans: TimelinessTreatmentPlan[]
  overrides: TimelinessOverride[]
  audit_history: AuditLogRecord[]
  alleva_lead_id?: string
  alleva_client_id?: string
  alleva_unique_id?: string
  alleva_mrn?: string
  alleva_source_id?: string
  id_join_warnings?: string[]
}

type ClearPatientDataResponse = {
  status: 'cleared' | 'partial'
  message: string
  deleted_counts: Record<string, number>
  storage_result: Record<string, unknown>
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
  api_client_id: string
  api_client_secret_configured: boolean
  api_oauth_token_url: string
  api_token_auth_style: string
  emr_api_timeout_seconds: number
  emr_periodic_check_enabled: boolean
  emr_periodic_check_interval_minutes: number
  emr_last_check_at: string | null
  emr_last_check_status: string
  emr_last_check_message: string
  emr_last_successful_check_at: string | null
  emr_last_failure_at: string | null
  alleva_api_base_url: string
  alleva_openapi_url: string
  alleva_api_version: string
  alleva_treatment_plan_sync_enabled: boolean
  alleva_treatment_plan_sync_on_startup: boolean
  alleva_treatment_plan_sync_approved: boolean
  alleva_treatment_plan_endpoint_mapping_validated: boolean
  alleva_treatment_plan_sync_limit: number
  alleva_treatment_plan_detail_fetch_enabled?: boolean
  alleva_treatment_plan_patient_name_import_enabled?: boolean
  alleva_treatment_plan_name_join_fallback_enabled?: boolean
  alleva_treatment_plan_detail_fetch_limit?: number
  alleva_treatment_plan_sync_last_at: string | null
  alleva_treatment_plan_sync_last_status: string
  alleva_treatment_plan_sync_last_message: string
  alleva_treatment_plan_sync_last_success_at: string | null
  alleva_treatment_plan_sync_last_failure_at: string | null
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
  api_client_id: string
  api_client_secret: string
  clear_api_client_secret: boolean
  api_oauth_token_url: string
  api_token_auth_style: string
  emr_api_timeout_seconds: number
  emr_periodic_check_enabled: boolean
  emr_periodic_check_interval_minutes: number
  alleva_api_base_url: string
  alleva_openapi_url: string
  alleva_api_version: string
  alleva_treatment_plan_sync_enabled: boolean
  alleva_treatment_plan_sync_on_startup: boolean
  alleva_treatment_plan_sync_approved: boolean
  alleva_treatment_plan_endpoint_mapping_validated: boolean
  alleva_treatment_plan_sync_limit: number
  alleva_treatment_plan_detail_fetch_enabled: boolean
  alleva_treatment_plan_patient_name_import_enabled: boolean
  alleva_treatment_plan_name_join_fallback_enabled: boolean
  alleva_treatment_plan_detail_fetch_limit: number
  facility_timezone: string
  treatment_plan_loc_change_window_days: number | null
  treatment_plan_loc_change_window_validated: boolean
}

type AllevaTreatmentPlanSyncResult = {
  status: string
  message: string
  warnings?: string[]
  failure_stage?: string
  category?: string
  endpoint?: string
  status_code?: number
  upserted_client_count?: number
  active_client_count?: number
  treatment_plan_count?: number
  treatment_review_count?: number
  unmapped_treatment_plan_count?: number
  unmapped_treatment_review_count?: number
  unmapped_plan_ids?: Record<string, string>[]
  unmapped_review_ids?: Record<string, string>[]
  name_join_fallback_count?: number
  current_plan_selected_count?: number
  current_plan_missing_count?: number
  detail_fetch_enabled?: boolean
  detail_fetch_attempt_count?: number
  detail_fetch_success_count?: number
  detail_fetch_failed_count?: number
  detail_fetch_skipped_count?: number
  missing_fields?: string[]
}

type AllevaTreatmentPlanSyncResponse = {
  sync_result: AllevaTreatmentPlanSyncResult
  settings: AppSettings
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
  source_attachment_url: string
  source_author: string
  source_custodian: string
  source_security_label: string
}

type TransitionAction = {
  toState: WorkflowState
  label: string
  commentLabel: string
  requiresComment?: boolean
}

type ApiError = {
  detail?: string | { msg?: string } | { msg?: string }[]
  raw?: string
}

type ApiConfigurationOut = {
  vendor_name: string
  api_base_url: string
  swagger_ui_url: string
  openapi_url: string
  api_key_configured: boolean
  client_id: string
  client_id_configured: boolean
  client_secret_configured: boolean
  token_url: string
  token_auth_style: string
  api_key_header_name: string
  timeout_seconds: number
  api_enabled: boolean
  recommended_auth_mode: 'api_key' | 'client_credentials' | 'none'
}

type AllevaPatientCenteredTreatmentPlanPullPayload = {
  report: AllevaPatientCenteredTreatmentPlanReport
  patient_id: string | null
  swagger_ui_url: string
  api_base_url: string
  openapi_url: string
  auth_mode: 'client_credentials'
  token_url: string
  token_auth_style: string
  client_id: string | null
  client_secret: null
  use_saved_client_credentials: true
  api_key: null
  use_saved_api_key: true
  api_key_header_name: string
  scope: null
  timeout_seconds: number
  max_pages: number
  operation_parameters: Record<string, string | number>
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

type EmrEndpointProfile = {
  id: number
  profile_key: string
  display_name: string
  vendor_name: string
  adapter_key: string
  api_base_url: string
  openapi_url: string
  token_url: string
  token_auth_style: string
  client_id: string
  client_id_configured: boolean
  client_secret_configured: boolean
  timeout_seconds: number
  is_active: boolean
  is_default: boolean
  notes: string
  created_by_id: number | null
  updated_by_id: number | null
  created_at: string
  updated_at: string
}

type EmrEndpointProfileForm = {
  profile_key: string
  display_name: string
  vendor_name: string
  adapter_key: string
  api_base_url: string
  openapi_url: string
  token_url: string
  token_auth_style: string
  client_id: string
  client_secret: string
  timeout_seconds: number
  notes: string
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

const TIMELINESS_FILTERS: TimelinessFilter[] = ['All', ...OPERATIONAL_STATUS_CONFIG.map((config) => config.status)]
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
const CLEAR_PATIENT_DATA_CONFIRMATION = 'CLEAR ALL PATIENT DATA'
const MANAGER_CRITERION_STATUSES = ['Not Reviewed', 'OK', 'Needs Review', 'Needs Update', 'Not Applicable']

const VIEW_LABELS: Record<AppView, string> = {
  dashboard: 'Status Dashboard',
  reviews: 'Review queue',
  uploads: 'Manual upload',
  timeliness: 'Treatment plans',
  sources: 'Source readiness',
  checklist: 'Checklist',
  profile: 'My account',
  users: 'User management',
  workflows: 'Workflow profiles',
  logs: 'Forensic logs',
  settings: 'App settings',
  help: 'Help',
}

const APP_VIEWS: AppView[] = ['dashboard', 'timeliness', 'reviews', 'sources', 'checklist', 'uploads', 'profile', 'users', 'workflows', 'logs', 'settings', 'help']
const PRIMARY_WORKFLOW_VIEWS: readonly AppView[] = ['dashboard', 'timeliness', 'reviews', 'uploads']
const SUPPORT_WORKFLOW_VIEWS: readonly AppView[] = ['sources', 'checklist', 'help', 'profile']
const MANAGER_WORKFLOW_VIEWS: readonly AppView[] = ['users', 'workflows']
const ADMIN_WORKFLOW_VIEWS: readonly AppView[] = ['logs', 'settings']

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

const ROLE_CAPABILITIES = [
  {
    role: 'Admin',
    can: [
      'Use every screen and action, including user management, workflow profiles, app settings, API/EMR setup, LLM setup, logs, uploads, reviews, overrides, exports, and readiness checks.',
    ],
    cannot: ['Change the fixed bootstrap admin password in-app.'],
  },
  {
    role: 'Office manager',
    can: [
      'Use the treatment-plan queue, review queue, manual upload/update, counselor user management, workflow profile editing/versioning, manager approvals/returns, manual timeliness overrides, exports, and own account.',
    ],
    cannot: ['Open App settings, API/EMR configuration, LLM setup, forensic logs, or manage admin/manager accounts.'],
  },
  {
    role: 'Counselor',
    can: ['Manual upload/update for their own binders, view accessible queues/details, respond to returned review work, export permitted details, and manage their own account.'],
    cannot: ['Manage users, settings, API/EMR setup, workflow profiles, forensic logs, manager approvals, or treatment-plan overrides.'],
  },
]

const HELP_SECTIONS = [
  {
    title: 'Status Dashboard',
    items: [
      'Refresh reloads the current workspace and clears stale queue data.',
      'EMR/API access shows readiness-only status until vendor mapping and compliance approval are complete.',
      'Run safe API readiness check performs a connection/readiness check only; it does not import live Alleva patient charts.',
      'Retrieve Active Treatment Plans runs the gated manual Alleva treatment-plan sync only when admin settings, R3/Alleva approval, and mapping validation are complete.',
      'Clear All Patient Data is admin-only, requires an exact typed phrase, and preserves settings, API credentials, users, and forensic logs.',
      'Upload binder starts a manual upload or update workflow; Open review queue opens generated chart-review work.',
    ],
  },
  {
    title: 'Treatment Plans',
    items: [
      'The date clock uses the local laptop/facility date, the admission date, and the last valid treatment-plan review/update date to calculate the next required update.',
      'PHP levels use a 30-calendar-day recurring update window; IOP, OP, and other configured non-PHP levels use 60 calendar days.',
      'Level-of-care changes use the separate manager-editable LOC-change window in App settings. The preset is 7 calendar days and the validation checkbox shows whether R3 has accepted the rule.',
      'Status filters narrow the queue by Overdue, Urgent, Due Soon, Returned, Needs Review, Missing Data, Conflicting Evidence, Unable to Evaluate, Compliant, or Approved.',
      'View evidence opens the exact date fields used for the selected due-date comparison.',
      'Copy task list and Export task list create non-secret work lists for follow-up tracking. Export CSV/JSON includes rule results and the current 42-step workflow step statuses.',
      'Admins and office managers can save manager status/comments on each of the 42 checklist criteria and export a selected-client counselor action list.',
      'Manual override is available only to admins and office managers and requires a reason.',
    ],
  },
  {
    title: 'Manual Upload',
    items: [
      'Initial creates the first binder for a patient ID; Update supersedes the active binder and re-runs evaluation.',
      'Detect patient ID reads supported synthetic/export files conservatively; conflicting IDs are blocked.',
      'Upload and run automated evaluation stores files encrypted, creates a review chart, syncs treatment-plan tracker records, and evaluates deterministic rules. When evidence is found in an uploaded PDF, the evidence location includes an uploaded page number when available.',
      'If no approved client display name is supplied or detected, the app creates no-name-found_YYYY-MM-DD_HHMMSS or no-value-found_YYYY-MM-DD_HHMMSS as the display name.',
      'Delete uploaded binder stays clickable so it can show exact patient-ID confirmation guidance; once confirmed, it removes the binder, linked generated review, upload-derived treatment-plan data, and encrypted stored files when authorized.',
    ],
  },
  {
    title: 'Review Queue',
    items: [
      'Open automated review loads the selected uploaded-binder chart and criterion workbench.',
      'Review Queue remains the manual/generated chart-review workbench; Treatment Plans remains the active due-date and timeliness work queue.',
      'Mark OK, Mark not OK, Not applicable, and Save criterion review changes are available to admins and office managers.',
      'Export CSV and Export JSON keep the existing checklist-domain status rows and also include the current 42-step workflow statuses.',
      'Approve and Return to counselor are manager/admin decisions; returns require a correction note.',
      'Re-analyze reruns deterministic checks from the stored encrypted binder while preserving an operator-approved display name.',
    ],
  },
  {
    title: 'User Management',
    items: [
      'Admins can create and maintain admin, manager, and counselor accounts.',
      'Office managers can create, update, unlock, deactivate, reset, or delete counselor accounts only.',
      'Delete user works only when the account has no linked clinical, workflow, or audit history; otherwise deactivate it.',
    ],
  },
  {
    title: 'Workflow Profiles',
    items: [
      'Create profile defines a versioned checklist/workflow logic container.',
      'Seed draft from 42-step checklist loads the canonical checklist into editable workflow JSON.',
      'Edit draft changes the selected draft in place. Use as draft loads a published version as a new draft template without archiving the current profile.',
      'Create draft version records proposed logic changes; Publish makes that version current and archives the previous published version.',
      'Archive profile retires a workflow profile without deleting its audit history.',
    ],
  },
  {
    title: 'App Settings, API/EMR, And LLM',
    items: [
      'App settings are admin-only and include organization, timezone, LOC-change blocker, access intelligence, optional LLM, EMR/API configuration, and the Clear All Patient Data control.',
      'Alleva currently identifies HL7 as the standards-based integration path; active app integration is Alleva REST/OpenAPI/HL7 readiness.',
      'There is one active Alleva/API connection in App settings. The API test harness loads these same active values.',
      'Pasting the client ID and client secret supplied by Alleva/R3 is the normal OAuth client-credentials setup. The saved secret is encrypted and never returned to the browser.',
      'Alleva REST treatment-plan sync uses the active REST API base URL and OpenAPI documentation URL. R3 runs compliance checks locally after the app imports approved mapped treatment-plan data.',
      'Run sync every time the app starts remains off by default for beta client builds; use manual retrieval until R3/Alleva approval and mapping are confirmed.',
      'Periodic API checks require the REST API base URL, OpenAPI URL, OAuth token URL, client ID, and a stored client secret. Save errors list the exact missing fields.',
      'Saved API endpoint profiles are presets. Activating one copies its values into the active App settings connection used by readiness/API tests.',
      'LLM support is disabled by default; when enabled it uses an OpenAI-compatible base URL, API key, model, and optional analysis instructions.',
    ],
  },
  {
    title: 'Field Guidance',
    items: [
      'Admission date is the treatment episode start date and is used when no later valid treatment-plan review/update date exists.',
      'Last valid review/update date comes from a treatment-plan review or LOC-update record with usable source evidence and a staff/therapist signature date.',
      'Current LOC must map to configured LOC aliases. PHP maps to a 30-day update clock; other configured treatment levels map to 60 days unless the rules config is changed.',
      'Alleva REST API base URL is the source for startup treatment-plan sync. Leave startup sync off until R3 and Alleva approve live sync and validate active-client, treatment-plan, treatment-review, pagination, and field mapping.',
      'OpenAPI URL is the Swagger/OpenAPI JSON definition used by the API test harness to discover operations and required fields.',
      'Client secret and API keys are write-only fields. A configured flag means a secret is stored; the secret itself is never returned to the browser.',
    ],
  },
  {
    title: 'Forensic Logs And Account',
    items: [
      'Forensic logs are admin-only and show request, access, workflow, upload, settings, API, and user-management events.',
      'My account lets every role update their display name and change managed-account passwords.',
      'The fixed bootstrap admin account is recovered outside the app and cannot change its password in-app.',
    ],
  },
]

class ApiRequestError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiRequestError'
    this.status = status
  }
}

function readErrorMessage(status: number, payload: ApiError | null, isSessionExpired = false) {
  const detail = payload?.detail
  const detailText =
    typeof detail === 'string' && detail.trim()
      ? detail.trim()
      : Array.isArray(detail)
        ? detail
            .map((item) => (typeof item?.msg === 'string' ? item.msg.trim() : ''))
            .filter(Boolean)
            .join('; ')
      : detail && typeof detail === 'object' && typeof detail.msg === 'string'
        ? detail.msg.trim()
        : payload?.raw?.trim() || ''

  if (status === 401) return isSessionExpired ? 'Your session has expired. Sign in again to continue.' : detailText || 'Invalid credentials'
  if (status === 403) return detailText || 'Your account does not have access to that action.'
  if (status === 413) return 'The selected upload is too large. Remove files or split the binder into a smaller upload.'
  if (status === 422) return detailText || 'Some required information is missing or needs a different format.'
  if (status >= 500) return detailText || 'The local app could not finish that request. Try again, then restart the app if it keeps happening.'
  if (detailText) return detailText
  return 'The request could not be completed.'
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

function requestedViewFromUrl(): AppView | null {
  if (typeof window === 'undefined') return null
  const requested = new URLSearchParams(window.location.search).get('view') || window.location.hash.replace(/^#\/?/, '')
  return APP_VIEWS.includes(requested as AppView) ? (requested as AppView) : null
}

function allevaPatientIdFromUrl() {
  if (typeof window === 'undefined') return ''
  return new URLSearchParams(window.location.search).get('allevaPatientId')?.trim() || ''
}

function viewFromUrl(): AppView {
  return requestedViewFromUrl() || 'dashboard'
}

function hasExplicitViewInUrl() {
  return requestedViewFromUrl() !== null
}

function getStoredSessionToken() {
  if (typeof window === 'undefined') return ''
  return window.sessionStorage.getItem(SESSION_TOKEN_KEY) || ''
}

function storeSessionToken(token: string) {
  if (typeof window === 'undefined') return
  if (token) {
    window.sessionStorage.setItem(SESSION_TOKEN_KEY, token)
  } else {
    window.sessionStorage.removeItem(SESSION_TOKEN_KEY)
  }
}

function createAllevaPatientPlanPullState(patientId = allevaPatientIdFromUrl()): AllevaPatientPlanPullState {
  return {
    status: 'idle',
    message: patientId ? `Ready to load Alleva patient_id ${patientId}.` : 'Enter an Alleva patient ID or load active patient-centered records.',
    result: null,
    selectedPatientId: patientId,
  }
}

function allevaTreatmentPlanOperationParameters(apiVersion = '1.0') {
  return {
    Limit: 100,
    Cursor: 0,
    StartDate: '2000-01-01T16:03',
    'api-version': apiVersion,
    'X-Version': apiVersion,
  }
}

function allevaPatientCenteredTreatmentPlanPullPayload(
  config: ApiConfigurationOut,
  report: AllevaPatientCenteredTreatmentPlanReport,
  patientId: string,
): AllevaPatientCenteredTreatmentPlanPullPayload {
  return {
    report,
    patient_id: report === 'single_patient_treatment_plans' ? patientId : null,
    swagger_ui_url: config.swagger_ui_url || 'https://api.allevasoft.com/swagger/index.html',
    api_base_url: config.api_base_url || 'https://api.allevasoft.com',
    openapi_url: config.openapi_url || 'https://api.allevasoft.com/swagger/v1/swagger.json',
    auth_mode: 'client_credentials',
    token_url: config.token_url || 'https://authorization.allevasoft.com/connect/token',
    token_auth_style: config.token_auth_style || 'body',
    client_id: config.client_id || null,
    client_secret: null,
    use_saved_client_credentials: true,
    api_key: null,
    use_saved_api_key: true,
    api_key_header_name: config.api_key_header_name || 'x-api-key',
    scope: null,
    timeout_seconds: config.timeout_seconds || 10,
    max_pages: 1,
    operation_parameters: allevaTreatmentPlanOperationParameters('1.0'),
  }
}

function defaultViewForRole(role: Role): AppView | null {
  return role === 'admin' || role === 'manager' ? 'timeliness' : null
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
    api_client_id: settings.api_client_id,
    api_client_secret: '',
    clear_api_client_secret: false,
    api_oauth_token_url: settings.api_oauth_token_url || 'https://authorization.allevasoft.com/connect/token',
    api_token_auth_style: settings.api_token_auth_style || 'body',
    emr_api_timeout_seconds: settings.emr_api_timeout_seconds,
    emr_periodic_check_enabled: settings.emr_periodic_check_enabled,
    emr_periodic_check_interval_minutes: settings.emr_periodic_check_interval_minutes || 1440,
    alleva_api_base_url: settings.alleva_api_base_url || 'https://api.allevasoft.com',
    alleva_openapi_url: settings.alleva_openapi_url || 'https://api.allevasoft.com/swagger/v1/swagger.json',
    alleva_api_version: settings.alleva_api_version || '1.0',
    alleva_treatment_plan_sync_enabled: settings.alleva_treatment_plan_sync_enabled,
    alleva_treatment_plan_sync_on_startup: settings.alleva_treatment_plan_sync_on_startup,
    alleva_treatment_plan_sync_approved: settings.alleva_treatment_plan_sync_approved,
    alleva_treatment_plan_endpoint_mapping_validated: settings.alleva_treatment_plan_endpoint_mapping_validated,
    alleva_treatment_plan_sync_limit: settings.alleva_treatment_plan_sync_limit || 250,
    alleva_treatment_plan_detail_fetch_enabled: Boolean(settings.alleva_treatment_plan_detail_fetch_enabled),
    alleva_treatment_plan_patient_name_import_enabled: Boolean(settings.alleva_treatment_plan_patient_name_import_enabled),
    alleva_treatment_plan_name_join_fallback_enabled: Boolean(settings.alleva_treatment_plan_name_join_fallback_enabled),
    alleva_treatment_plan_detail_fetch_limit: settings.alleva_treatment_plan_detail_fetch_limit ?? 50,
    facility_timezone: settings.facility_timezone || 'local_machine',
    treatment_plan_loc_change_window_days: settings.treatment_plan_loc_change_window_days ?? 7,
    treatment_plan_loc_change_window_validated: settings.treatment_plan_loc_change_window_validated,
  }
}

function createEmrEndpointProfileForm(): EmrEndpointProfileForm {
  return {
    profile_key: 'alleva-rest-api',
    display_name: 'Alleva REST API documentation profile',
    vendor_name: 'Alleva REST API',
    adapter_key: 'alleva-rest-api',
    api_base_url: 'https://api.allevasoft.com',
    openapi_url: 'https://api.allevasoft.com/swagger/v1/swagger.json',
    token_url: 'https://authorization.allevasoft.com/connect/token',
    token_auth_style: 'body',
    client_id: '',
    client_secret: '',
    timeout_seconds: 10,
    notes: 'Saved preset only. Activate this profile to copy its values into the active App settings API connection. REST sync remains gated by R3/Alleva approval and endpoint mapping validation.',
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
    source_attachment_url: '',
    source_author: '',
    source_custodian: '',
    source_security_label: '',
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

function formatEvaluatedValue(value: unknown): string {
  if (value == null || value === '') return 'Not recorded'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (Array.isArray(value)) return value.length ? value.map(formatEvaluatedValue).join('; ') : 'None'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function evaluatedValuesSummary(values: TimelinessEvaluatedValue[] | undefined) {
  if (!values?.length) return ''
  return values.map((item) => `${item.label || item.field}: ${formatEvaluatedValue(item.value)} (${item.status})`).join('; ')
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
  const header = ['patient_id', 'due_date', 'status', 'current_loc', 'primary_clinician', 'reason']
  const rows = timelinessTaskItems(items).map((item) =>
    [
      item.patient_id,
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

function buildSelectedTimelinessCounselorActions(client: TimelinessClientDetail) {
  const actionableCriteria = client.checklist_results.filter((result) => {
    const managerActionable = result.manager_status === 'Needs Review' || result.manager_status === 'Needs Update'
    const resultActionable = TIMELINESS_TASK_STATUSES.has(result.status as TimelinessStatus)
    return managerActionable || resultActionable || result.manager_comment.trim()
  })
  const header = [
    'patient_id',
    'current_loc',
    'primary_clinician',
    'next_due_date',
    'overall_status',
    'criterion_step',
    'criterion_key',
    'criterion_title',
    'criterion_status',
    'manager_status',
    'manager_comment',
    'recommended_action',
    'source_evidence',
  ]
  const rows = actionableCriteria.map((result) =>
    [
      client.patient_id,
      client.current_level_of_care || 'Missing',
      client.counselor_name || 'Unassigned',
      client.next_due_date || 'Not calculated',
      client.status,
      result.step,
      result.key,
      result.title,
      result.status,
      result.manager_status || 'Not Reviewed',
      result.manager_comment || '',
      result.reviewer_actions.length ? result.reviewer_actions.join('; ') : result.remediation_suggestions.join('; '),
      result.source_evidence || client.evidence_summary,
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
  if (status === 'Overdue') return 'overdue'
  if (status === 'Urgent') return 'urgent'
  if (status === 'Due Soon') return 'due-soon'
  if (status === 'Returned for Correction') return 'returned'
  if (status === 'Needs Review') return 'needs-review'
  if (status === 'Missing Data') return 'missing-data'
  if (status === 'Conflicting Evidence') return 'conflicting'
  if (status === 'Unable to Evaluate') return 'unable'
  return 'neutral'
}

function managerCriterionTone(status: string) {
  if (status === 'OK') return 'success'
  if (status === 'Needs Update') return 'urgent'
  if (status === 'Needs Review') return 'needs-review'
  if (status === 'Not Applicable') return 'neutral'
  return 'muted'
}

function timelinessFilterCount(dashboard: TimelinessDashboard | null, filter: TimelinessFilter) {
  if (!dashboard) return 0
  if (filter === 'All') return dashboard.items.length
  return dashboard.items.filter((item) => statusToOperationalStatus(item.status) === filter).length
}

function timelinessDashboardCounts(dashboard: TimelinessDashboard | null): Partial<Record<OperationalStatus, number>> {
  return {
    Overdue: dashboard?.overdue ?? 0,
    Urgent: dashboard?.urgent ?? 0,
    'Due Soon': dashboard?.due_soon ?? 0,
    'Returned for Correction': dashboard?.returned ?? 0,
    'Needs Review': dashboard?.needs_review ?? 0,
    'Missing Data': dashboard?.missing_data ?? 0,
    'Conflicting Evidence': dashboard?.conflicting_evidence ?? 0,
    'Unable to Evaluate': dashboard?.unable_to_evaluate ?? 0,
    Compliant: (dashboard?.compliant ?? 0) + (dashboard?.approved ?? 0),
  }
}

function operationalStatusSentence(summaries: StatusSummary[]) {
  const activeSummaries = summaries.filter((summary) => summary.count > 0)
  if (!activeSummaries.length) return 'No treatment-plan records are loaded yet.'
  return activeSummaries.map((summary) => `${summary.count} ${summary.label.toLowerCase()}`).join(', ')
}

type SourceReadinessInputs = {
  readonly reviewSourceDiscovery: ReviewSourceDiscovery | null
  readonly appSettings: AppSettings | null
  readonly noteSets: readonly PatientNoteSetSummary[]
  readonly readiness: RuntimeReadiness | null
  readonly lastAllevaSyncResult: AllevaTreatmentPlanSyncResult | null
  readonly canRunAllevaTreatmentPlanSync: boolean
}

type EvidenceLedgerInputs = {
  readonly reviewSourceDiscovery: ReviewSourceDiscovery | null
  readonly appSettings: AppSettings | null
  readonly noteSets: readonly PatientNoteSetSummary[]
  readonly logs: readonly AuditLogRecord[]
  readonly lastAllevaSyncResult: AllevaTreatmentPlanSyncResult | null
}

function latestNoteSet(noteSets: readonly PatientNoteSetSummary[]) {
  return [...noteSets].sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())[0] || null
}

function sourceReadinessCards(input: SourceReadinessInputs): SourceReadinessCardModel[] {
  const latestUpload = latestNoteSet(input.noteSets)
  const apiConfigured = Boolean(input.reviewSourceDiscovery?.api_configured || input.appSettings?.emr_api_enabled)
  const syncEnabled = Boolean(input.appSettings?.alleva_treatment_plan_sync_enabled)
  const syncApproved = Boolean(input.appSettings?.alleva_treatment_plan_sync_approved)
  const syncMapped = Boolean(input.appSettings?.alleva_treatment_plan_endpoint_mapping_validated)
  const syncReady = syncEnabled && syncApproved && syncMapped
  const syncBlockers = [
    syncApproved ? '' : 'R3/Alleva approval for live treatment-plan sync is not recorded.',
    syncMapped ? '' : 'Treatment-plan endpoint mapping is not validated.',
    syncEnabled ? '' : 'Alleva treatment-plan sync is disabled by default.',
    input.appSettings?.api_client_secret_configured ? '' : 'Saved API secret is not configured.',
  ].filter(Boolean)

  return [
    {
      title: 'Manual upload',
      state: latestUpload ? 'Available' : 'Ready for binder',
      tone: 'success',
      description: input.reviewSourceDiscovery?.manual_mode_message || 'Encrypted local binder upload remains the approved fallback source for chart review and treatment-plan evaluation.',
      facts: [
        { label: 'Active binders', value: String(input.noteSets.filter((noteSet) => noteSet.status === 'active').length) },
        { label: 'Latest upload', value: latestUpload ? formatDateTime(latestUpload.created_at) : 'No upload loaded' },
        { label: 'Cadence', value: input.reviewSourceDiscovery?.manual_review_cadence || 'Monthly compliance-check fallback' },
        { label: 'Freshness', value: 'As of upload time only' },
      ],
      blockers: [],
      allowedActions: ['Upload encrypted binder', 'Review generated findings', 'Export task lists'],
      disabledActions: ['Automatic vendor import from manual files'],
      prerequisites: ['Synthetic or approved patient IDs only', 'No local runtime files committed'],
    },
    {
      title: 'API readiness',
      state: input.reviewSourceDiscovery?.api_mode_label || (apiConfigured ? 'Configured for readiness' : 'Mock/stub mode'),
      tone: apiConfigured ? 'needs-review' : 'missing-data',
      description: input.reviewSourceDiscovery?.plain_english_status || 'API checks stay in readiness mode until vendor credentials, mapping, and compliance approval are complete.',
      facts: [
        { label: 'Last safe check', value: input.reviewSourceDiscovery?.last_successful_check_at ? formatDateTime(input.reviewSourceDiscovery.last_successful_check_at) : 'Not run' },
        { label: 'Last failure', value: input.reviewSourceDiscovery?.last_failure_at ? formatDateTime(input.reviewSourceDiscovery.last_failure_at) : input.appSettings?.emr_last_failure_at ? formatDateTime(input.appSettings.emr_last_failure_at) : 'None loaded' },
        { label: 'Next refresh', value: input.reviewSourceDiscovery?.next_refresh_at ? formatDateTime(input.reviewSourceDiscovery.next_refresh_at) : 'After configuration' },
        { label: 'Runtime', value: input.readiness ? `${input.readiness.status}; ${input.readiness.warnings} warning(s)` : 'Readiness not loaded' },
      ],
      blockers: apiConfigured ? [] : ['API client, token URL, and encrypted secret must be configured by an admin.'],
      allowedActions: ['Run safe API readiness check', 'Review source discovery items'],
      disabledActions: ['Live Alleva patient import'],
      prerequisites: ['Official tenant credentials', 'Endpoint documentation', 'Compliance approval'],
    },
    {
      title: 'Alleva treatment-plan sync',
      state: syncReady ? 'Ready for admin pull' : 'Awaiting approval',
      tone: syncReady ? 'success' : 'conflicting',
      description: 'Manual admin pull remains gated and must not run as live patient import until approval, credentials, and endpoint mapping are confirmed.',
      facts: [
        { label: 'Last sync', value: input.appSettings?.alleva_treatment_plan_sync_last_at ? formatDateTime(input.appSettings.alleva_treatment_plan_sync_last_at) : 'Not run' },
        { label: 'Last status', value: input.appSettings?.alleva_treatment_plan_sync_last_status || input.lastAllevaSyncResult?.status || 'No sync result' },
        { label: 'Configured limit', value: String(input.appSettings?.alleva_treatment_plan_sync_limit ?? 'Not set') },
        { label: 'Admin action', value: input.canRunAllevaTreatmentPlanSync ? 'Visible to admin' : 'Admin only' },
      ],
      blockers: syncBlockers.length ? syncBlockers : [],
      allowedActions: syncReady ? ['Retrieve Active Treatment Plans', 'Review sync diagnostics'] : ['Review configuration', 'Document blocker status'],
      disabledActions: syncReady ? ['Automatic startup live import unless separately enabled'] : ['Retrieve Active Treatment Plans'],
      prerequisites: ['R3/Alleva approval', 'Validated endpoint mapping', 'Encrypted credential storage', 'Pagination/rate-limit behavior confirmed'],
    },
  ]
}

function evidenceLedgerEntries(input: EvidenceLedgerInputs): EvidenceLedgerEntry[] {
  const latestUpload = latestNoteSet(input.noteSets)
  const recentExport = input.logs.find((entry) => entry.action.toLowerCase().includes('export'))
  const recentOverride = input.logs.find((entry) => entry.action.toLowerCase().includes('override'))
  const entries = [
    input.reviewSourceDiscovery?.last_successful_check_at
      ? {
          label: 'Safe API readiness check',
          detail: input.reviewSourceDiscovery.last_check_mode || input.reviewSourceDiscovery.refresh_mode || 'Readiness check completed',
          timestamp: formatDateTime(input.reviewSourceDiscovery.last_successful_check_at),
          tone: 'needs-review',
        }
      : null,
    latestUpload
      ? {
          label: 'Manual binder upload',
          detail: `${latestUpload.file_count} file(s); ${latestUpload.status} binder`,
          timestamp: formatDateTime(latestUpload.created_at),
          tone: 'success',
        }
      : null,
    input.appSettings?.alleva_treatment_plan_sync_last_at
      ? {
          label: 'Alleva sync gate',
          detail: input.appSettings.alleva_treatment_plan_sync_last_message || input.appSettings.alleva_treatment_plan_sync_last_status,
          timestamp: formatDateTime(input.appSettings.alleva_treatment_plan_sync_last_at),
          tone: input.appSettings.alleva_treatment_plan_sync_approved ? 'success' : 'conflicting',
        }
      : null,
    input.lastAllevaSyncResult
      ? {
          label: 'Latest sync diagnostics',
          detail: input.lastAllevaSyncResult.message || input.lastAllevaSyncResult.status,
          timestamp: 'Current session',
          tone: input.lastAllevaSyncResult.status === 'success' ? 'success' : 'warning',
        }
      : null,
    recentExport
      ? {
          label: 'Recent export',
          detail: recentExport.message || recentExport.action,
          timestamp: formatLogDateTime(recentExport),
          tone: 'neutral',
        }
      : null,
    recentOverride
      ? {
          label: 'Manual override',
          detail: recentOverride.message || recentOverride.action,
          timestamp: formatLogDateTime(recentOverride),
          tone: 'warning',
        }
      : null,
  ].filter((entry): entry is EvidenceLedgerEntry => entry !== null)

  return entries.slice(0, 8)
}

function treatmentPlanTimelineSteps(client: TimelinessClientDetail): EvidenceTimelineStep[] {
  const initialPlan = client.treatment_plans.find((plan) => plan.plan_kind === 'initial') || null
  const currentPlan = client.current_plan_record_id
    ? client.treatment_plans.find((plan) => plan.id === client.current_plan_record_id) || null
    : client.treatment_plans.find((plan) => plan.is_current) || null
  const comparison = client.evidence_comparison
  return [
    {
      label: 'Admission date',
      date: displayDate(client.admission_date),
      source: client.source_evidence || 'Client record',
      confidence: client.admission_date ? 'Available' : 'Missing',
      tone: client.admission_date ? 'success' : 'missing-data',
    },
    {
      label: 'Initial TP date',
      date: displayDate(initialPlan?.document_date),
      source: initialPlan?.source_evidence || 'Treatment-plan record',
      confidence: initialPlan?.is_valid ? 'Valid source' : 'Needs review',
      tone: initialPlan?.document_date ? 'success' : 'missing-data',
    },
    {
      label: 'Current plan anchor',
      date: displayDate(comparison.date_clock_anchor_date || currentPlan?.document_date),
      source: comparison.date_clock_anchor_source || currentPlan?.source_evidence || 'Date clock',
      confidence: comparison.date_clock_anchor_date || currentPlan?.document_date ? 'Used for date clock' : 'Unable to evaluate',
      tone: comparison.date_clock_anchor_date || currentPlan?.document_date ? timelinessTone(client.status) : 'unable',
    },
    {
      label: 'LOC change anchor',
      date: displayDate(comparison.loc_effective_date),
      source: comparison.loc_change_rule_validated ? 'Validated LOC rule' : 'Unvalidated LOC rule',
      confidence:
        comparison.loc_change_window_days == null ? 'Window not configured' : `${comparison.loc_change_window_days} day window`,
      tone: comparison.loc_change_rule_validated ? 'success' : 'conflicting',
    },
    {
      label: 'Next required update',
      date: displayDate(client.next_due_date || comparison.date_clock_due_date),
      source: client.rule_used || 'Timeliness rule',
      confidence: formatDueDelta(client.status, client.days_until_due),
      tone: timelinessTone(client.status),
    },
  ]
}

function treatmentPlanSourceRows(client: TimelinessClientDetail): SourceComparisonRow[] {
  const comparison = client.evidence_comparison
  return [
    {
      field: 'Admission date',
      manualUpload: displayDate(client.admission_date),
      api: displayDate(comparison.date_clock_anchor_date),
      allevaSync: client.last_imported_at ? `Imported ${formatDateTime(client.last_imported_at)}` : 'No import timestamp',
      result: client.admission_date ? 'Available' : 'Missing data',
      tone: client.admission_date ? 'success' : 'missing-data',
    },
    {
      field: 'Source-document next review',
      manualUpload: displayDate(comparison.document_next_due_date),
      api: displayDate(comparison.date_clock_due_date),
      allevaSync: displayDate(comparison.signature_anchor_due_date),
      result: comparison.document_next_due_date ? 'Compared' : 'Missing data',
      tone: comparison.document_next_due_date ? timelinessTone(client.status) : 'missing-data',
    },
    {
      field: 'LOC-change due date',
      manualUpload: displayDate(comparison.loc_anchor_due_date),
      api: displayDate(comparison.loc_change_due_date),
      allevaSync: displayDate(comparison.loc_effective_date),
      result: comparison.loc_change_rule_validated ? 'Validated' : 'Unvalidated',
      tone: comparison.loc_change_rule_validated ? 'success' : 'conflicting',
    },
    {
      field: 'Final status',
      manualUpload: client.evidence_summary || 'No evidence summary',
      api: comparison.source_evidence || 'No source evidence',
      allevaSync: client.source_confidence || 'No confidence label',
      result: comparison.final_status,
      tone: timelinessTone(comparison.final_status),
    },
  ]
}

function versionPrefix(versionInfo: VersionInfo | null) {
  return versionInfo?.is_prerelease || versionInfo?.stability === 'beta' || versionInfo?.version.includes('beta') ? 'Beta v' : 'v'
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

function syncCount(value: number | undefined) {
  return String(value ?? 0)
}

function allevaSyncDiagnostics(result: AllevaTreatmentPlanSyncResult) {
  return [
    { label: 'Active clients', value: syncCount(result.active_client_count) },
    { label: 'Loaded clients', value: syncCount(result.upserted_client_count) },
    { label: 'Plan records', value: syncCount(result.treatment_plan_count) },
    { label: 'Review records', value: syncCount(result.treatment_review_count) },
    { label: 'Current plans', value: syncCount(result.current_plan_selected_count) },
    { label: 'Missing current plans', value: syncCount(result.current_plan_missing_count) },
    { label: 'Unmapped plans', value: syncCount(result.unmapped_treatment_plan_count) },
    { label: 'Unmapped reviews', value: syncCount(result.unmapped_treatment_review_count) },
    { label: 'Name fallback joins', value: syncCount(result.name_join_fallback_count) },
    { label: 'Detail fetch', value: result.detail_fetch_enabled ? 'Enabled' : 'Off' },
    { label: 'Detail attempts', value: syncCount(result.detail_fetch_attempt_count) },
    { label: 'Detail successes', value: syncCount(result.detail_fetch_success_count) },
    { label: 'Detail failures', value: syncCount(result.detail_fetch_failed_count) },
    { label: 'Detail skipped', value: syncCount(result.detail_fetch_skipped_count) },
  ]
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
  try {
    return JSON.parse(text)
  } catch {
    return { detail: response.ok ? '' : response.statusText, raw: text }
  }
}

export function App() {
  const explicitInitialViewRef = useRef(hasExplicitViewInUrl())
  const initialRoleViewAppliedRef = useRef(false)
  const [token, setToken] = useState(getStoredSessionToken)
  const [user, setUser] = useState<User | null>(null)
  const [status, setStatus] = useState('Sign in to upload notes, review findings, and manage approvals.')
  const [error, setError] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [settingsActivityLog, setSettingsActivityLog] = useState<string[]>([])
  const [mustResetPassword, setMustResetPassword] = useState(false)
  const [activeView, setActiveView] = useState<AppView>(viewFromUrl)
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null)
  const [localNow, setLocalNow] = useState(() => new Date())

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
  const [timelinessCriterionDirty, setTimelinessCriterionDirty] = useState(false)
  const [allevaPatientPlanPull, setAllevaPatientPlanPull] = useState<AllevaPatientPlanPullState>(() => createAllevaPatientPlanPullState())
  const [allevaPatientPlanInput, setAllevaPatientPlanInput] = useState(() => allevaPatientIdFromUrl())
  const [evidencePreview, setEvidencePreview] = useState<EvidencePreview | null>(null)
  const [appDialog, setAppDialog] = useState<AppDialogState | null>(null)
  const [confirmDialog, setConfirmDialog] = useState<ConfirmDialogState | null>(null)
  const [uploadForm, setUploadForm] = useState<UploadFormState>(createUploadForm())
  const [uploadProgress, setUploadProgress] = useState<UploadProgressState | null>(null)
  const [patientIdDetection, setPatientIdDetection] = useState<PatientIdDetection | null>(null)
  const [patientIdTouched, setPatientIdTouched] = useState(false)
  const [lastAutoFilledPatientId, setLastAutoFilledPatientId] = useState('')
  const [deleteNoteSetConfirmation, setDeleteNoteSetConfirmation] = useState('')
  const [deletingNoteSetId, setDeletingNoteSetId] = useState<number | null>(null)
  const uploadPatientIdRef = useRef('')
  const patientIdTouchedRef = useRef(false)
  const lastAutoFilledPatientIdRef = useRef('')
  const criterionWorkbenchRef = useRef<HTMLDivElement | null>(null)
  const allevaPatientPlanDeepLinkLoadedRef = useRef('')

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
  const [lastAllevaSyncResult, setLastAllevaSyncResult] = useState<AllevaTreatmentPlanSyncResult | null>(null)
  const [readiness, setReadiness] = useState<RuntimeReadiness | null>(null)
  const [emrProfile, setEmrProfile] = useState<EmrProfile | null>(null)
  const [emrEndpointProfiles, setEmrEndpointProfiles] = useState<EmrEndpointProfile[]>([])
  const [selectedEmrEndpointProfileId, setSelectedEmrEndpointProfileId] = useState<number | null>(null)
  const [emrEndpointProfileForm, setEmrEndpointProfileForm] = useState<EmrEndpointProfileForm>(createEmrEndpointProfileForm())
  const [treatmentPlanChecklist, setTreatmentPlanChecklist] = useState<TreatmentPlanChecklist | null>(null)
  const [reviewSourceDiscovery, setReviewSourceDiscovery] = useState<ReviewSourceDiscovery | null>(null)
  const [workflowDefinitions, setWorkflowDefinitions] = useState<WorkflowDefinition[]>([])
  const [selectedWorkflowDefinitionId, setSelectedWorkflowDefinitionId] = useState<number | null>(null)
  const [workflowDefinitionForm, setWorkflowDefinitionForm] = useState<WorkflowDefinitionForm>(createWorkflowDefinitionForm())
  const [workflowVersionForm, setWorkflowVersionForm] = useState<WorkflowVersionForm>(createWorkflowVersionForm())
  const [editingWorkflowVersionId, setEditingWorkflowVersionId] = useState<number | null>(null)

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
  const canRunAllevaTreatmentPlanSync = user?.role === 'admin'

  const selectedManagedUser = useMemo(
    () => users.find((candidate) => candidate.id === selectedManagedUserId) || null,
    [users, selectedManagedUserId],
  )
  const selectedWorkflowDefinition = useMemo(
    () => workflowDefinitions.find((definition) => definition.id === selectedWorkflowDefinitionId) || workflowDefinitions[0] || null,
    [selectedWorkflowDefinitionId, workflowDefinitions],
  )
  const selectedEmrEndpointProfile = useMemo(
    () => emrEndpointProfiles.find((profile) => profile.id === selectedEmrEndpointProfileId) || emrEndpointProfiles[0] || null,
    [emrEndpointProfiles, selectedEmrEndpointProfileId],
  )
  const selectedWorkflowDefinitionCanDelete = Boolean(
    selectedWorkflowDefinition &&
      selectedWorkflowDefinition.current_version_id == null &&
      selectedWorkflowDefinition.versions.every((version) => version.status === 'draft'),
  )
  const canManageUsers = user?.role === 'admin' || user?.role === 'manager'
  const canManageWorkflowProfiles = user?.role === 'admin' || user?.role === 'manager'
  const canManageSelectedUser = Boolean(user?.role === 'admin' || (user?.role === 'manager' && selectedManagedUser?.role === 'counselor'))
  const selectedManagedUserIsBootstrap = isBootstrapAdmin(selectedManagedUser)
  const selectedManagedUserIsCurrentUser = selectedManagedUser?.id === user?.id
  const selectedManagedUserCanDelete = Boolean(
    selectedManagedUser && canManageSelectedUser && !selectedManagedUserIsBootstrap && !selectedManagedUserIsCurrentUser,
  )

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
      const matchesStatus = timelinessStatusFilter === 'All' || statusToOperationalStatus(item.status) === timelinessStatusFilter
      const matchesQuery =
        !query ||
        item.patient_id.toLowerCase().includes(query) ||
        item.current_level_of_care.toLowerCase().includes(query) ||
        item.counselor_name.toLowerCase().includes(query)
      return matchesStatus && matchesQuery
    })
  }, [timelinessDashboard, timelinessSearch, timelinessStatusFilter])

  const timelinessStatusSummaries = useMemo(
    () => buildStatusSummaries(timelinessDashboardCounts(timelinessDashboard)),
    [timelinessDashboard],
  )
  const groupedTimelinessItems = useMemo(() => groupOperationalQueueItems(filteredTimelinessItems), [filteredTimelinessItems])
  const operationalStatusText = useMemo(() => operationalStatusSentence(timelinessStatusSummaries), [timelinessStatusSummaries])
  const sourceCards = useMemo(
    () =>
      sourceReadinessCards({
        reviewSourceDiscovery,
        appSettings,
        noteSets,
        readiness,
        lastAllevaSyncResult,
        canRunAllevaTreatmentPlanSync,
      }),
    [appSettings, canRunAllevaTreatmentPlanSync, lastAllevaSyncResult, noteSets, readiness, reviewSourceDiscovery],
  )
  const evidenceLedger = useMemo(
    () =>
      evidenceLedgerEntries({
        reviewSourceDiscovery,
        appSettings,
        noteSets,
        logs,
        lastAllevaSyncResult,
      }),
    [appSettings, lastAllevaSyncResult, logs, noteSets, reviewSourceDiscovery],
  )
  const selectedTreatmentTimeline = useMemo(
    () => (selectedTimelinessClient ? treatmentPlanTimelineSteps(selectedTimelinessClient) : []),
    [selectedTimelinessClient],
  )
  const selectedSourceComparisonRows = useMemo(
    () => (selectedTimelinessClient ? treatmentPlanSourceRows(selectedTimelinessClient) : []),
    [selectedTimelinessClient],
  )

  const exportableTimelinessTaskCount = useMemo(
    () => timelinessTaskItems(timelinessDashboard?.items || []).length,
    [timelinessDashboard],
  )

  const versionLabel = versionInfo
    ? `${versionPrefix(versionInfo)}${versionInfo.version}${versionInfo.environment ? ` · ${versionInfo.environment}` : ''}${versionInfo.git_commit && versionInfo.git_commit !== 'unknown' ? ` · ${versionInfo.git_commit}` : ''}`
    : 'Version unavailable'
  const timelinessBuildLabel = versionInfo?.version ? `${versionPrefix(versionInfo)}${versionInfo.version}` : 'current build'
  const lastAllevaSyncDiagnostics = useMemo(
    () => (lastAllevaSyncResult ? allevaSyncDiagnostics(lastAllevaSyncResult) : []),
    [lastAllevaSyncResult],
  )
  const localClockLabel = localNow.toLocaleString(undefined, {
    weekday: 'short',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })

  useEffect(() => {
    storeSessionToken(token)
  }, [token])

  useEffect(() => {
    const interval = window.setInterval(() => setLocalNow(new Date()), 60_000)
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const current = new URL(window.location.href)
    current.searchParams.set('view', activeView)
    window.history.replaceState(null, '', `${current.pathname}?${current.searchParams.toString()}`)
  }, [activeView])

  useEffect(() => {
    if (!evidencePreview && !appDialog && !confirmDialog) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (confirmDialog) {
        setConfirmDialog(null)
      } else if (appDialog) {
        setAppDialog(null)
      } else {
        setEvidencePreview(null)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [evidencePreview, appDialog, confirmDialog])

  useEffect(() => {
    if (error && user) {
      setAppDialog({ title: 'Action could not be completed', message: error })
    }
  }, [error, user])

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

  function appendSettingsActivity(message: string) {
    const timestamp = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    setSettingsActivityLog((current) => [`${timestamp} ${message}`, ...current].slice(0, 8))
  }

  async function apiRequest<T>(path: string, init?: RequestInit, includeAuth = true): Promise<T> {
    const headers = new Headers(init?.headers)
    if (includeAuth && token) headers.set('Authorization', `Bearer ${token}`)
    const response = await fetch(`${API}${path}`, { ...init, headers })
    const payload = (await readJson(response)) as ApiError | T | null
    if (!response.ok) {
      const isSessionExpired = response.status === 401 && includeAuth && Boolean(token)
      if (isSessionExpired) handleExpiredSession()
      throw new ApiRequestError(response.status, readErrorMessage(response.status, payload as ApiError | null, isSessionExpired))
    }
    return payload as T
  }

  function uploadPatientNoteSet(body: FormData, fileNames: string[], totalBytes: number): Promise<PatientNoteSetDetail> {
    if (import.meta.env.MODE === 'test' || typeof XMLHttpRequest === 'undefined') {
      setUploadProgress((current) =>
        current
          ? {
              ...current,
              phase: 'processing',
              percent: 100,
              loadedBytes: totalBytes,
              message: 'Upload received. Processing securely...',
            }
          : current,
      )
      return apiRequest<PatientNoteSetDetail>('/patient-note-sets', { method: 'POST', body })
    }

    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open('POST', `${API}/patient-note-sets`)
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)

      xhr.upload.onprogress = (event) => {
        const total = event.lengthComputable && event.total > 0 ? event.total : totalBytes
        const percent = total > 0 ? Math.min(99, Math.round((event.loaded / total) * 100)) : 0
        setUploadProgress({
          phase: 'uploading',
          percent,
          loadedBytes: event.loaded,
          totalBytes,
          fileCount: fileNames.length,
          fileNames,
          message: `Uploading ${fileNames.length} ${fileNames.length === 1 ? 'file' : 'files'}...`,
        })
      }

      xhr.upload.onload = () => {
        setUploadProgress({
          phase: 'processing',
          percent: 100,
          loadedBytes: totalBytes,
          totalBytes,
          fileCount: fileNames.length,
          fileNames,
          message: 'Upload received. Processing securely...',
        })
      }

      xhr.onerror = () => reject(new Error('The upload could not reach the local app. Confirm the app is still running and try again.'))
      xhr.onabort = () => reject(new Error('Upload was cancelled before it finished.'))
      xhr.onload = () => {
        let payload: ApiError | PatientNoteSetDetail | null = null
        try {
          payload = xhr.responseText ? (JSON.parse(xhr.responseText) as ApiError | PatientNoteSetDetail) : null
        } catch {
          reject(new Error('The local app returned a response that could not be read.'))
          return
        }

        if (xhr.status < 200 || xhr.status >= 300) {
          const isSessionExpired = xhr.status === 401 && Boolean(token)
          if (isSessionExpired) handleExpiredSession()
          reject(new ApiRequestError(xhr.status, readErrorMessage(xhr.status, payload as ApiError | null, isSessionExpired)))
          return
        }
        resolve(payload as PatientNoteSetDetail)
      }

      xhr.send(body)
    })
  }

  function safeButtonLabel(value: string) {
    return value
      .replace(/\s+/g, ' ')
      .replace(/\b(PAT|SYNTH|MRN|CLIENT|ID)[-_:A-Z0-9]{2,}\b/gi, '[id]')
      .trim()
      .slice(0, 120)
  }

  function changeView(view: AppView) {
    explicitInitialViewRef.current = true
    setActiveView(view)
  }

  function applyInitialRoleView(profile: User) {
    if (initialRoleViewAppliedRef.current) return
    initialRoleViewAppliedRef.current = true
    if (explicitInitialViewRef.current) return
    const nextView = defaultViewForRole(profile.role)
    if (nextView) setActiveView(nextView)
  }

  function clearWorkspaceState() {
    setUser(null)
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
    setTimelinessCriterionDirty(false)
    setEvidencePreview(null)
    setAppDialog(null)
    setConfirmDialog(null)
    setReadiness(null)
    setUsers([])
    setSelectedManagedUserId(null)
    setManagedUserForm(null)
    setLogs([])
    setAppSettings(null)
    setSettingsForm(null)
    setLastAllevaSyncResult(null)
    setEmrProfile(null)
    setEmrEndpointProfiles([])
    setSelectedEmrEndpointProfileId(null)
    setEmrEndpointProfileForm(createEmrEndpointProfileForm())
    setTreatmentPlanChecklist(null)
    setReviewSourceDiscovery(null)
    syncWorkflowDefinitions([])
    setUploadProgress(null)
    setDeleteNoteSetConfirmation('')
    setDeletingNoteSetId(null)
    setReviewDirty(false)
  }

  function handleExpiredSession() {
    storeSessionToken('')
    setToken('')
    setMustResetPassword(false)
    initialRoleViewAppliedRef.current = false
    explicitInitialViewRef.current = false
    setActiveView('dashboard')
    clearWorkspaceState()
    setStatus('Session expired. Sign in again to continue.')
    setError('')
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
    })
      .then((response) => {
        if (response.status === 401) handleExpiredSession()
      })
      .catch(() => undefined)
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
    setEditingWorkflowVersionId(null)
  }

  async function loadWorkflowDefinitions(preferredId?: number | null) {
    if (user?.role !== 'admin' && user?.role !== 'manager') return
    const payload = await apiRequest<WorkflowDefinition[]>('/workflow-definitions?include_archived=true')
    syncWorkflowDefinitions(payload, preferredId)
  }

  async function loadEmrEndpointProfiles(preferredId?: number | null) {
    if (user?.role !== 'admin') return
    const payload = await apiRequest<EmrEndpointProfile[]>('/emr/profiles')
    setEmrEndpointProfiles(payload)
    const selectedId = preferredId ?? selectedEmrEndpointProfileId ?? payload.find((profile) => profile.is_default)?.id ?? payload[0]?.id ?? null
    setSelectedEmrEndpointProfileId(selectedId)
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
    setStatus('Running the safe API readiness check...')
    appendSettingsActivity('Started safe API readiness check.')
    try {
      const payload = await apiRequest<ReviewSourceDiscovery>('/review-source-discovery/run-daily-check', { method: 'POST' })
      setReviewSourceDiscovery(payload)
      if (user?.role === 'admin') {
        const latestSettings = await apiRequest<AppSettings>('/settings')
        setAppSettings(latestSettings)
        setSettingsForm(createSettingsForm(latestSettings))
      }
      setStatus(`Safe API readiness check finished: ${payload.api_mode_label || payload.last_check_mode || payload.refresh_mode}.`)
      appendSettingsActivity(`API readiness check finished: ${payload.api_mode_label || payload.last_check_mode || payload.refresh_mode}.`)
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Failed to run safe API readiness check'
      appendSettingsActivity(`API readiness check failed: ${message}`)
      setError(message)
    } finally {
      setIsBusy(false)
    }
  }

  async function runAllevaTreatmentPlanSyncNow(options: { revealTimeliness?: boolean } = {}) {
    setIsBusy(true)
    setError('')
    setStatus('Running Alleva REST treatment-plan sync...')
    appendSettingsActivity('Started manual Alleva treatment-plan sync.')
    try {
      const payload = await apiRequest<AllevaTreatmentPlanSyncResponse>('/alleva/treatment-plan-sync/run', { method: 'POST' })
      setLastAllevaSyncResult(payload.sync_result)
      setAppSettings(payload.settings)
      setSettingsForm(createSettingsForm(payload.settings))
      await loadTimelinessDashboard()
      setStatus(payload.sync_result.message)
      if (payload.sync_result.status === 'fail' || payload.sync_result.status === 'blocked') {
        setError(payload.sync_result.message)
      } else if (options.revealTimeliness) {
        changeView('timeliness')
      }
      appendSettingsActivity(`Treatment-plan sync ${payload.sync_result.status}: ${payload.sync_result.message}`)
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Failed to run Alleva treatment-plan sync'
      appendSettingsActivity(`Treatment-plan sync failed: ${message}`)
      setError(message)
    } finally {
      setIsBusy(false)
    }
  }

  async function loadChartDetail(chartId: number, options: { skipDirtyCheck?: boolean } = {}) {
    if (!options.skipDirtyCheck && reviewDirty && selectedChartId !== chartId) {
      setConfirmDialog({
        title: 'Discard unsaved review changes?',
        message: 'The current criterion edits have not been saved. Keep editing, or discard them and open the selected chart.',
        confirmLabel: 'Discard changes',
        cancelLabel: 'Keep editing',
        onConfirm: () => {
          setConfirmDialog(null)
          setReviewDirty(false)
          void loadChartDetail(chartId, { skipDirtyCheck: true })
        },
      })
      return
    }
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
    setDeleteNoteSetConfirmation('')
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
    setTimelinessCriterionDirty(false)
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
      setTimelinessCriterionDirty(false)
    }
  }

  async function loadAllevaPatientCenteredTreatmentPlans(report: AllevaPatientCenteredTreatmentPlanReport, patientId = allevaPatientPlanInput) {
    const requestedPatientId = patientId.trim()
    if (report === 'single_patient_treatment_plans' && !requestedPatientId) {
      const message = 'patient_id is required before pulling single-patient production treatment plans.'
      setAllevaPatientPlanPull({ status: 'error', message, result: null, selectedPatientId: '' })
      setError(message)
      return
    }
    setIsBusy(true)
    setError('')
    setStatus('Loading Alleva patient-centered treatment-plan aggregate...')
    setAllevaPatientPlanPull({
      status: 'loading',
      message:
        report === 'single_patient_treatment_plans'
          ? `Loading single_patient_treatment_plans for patient_id ${requestedPatientId}...`
          : 'Loading active_patient_centered_treatment_plans...',
      result: null,
      selectedPatientId: requestedPatientId,
    })
    appendSettingsActivity(`Started ${report} quick pull.`)
    try {
      const config = await apiRequest<ApiConfigurationOut>('/api-configuration')
      const result = await apiRequest<AllevaPatientCenteredTreatmentPlanHarnessResult>('/api-configuration/alleva-quick-pull', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(allevaPatientCenteredTreatmentPlanPullPayload(config, report, requestedPatientId)),
      })
      const isError = result.status === 'fail'
      setAllevaPatientPlanPull({
        status: isError ? 'error' : 'ready',
        message: result.message || `${report} returned ${result.returned_count ?? result.rows?.length ?? 0} row(s).`,
        result,
        selectedPatientId: requestedPatientId,
      })
      setStatus(result.message || 'Alleva patient-centered treatment-plan pull completed.')
      if (isError) setError(result.message || 'Alleva patient-centered treatment-plan pull failed.')
      appendSettingsActivity(`${report} ${result.status}: ${result.message || 'completed'}`)
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Failed to load Alleva patient-centered treatment-plan aggregate'
      setAllevaPatientPlanPull({ status: 'error', message, result: null, selectedPatientId: requestedPatientId })
      setError(message)
      appendSettingsActivity(`${report} failed: ${message}`)
    } finally {
      setIsBusy(false)
    }
  }

  async function loadUsers(preferredId?: number | null) {
    if (user?.role !== 'admin' && user?.role !== 'manager') return
    const nextUsers = await apiRequest<User[]>('/users')
    setUsers(nextUsers)
    syncSelectedManagedUser(nextUsers, preferredId)
  }

  async function loadSettings() {
    if (user?.role !== 'admin') return
    const [payload, profile, endpointProfiles] = await Promise.all([
      apiRequest<AppSettings>('/settings'),
      apiRequest<EmrProfile>('/emr/profile'),
      apiRequest<EmrEndpointProfile[]>('/emr/profiles'),
    ])
    setAppSettings(payload)
    setSettingsForm(createSettingsForm(payload))
    setEmrProfile(profile)
    setEmrEndpointProfiles(endpointProfiles)
    setSelectedEmrEndpointProfileId((current) => current ?? endpointProfiles.find((endpointProfile) => endpointProfile.is_default)?.id ?? endpointProfiles[0]?.id ?? null)
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
      setStatus(`Workspace ready for ${profile.full_name || profile.username}.`)
      setProfileForm({ full_name: profile.full_name })
      applyInitialRoleView(profile)
      setCharts(chartList)
      setNoteSets(noteSetList)
      setReviewSourceDiscovery(sourceDiscovery)

      if (profile.role === 'admin') {
        const [directory, configuredSettings, runtimeReadiness, configuredEmrProfile, endpointProfiles, definitions] = await Promise.all([
          apiRequest<User[]>('/users'),
          apiRequest<AppSettings>('/settings'),
          apiRequest<RuntimeReadiness>('/system/readiness'),
          apiRequest<EmrProfile>('/emr/profile'),
          apiRequest<EmrEndpointProfile[]>('/emr/profiles'),
          apiRequest<WorkflowDefinition[]>('/workflow-definitions?include_archived=true'),
        ])
        setUsers(directory)
        syncSelectedManagedUser(directory, selectedManagedUserId)
        setAppSettings(configuredSettings)
        setSettingsForm(createSettingsForm(configuredSettings))
        setReadiness(runtimeReadiness)
        setEmrProfile(configuredEmrProfile)
        setEmrEndpointProfiles(endpointProfiles)
        setSelectedEmrEndpointProfileId((current) => current ?? endpointProfiles.find((endpointProfile) => endpointProfile.is_default)?.id ?? endpointProfiles[0]?.id ?? null)
        syncWorkflowDefinitions(definitions, selectedWorkflowDefinitionId)
      } else if (profile.role === 'manager') {
        setNewUserForm((current) => ({ ...current, role: 'counselor' }))
        const [directory, definitions] = await Promise.all([
          apiRequest<User[]>('/users'),
          apiRequest<WorkflowDefinition[]>('/workflow-definitions?include_archived=true'),
        ])
        setUsers(directory)
        syncSelectedManagedUser(directory, selectedManagedUserId)
        setAppSettings(null)
        setSettingsForm(null)
        setReadiness(null)
        setEmrProfile(null)
        setEmrEndpointProfiles([])
        setSelectedEmrEndpointProfileId(null)
        syncWorkflowDefinitions(definitions, selectedWorkflowDefinitionId)
      } else {
        setUsers([])
        setSelectedManagedUserId(null)
        setManagedUserForm(null)
        setAppSettings(null)
        setSettingsForm(null)
        setReadiness(null)
        setEmrProfile(null)
        setEmrEndpointProfiles([])
        setSelectedEmrEndpointProfileId(null)
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
      if (caught instanceof ApiRequestError && caught.status === 401) {
        handleExpiredSession()
        return
      }
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
    if (activeView === 'users' && token && (user?.role === 'admin' || user?.role === 'manager') && !mustResetPassword) {
      void loadUsers()
    }
  }, [activeView, token, user, mustResetPassword])

  useEffect(() => {
    if (activeView === 'workflows' && token && (user?.role === 'admin' || user?.role === 'manager') && !mustResetPassword) {
      void loadWorkflowDefinitions(selectedWorkflowDefinitionId)
    }
  }, [activeView, token, user, mustResetPassword])

  useEffect(() => {
    if (activeView === 'timeliness' && token && user && !mustResetPassword) {
      void loadTimelinessDashboard()
    }
  }, [activeView, token, user, mustResetPassword])

  useEffect(() => {
    if ((activeView === 'dashboard' || activeView === 'sources') && token && user && !mustResetPassword) {
      void loadTimelinessDashboard().catch(() => {
        setTimelinessDashboard(null)
      })
    }
  }, [activeView, token, user, mustResetPassword])

  useEffect(() => {
    if (activeView !== 'timeliness' || !token || user?.role !== 'admin' || mustResetPassword) return
    const patientId = allevaPatientIdFromUrl()
    if (!patientId || allevaPatientPlanDeepLinkLoadedRef.current === patientId) return
    allevaPatientPlanDeepLinkLoadedRef.current = patientId
    setAllevaPatientPlanInput(patientId)
    void loadAllevaPatientCenteredTreatmentPlans('single_patient_treatment_plans', patientId)
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
    setAppDialog(null)
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
      const profile = await apiRequest<User>('/users/me', { headers: { Authorization: `Bearer ${login.access_token}` } }, false)
      storeSessionToken(login.access_token)
      setToken(login.access_token)
      setMustResetPassword(login.must_reset_password)
      setUser(profile)
      setProfileForm({ full_name: profile.full_name })
      if (login.must_reset_password) {
        setStatus('Password reset required before continuing.')
      } else {
        applyInitialRoleView(profile)
        setStatus(`Signed in as ${profile.full_name || profile.username}. Loading workspace...`)
      }
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.status === 401) {
        setStatus('Sign in failed. Check the username and password.')
      }
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
    const uploadFileNames = uploadForm.entries.map((entry) => entry.file.name)
    const uploadTotalBytes = uploadForm.entries.reduce((total, entry) => total + entry.file.size, 0)
    setUploadProgress({
      phase: 'uploading',
      percent: 0,
      loadedBytes: 0,
      totalBytes: uploadTotalBytes,
      fileCount: uploadForm.entries.length,
      fileNames: uploadFileNames,
      message: `Preparing ${uploadForm.entries.length} ${uploadForm.entries.length === 1 ? 'file' : 'files'}...`,
    })

    try {
      const body = new FormData()
      body.set('patient_id', uploadForm.patient_id)
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
            source_attachment_url: entry.source_attachment_url,
            source_author: entry.source_author,
            source_custodian: entry.source_custodian,
            source_security_label: entry.source_security_label,
          })),
        ),
      )
      uploadForm.entries.forEach((entry) => body.append('files', entry.file))

      const uploaded = await uploadPatientNoteSet(body, uploadFileNames, uploadTotalBytes)

      setUploadForm(
        createUploadForm({
          patient_id: uploaded.patient_id,
          client_name: '',
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
      changeView('reviews')
      await loadWorkspace()
      if (uploaded.review_chart_id) {
        await loadChartDetail(uploaded.review_chart_id)
      }
      setStatus(`Clinical notes uploaded for patient ${uploaded.patient_id}. The system review is ready for office-manager disposition.`)
    } catch (caught) {
      if (caught instanceof ApiRequestError && caught.status === 401) {
        handleExpiredSession()
        return
      }
      setError(caught instanceof Error ? caught.message : 'Upload failed')
    } finally {
      setUploadProgress(null)
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
        const isSessionExpired = response.status === 401 && Boolean(token)
        if (isSessionExpired) handleExpiredSession()
        throw new Error(readErrorMessage(response.status, payload, isSessionExpired))
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

  async function deleteSelectedNoteSet() {
    if (!selectedNoteSet) return
    if (deleteNoteSetConfirmation.trim() !== selectedNoteSet.patient_id) {
      setError('Type the patient ID exactly before deleting this uploaded binder.')
      return
    }

    const deletedPatientId = selectedNoteSet.patient_id
    const deletedVersion = selectedNoteSet.version
    setDeletingNoteSetId(selectedNoteSet.id)
    setIsBusy(true)
    setError('')
    try {
      await apiRequest(`/patient-note-sets/${selectedNoteSet.id}`, { method: 'DELETE' })
      setSelectedNoteSet(null)
      setSelectedNoteSetId(null)
      setSelectedChart(null)
      setSelectedChartId(null)
      setDeleteNoteSetConfirmation('')
      await loadWorkspace()
      setStatus(`Deleted uploaded binder version ${deletedVersion} for patient ${deletedPatientId}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to delete uploaded binder')
    } finally {
      setDeletingNoteSetId(null)
      setIsBusy(false)
    }
  }

  function activeTreatmentPlanWorkflow() {
    return (
      workflowDefinitions.find((definition) => definition.workflow_key === 'treatment_plan_timeliness') ||
      workflowDefinitions.find((definition) => definition.category === 'treatment_plan') ||
      selectedWorkflowDefinition ||
      null
    )
  }

  function workflowStepsForExport(chart: ChartDetail | null, client: TimelinessClientDetail | null) {
    const workflow = activeTreatmentPlanWorkflow()
    if (client?.checklist_results?.length) {
      return client.checklist_results.map((result) => ({
        row_type: 'checklist_result',
        workflow_key: workflow?.workflow_key || 'treatment_plan_timeliness',
        workflow_version: workflow?.current_version?.version || null,
        checklist_version: client.checklist_version || treatmentPlanChecklist?.version || workflow?.current_version?.definition_snapshot?.checklist_version || '',
        step: result.step,
        key: result.key,
        label: result.title,
        status: result.status,
        source_evidence: result.source_evidence,
        finding_message: result.finding_message,
        evaluated_values: evaluatedValuesSummary(result.evaluated_values),
        severity: result.severity,
        reviewer_action: result.reviewer_actions.join('; '),
        override_reason: '',
      }))
    }
    const rawSteps = workflow?.current_version?.definition_snapshot?.steps
    const checklistSteps = Array.isArray(rawSteps) && rawSteps.length ? rawSteps : treatmentPlanChecklist?.steps || []
    const chartResponses = new Map((chart?.checklist_items || []).map((item) => [item.item_key, item]))
    const ruleResults = client?.rule_results || []
    const hasRuleStatus = (rulePrefix: string) => ruleResults.find((result) => result.rule_id.startsWith(rulePrefix))?.status
    const evidenceSummary = [client?.source_evidence, client?.evidence_comparison?.source_evidence].filter(Boolean).join('; ')

    return checklistSteps.map((rawStep, index) => {
      const step = rawStep as Partial<TreatmentPlanChecklistStep> & { label?: string }
      const key = String(step.key || `workflow_step_${index + 1}`)
      const chartResponse = chartResponses.get(key)
      let status = chartResponse ? STATUS_LABELS[chartResponse.status] : 'not_reviewed'
      let sourceEvidence = chartResponse?.evidence_location || evidenceSummary
      let finding = chartResponse?.notes || ''

      if (!chartResponse && client) {
        if (key.includes('admission')) {
          status = client.admission_date ? 'passed' : 'missing_data'
          sourceEvidence = client.admission_date ? `Admission date ${client.admission_date}; ${client.source_evidence}` : client.source_evidence
        } else if (key.includes('current_loc') || key.includes('loc_mapping') || key.includes('level_of_care')) {
          status = client.current_level_of_care ? 'passed' : 'missing_data'
          sourceEvidence = client.current_level_of_care ? `Current LOC ${client.current_level_of_care}; ${client.source_evidence}` : client.source_evidence
        } else if (key.includes('latest_review') || key.includes('next_due') || key.includes('interval') || key.includes('overdue') || key.includes('due_soon')) {
          status = client.status
          sourceEvidence = client.evidence_summary || client.evidence_comparison?.source_evidence || client.source_evidence
          finding = client.rule_used
        } else if (key.includes('loc_change')) {
          status = hasRuleStatus('TP-LOC-CHANGE') || (client.evidence_comparison?.loc_change_due_date ? client.status : 'not_reviewed')
          sourceEvidence = client.evidence_comparison?.source_evidence || client.source_evidence
          finding = client.evidence_comparison?.conflict_explanation || ''
        } else if (key.includes('missing_data')) {
          status = client.missing_evidence_fields.length ? 'missing_data' : 'passed'
          finding = client.missing_evidence_fields.join(', ')
        } else if (key.includes('final') || key.includes('worklist') || key.includes('approval')) {
          status = chart?.state || client.status
          sourceEvidence = chart?.system_summary || client.evidence_summary
        }
      }

      return {
        row_type: 'workflow_step',
        workflow_key: workflow?.workflow_key || 'treatment_plan_timeliness',
        workflow_version: workflow?.current_version?.version || null,
        checklist_version: treatmentPlanChecklist?.version || workflow?.current_version?.definition_snapshot?.checklist_version || '',
        step: Number(step.step || index + 1),
        key,
        label: String(step.title || step.label || key),
        status,
        source_evidence: sourceEvidence || '',
        finding_message: finding,
        evaluated_values: '',
        severity: String(step.severity_default || ''),
        reviewer_action: '',
        override_reason: '',
      }
    })
  }

  function safeTreatmentPlanForExport(plan: TimelinessTreatmentPlan) {
    const contentItems = safeContentItems(plan.content_items)
    return {
      id: plan.id,
      plan_kind: plan.plan_kind,
      document_date: plan.document_date,
      staff_signature_date: plan.staff_signature_date,
      client_signature_date: plan.client_signature_date,
      reviewer_signature_date: plan.reviewer_signature_date,
      displayed_next_due_date: plan.displayed_next_due_date,
      source_evidence: plan.source_evidence,
      source_section: plan.source_section,
      is_valid: plan.is_valid,
      conflict_note: plan.conflict_note,
      plan_field_count: plan.plan_field_count ?? contentItems.filter((item) => item.kind === 'plan_field').length,
      problem_count: plan.problem_count ?? 0,
      diagnosis_count: plan.diagnosis_count ?? 0,
      behavioral_definition_count: plan.behavioral_definition_count ?? 0,
      goal_count: plan.goal_count ?? 0,
      objective_count: plan.objective_count ?? 0,
      intervention_count: plan.intervention_count ?? 0,
      has_guardian_signature: Boolean(plan.has_guardian_signature),
      guardian_signature_date: plan.guardian_signature_date || '',
      alleva_is_active: Boolean(plan.alleva_is_active),
      alleva_is_complete: Boolean(plan.alleva_is_complete),
      alleva_is_initial_tp: Boolean(plan.alleva_is_initial_tp),
      alleva_start_date: plan.alleva_start_date || '',
      alleva_end_date: plan.alleva_end_date || '',
      alleva_last_modified: plan.alleva_last_modified || '',
      detail_fetched: Boolean(plan.detail_fetched),
      detail_fetched_at: plan.detail_fetched_at || null,
      content_source: plan.content_source || '',
      content_capture_status: plan.content_capture_status || '',
      content_capture_warnings: plan.content_capture_warnings || '',
      content_items: contentItems,
      content_tree: safeContentTree(plan.content_items),
      is_current: Boolean(plan.is_current),
    }
  }

  function safeTimelinessClientForExport(client: TimelinessClientDetail) {
    return {
      id: client.id,
      patient_id: client.patient_id,
      is_active: client.is_active,
      current_level_of_care: client.current_level_of_care,
      counselor_name: client.counselor_name,
      admission_date: client.admission_date,
      last_valid_review_date: client.last_valid_review_date,
      next_due_date: client.next_due_date,
      days_until_due: client.days_until_due,
      current_date: client.current_date,
      status: client.status,
      rule_used: client.rule_used,
      evidence_summary: client.evidence_summary,
      evidence_completeness_percent: client.evidence_completeness_percent,
      missing_evidence_fields: client.missing_evidence_fields,
      data_quality_warnings: client.data_quality_warnings || [],
      id_join_confidence: client.id_join_confidence || 'unknown',
      source_confidence: client.source_confidence || client.id_join_confidence || 'unknown',
      source_endpoint_count: client.source_endpoint_count || 0,
      last_checked_at: client.last_checked_at,
      last_imported_at: client.last_imported_at,
      source_evidence: client.source_evidence,
      checklist_id: client.checklist_id,
      checklist_version: client.checklist_version,
      evidence_comparison: client.evidence_comparison,
      rule_results: client.rule_results,
      checklist_results: client.checklist_results,
      level_of_care_history: client.level_of_care_history,
      treatment_plans: client.treatment_plans.map(safeTreatmentPlanForExport),
    }
  }

  function treatmentPlanContentRowsForExport(client: TimelinessClientDetail) {
    return client.treatment_plans.flatMap((plan) => {
      const contentItems = safeContentItems(plan.content_items)
      const planRows = [
        [
          'treatment_plan_content_summary',
          String(plan.id),
          planKindLabel(plan.plan_kind),
          plan.content_capture_status || 'counts_only',
          plan.displayed_next_due_date || '',
          plan.source_section || plan.source_evidence || '',
          `plan_fields=${plan.plan_field_count ?? contentItems.filter((item) => item.kind === 'plan_field').length}; problems=${plan.problem_count ?? 0}; behavioral_definitions=${plan.behavioral_definition_count ?? 0}; diagnoses=${plan.diagnosis_count ?? 0}; goals=${plan.goal_count ?? 0}; objectives=${plan.objective_count ?? 0}; interventions=${plan.intervention_count ?? 0}`,
          plan.content_capture_warnings || '',
        ],
      ]
      const itemRows = contentItems.map((item) => [
        'treatment_plan_content_fact',
        String(plan.id),
        item.label || item.kind,
        item.kind,
        item.source_path || '',
        plan.source_section || plan.source_evidence || '',
        contentItemMetadataSummary(item),
        item.text || (item.text_present ? 'text value redacted or unavailable' : ''),
      ])
      return [...planRows, ...itemRows]
    })
  }

  function exportSelectedChart(format: 'json' | 'csv') {
    if (!selectedChart) {
      setError('Select a review before exporting a report.')
      return
    }
    const safePatientId = selectedChart.patient_id.replace(/[^a-z0-9_-]+/gi, '-')
    const checklistVersion = treatmentPlanChecklist?.version || 'Not loaded'
    const linkedTimelinessClient =
      selectedTimelinessClient?.patient_id === selectedChart.patient_id ? selectedTimelinessClient : null
    const workflowSteps = workflowStepsForExport(selectedChart, linkedTimelinessClient)
    if (format === 'json') {
      downloadTextFile(
        `review-report-${safePatientId}.json`,
        JSON.stringify(
          {
            report_type: 'chart_review',
            checklist_id: treatmentPlanChecklist?.checklist_id || 'treatment-plan-v1',
            checklist_version: checklistVersion,
            generated_at: new Date().toISOString(),
            local_clock_at_export: localNow.toISOString(),
            chart: selectedChart,
            workflow_steps: workflowSteps,
          },
          null,
          2,
        ),
        'application/json',
      )
    } else {
      const header = ['row_type', 'step', 'section_or_key', 'label', 'status', 'notes_or_finding', 'evaluated_values', 'evidence_location', 'evidence_date', 'expiration_date', 'instructions_or_severity']
      const checklistRows = selectedChart.checklist_items.map((item) =>
        ['checklist_domain', item.step, item.section, item.label, STATUS_LABELS[item.status], item.notes, item.evidence_location, item.evidence_date, item.expiration_date, item.instructions]
          .map(csvCell)
          .join(','),
      )
      const workflowRows = workflowSteps.map((item) =>
        [item.row_type, item.step, item.key, item.label, item.status, item.finding_message, item.evaluated_values, item.source_evidence, '', '', item.severity].map(csvCell).join(','),
      )
      downloadTextFile(`review-report-${safePatientId}.csv`, [header.map(csvCell).join(','), ...checklistRows, ...workflowRows].join('\n'), 'text/csv')
    }
    setStatus(`Exported review report for patient ${selectedChart.patient_id}.`)
  }

  function exportSelectedTimeliness(format: 'json' | 'csv') {
    if (!selectedTimelinessClient) {
      setError('Select a treatment-plan item before exporting a report.')
      return
    }
    const safePatientId = selectedTimelinessClient.patient_id.replace(/[^a-z0-9_-]+/gi, '-')
    const checklistVersion = selectedTimelinessClient.checklist_version || treatmentPlanChecklist?.version || 'Not loaded'
    const workflowSteps = workflowStepsForExport(null, selectedTimelinessClient)
    if (format === 'json') {
      downloadTextFile(
        `treatment-plan-report-${safePatientId}.json`,
        JSON.stringify(
          {
            report_type: 'treatment_plan_timeliness',
            checklist_id: treatmentPlanChecklist?.checklist_id || 'treatment-plan-v1',
            checklist_version: checklistVersion,
            generated_at: new Date().toISOString(),
            local_clock_at_export: localNow.toISOString(),
            client: safeTimelinessClientForExport(selectedTimelinessClient),
            checklist_results: selectedTimelinessClient.checklist_results,
            workflow_steps: workflowSteps,
          },
          null,
          2,
        ),
        'application/json',
      )
    } else {
      const header = ['row_type', 'id_or_step', 'label', 'status', 'due_date_or_key', 'evidence_summary_or_source', 'finding_or_rule', 'evaluated_values']
      const sourceRows = [
        [
          'source_metadata',
          selectedTimelinessClient.id,
          'Alleva source confidence',
          selectedTimelinessClient.source_confidence || selectedTimelinessClient.id_join_confidence || 'unknown',
          'source_endpoint_count',
          selectedTimelinessClient.source_evidence,
          selectedTimelinessClient.rule_used,
          JSON.stringify({
            source_endpoint_count: selectedTimelinessClient.source_endpoint_count || 0,
            data_quality_warnings: selectedTimelinessClient.data_quality_warnings || [],
          }),
        ]
          .map(csvCell)
          .join(','),
      ]
      const rows = selectedTimelinessClient.rule_results.map((result) =>
        ['timeliness_rule', result.rule_id, result.label, result.status, result.due_date || '', result.evidence_summary, result.rule_id, ''].map(csvCell).join(','),
      )
      const workflowRows = workflowSteps.map((item) =>
        [item.row_type, item.step, item.label, item.status, item.key, item.source_evidence, item.finding_message, item.evaluated_values].map(csvCell).join(','),
      )
      const contentRows = treatmentPlanContentRowsForExport(selectedTimelinessClient).map((item) => item.map(csvCell).join(','))
      downloadTextFile(
        `treatment-plan-report-${safePatientId}.csv`,
        [header.map(csvCell).join(','), ...sourceRows, ...rows, ...workflowRows, ...contentRows].join('\n'),
        'text/csv',
      )
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
      subtitle: selectedTimelinessClient.patient_id,
      fields: [
        { label: 'Current date used', value: displayDate(comparison.current_date), emphasis: true },
        { label: 'Date-clock anchor', value: `${displayDate(comparison.date_clock_anchor_date)} (${comparison.date_clock_anchor_source || 'not selected'})`, emphasis: true },
        { label: 'Date clock due date', value: displayDate(comparison.date_clock_due_date), emphasis: true },
        { label: 'Source-document Next Review Due', value: displayDate(comparison.document_next_due_date), emphasis: true },
        { label: 'Staff signature date', value: displayDate(comparison.staff_signature_date), emphasis: true },
        { label: 'Review/admission anchor + LOC cadence', value: displayDate(comparison.signature_anchor_due_date) },
        { label: 'Current LOC effective date', value: displayDate(comparison.loc_effective_date), emphasis: true },
        { label: 'LOC-change due date', value: displayDate(comparison.loc_change_due_date || comparison.loc_anchor_due_date) },
        { label: 'Cadence interval', value: comparison.interval_days == null ? 'Not configured' : `${comparison.interval_days} days` },
        { label: 'LOC-change window', value: comparison.loc_change_window_days == null ? 'Not configured' : `${comparison.loc_change_window_days} days` },
        { label: 'Source evidence', value: comparison.source_evidence || selectedTimelinessClient.source_evidence || 'Not recorded' },
      ],
      note: comparison.conflict_explanation || 'No due-date comparison detail is available.',
    })
  }

  function openPlanEvidence(plan: TimelinessTreatmentPlan) {
    const capturedFacts = safeContentItems(plan.content_items)
    const capturedTree = safeContentTree(plan.content_items)
    const planFieldCount = plan.plan_field_count ?? capturedTree.plan_fields.length
    const contentTotal =
      planFieldCount +
      (plan.problem_count ?? 0) +
      (plan.behavioral_definition_count ?? 0) +
      (plan.diagnosis_count ?? 0) +
      (plan.goal_count ?? 0) +
      (plan.objective_count ?? 0) +
      (plan.intervention_count ?? 0)
    const nestedProblemCount = capturedTree.problems.length
    const factPreview = capturedFacts
      .map((item) => {
        const metadata = contentItemMetadataSummary(item)
        const details = [item.text, metadata !== 'No metadata' ? metadata : '', item.source_path].filter(Boolean).join(' | ')
        return `${item.label}: ${details || item.source_path}`
      })
      .join(' | ')
    setEvidencePreview({
      title: `${planKindLabel(plan.plan_kind)} treatment-plan evidence`,
      subtitle: plan.source_section || plan.source_evidence || 'Treatment plan source',
      fields: [
        { label: 'Document date', value: displayDate(plan.document_date) },
        { label: 'Staff / therapist signature', value: signedLabel(plan.staff_signature_date), emphasis: true },
        { label: 'Client signature', value: plan.client_signature_date || (plan.plan_kind === 'review' ? 'Optional for ongoing reviews' : 'Missing') },
        { label: 'Reviewer signature', value: displayDate(plan.reviewer_signature_date) },
        { label: 'Displayed Next Review Due', value: displayDate(plan.displayed_next_due_date), emphasis: Boolean(plan.displayed_next_due_date) },
        { label: 'Current plan selected', value: plan.is_current ? 'Yes' : 'No' },
        { label: 'Detail fetch status', value: plan.detail_fetched ? 'Loaded from detail endpoint' : 'Not loaded' },
        { label: 'Treatment-plan elements', value: String(contentTotal), emphasis: contentTotal > 0 },
        { label: 'Structured content facts', value: `${capturedFacts.length}`, emphasis: capturedFacts.length > 0 },
        { label: 'Plan fields', value: `${planFieldCount}`, emphasis: planFieldCount > 0 },
        { label: 'Plan tree problems', value: `${nestedProblemCount}`, emphasis: nestedProblemCount > 0 },
        { label: 'Content capture status', value: plan.content_capture_status || 'counts_only' },
        { label: 'Problems / definitions / diagnoses', value: `${plan.problem_count ?? 0} / ${plan.behavioral_definition_count ?? 0} / ${plan.diagnosis_count ?? 0}` },
        { label: 'Goals / objectives / interventions', value: `${plan.goal_count ?? 0} / ${plan.objective_count ?? 0} / ${plan.intervention_count ?? 0}` },
        { label: 'Alleva lifecycle', value: plan.alleva_is_active ? 'Active' : plan.alleva_end_date ? `Ended ${plan.alleva_end_date}` : 'Not recorded' },
        { label: 'Guardian signature', value: plan.has_guardian_signature ? `Present${plan.guardian_signature_date ? ` (${plan.guardian_signature_date})` : ''}` : 'Not recorded' },
        { label: 'Source document ID', value: plan.source_document_id || 'Not recorded' },
        { label: 'Source evidence', value: plan.source_evidence || 'Not recorded' },
        { label: 'Captured fact preview', value: factPreview || 'No structured facts captured' },
      ],
      note: plan.conflict_note || plan.content_capture_warnings || 'Evidence preview shows structured treatment-plan values after direct-identifier redaction.',
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
        body: JSON.stringify({ ...newUserForm, role: user?.role === 'manager' ? 'counselor' : newUserForm.role }),
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
    if (!canManageSelectedUser) {
      setError('This account is outside your user-management scope.')
      return
    }
    setIsBusy(true)
    setError('')
    try {
      const updated = await apiRequest<User>(`/users/${selectedManagedUser.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...managedUserForm, role: user?.role === 'manager' ? 'counselor' : managedUserForm.role }),
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
    if (!canManageSelectedUser) {
      setError('This account is outside your user-management scope.')
      return
    }
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
    if (!selectedManagedUserCanDelete) {
      setError('This account cannot be deleted from your current role or while linked history exists.')
      return
    }
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
    const hasStoredApiSecret = Boolean(appSettings?.api_client_secret_configured && !settingsForm.clear_api_client_secret)
    const hasApiSecret = Boolean(settingsForm.api_client_secret.trim() || hasStoredApiSecret)
    const hasStoredLlmKey = Boolean(appSettings?.llm_api_key_configured && !settingsForm.clear_llm_api_key)
    const hasLlmKey = Boolean(settingsForm.llm_api_key.trim() || hasStoredLlmKey)
    if (settingsForm.llm_enabled && (!settingsForm.llm_base_url.trim() || !settingsForm.llm_model.trim() || !hasLlmKey)) {
      setError('To enable LLM analysis, enter the LLM base URL, model, and API key, or keep the existing stored key.')
      return
    }
    if (settingsForm.emr_api_enabled) {
      const missingFields = [
        !settingsForm.alleva_api_base_url.trim() ? 'Alleva REST API base URL' : '',
        !settingsForm.alleva_openapi_url.trim() ? 'Alleva OpenAPI URL' : '',
        !settingsForm.api_oauth_token_url.trim() ? 'OAuth token URL' : '',
        !settingsForm.api_client_id.trim() ? 'API client ID' : '',
        !hasApiSecret ? 'API client secret' : '',
      ].filter(Boolean)
      if (missingFields.length) {
        setError(`Missing API setting(s): ${missingFields.join(', ')}.`)
        return
      }
    }
    if (settingsForm.emr_periodic_check_enabled) {
      const missingFields = [
        !settingsForm.alleva_api_base_url.trim() ? 'REST API base URL' : '',
        !settingsForm.alleva_openapi_url.trim() ? 'OpenAPI URL' : '',
        !settingsForm.api_oauth_token_url.trim() ? 'OAuth token URL' : '',
        !settingsForm.api_client_id.trim() ? 'API client ID' : '',
        !hasApiSecret ? 'API client secret' : '',
      ].filter(Boolean)
      if (missingFields.length) {
        setError(`Missing periodic API check setting(s): ${missingFields.join(', ')}.`)
        return
      }
    }
    if (settingsForm.alleva_treatment_plan_sync_enabled || settingsForm.alleva_treatment_plan_sync_on_startup) {
      const missingFields = [
        !settingsForm.alleva_api_base_url.trim() ? 'Alleva REST API base URL' : '',
        !settingsForm.api_oauth_token_url.trim() ? 'Alleva OAuth token URL' : '',
        !settingsForm.api_client_id.trim() ? 'Alleva API client ID' : '',
        !hasApiSecret ? 'Alleva API client secret' : '',
        !settingsForm.alleva_treatment_plan_sync_approved ? 'R3/Alleva live treatment-plan sync approval' : '',
        !settingsForm.alleva_treatment_plan_endpoint_mapping_validated ? 'validated Alleva treatment-plan endpoint mapping' : '',
      ].filter(Boolean)
      if (missingFields.length) {
        setError(`Missing Alleva treatment-plan sync setting(s): ${missingFields.join(', ')}.`)
        return
      }
    }
    if (settingsForm.treatment_plan_loc_change_window_validated && settingsForm.treatment_plan_loc_change_window_days == null) {
      setError('Missing treatment-plan setting: LOC-change update window days.')
      return
    }
    setIsBusy(true)
    setError('')
    appendSettingsActivity('Saving App settings.')
    try {
      const payload = await apiRequest<AppSettings>('/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settingsForm),
      })
      const verifiedSettings = await apiRequest<AppSettings>('/settings')
      setAppSettings(verifiedSettings)
      setSettingsForm(createSettingsForm(verifiedSettings))
      setEmrProfile(await apiRequest<EmrProfile>('/emr/profile'))
      setStatus('Application settings have been saved and verified.')
      appendSettingsActivity(
        `App settings saved and verified. API client ${verifiedSettings.api_client_id ? 'stored' : 'missing'}, secret ${
          verifiedSettings.api_client_secret_configured ? 'configured' : 'missing'
        }.`,
      )
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Failed to update application settings'
      appendSettingsActivity(`App settings save failed: ${message}`)
      setError(message)
    } finally {
      setIsBusy(false)
    }
  }

  async function handleCreateEmrEndpointProfile(event?: FormEvent) {
    event?.preventDefault()
    setIsBusy(true)
    setError('')
    appendSettingsActivity('Saving endpoint profile preset.')
    try {
      const created = await apiRequest<EmrEndpointProfile>('/emr/profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(emrEndpointProfileForm),
      })
      setEmrEndpointProfileForm(createEmrEndpointProfileForm())
      await loadEmrEndpointProfiles(created.id)
      setStatus(`Stored EMR endpoint profile ${created.display_name}.`)
      appendSettingsActivity(`Endpoint profile saved: ${created.display_name}.`)
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Failed to create EMR endpoint profile'
      appendSettingsActivity(`Endpoint profile save failed: ${message}`)
      setError(message)
    } finally {
      setIsBusy(false)
    }
  }

  async function activateEmrEndpointProfile(profileId: number) {
    setIsBusy(true)
    setError('')
    appendSettingsActivity('Activating endpoint profile preset.')
    try {
      const updatedSettings = await apiRequest<AppSettings>(`/emr/profiles/${profileId}/activate`, { method: 'POST' })
      setAppSettings(updatedSettings)
      setSettingsForm(createSettingsForm(updatedSettings))
      await loadEmrEndpointProfiles(profileId)
      setEmrProfile(await apiRequest<EmrProfile>('/emr/profile'))
      setStatus('Endpoint profile copied into the active App settings API connection.')
      appendSettingsActivity('Endpoint profile copied into active API settings.')
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Failed to activate EMR endpoint profile'
      appendSettingsActivity(`Endpoint profile activation failed: ${message}`)
      setError(message)
    } finally {
      setIsBusy(false)
    }
  }

  async function deleteEmrEndpointProfile(profileId: number) {
    setIsBusy(true)
    setError('')
    appendSettingsActivity('Deleting endpoint profile preset.')
    try {
      const deleted = await apiRequest<{ status: string; profile_key: string }>(`/emr/profiles/${profileId}`, { method: 'DELETE' })
      await loadEmrEndpointProfiles(null)
      setStatus(`Deleted EMR endpoint profile ${deleted.profile_key}.`)
      appendSettingsActivity(`Endpoint profile deleted: ${deleted.profile_key}.`)
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : 'Failed to delete EMR endpoint profile'
      appendSettingsActivity(`Endpoint profile delete failed: ${message}`)
      setError(message)
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
      if (editingWorkflowVersionId) {
        await apiRequest<WorkflowDefinitionVersion>(`/workflow-definitions/${selectedWorkflowDefinition.id}/versions/${editingWorkflowVersionId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(versionPayload),
        })
        await loadWorkflowDefinitions(selectedWorkflowDefinition.id)
        setStatus(`Draft workflow version updated for ${selectedWorkflowDefinition.workflow_key}.`)
      } else {
        await apiRequest<WorkflowDefinitionVersion>(`/workflow-definitions/${selectedWorkflowDefinition.id}/versions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(versionPayload),
        })
        await loadWorkflowDefinitions(selectedWorkflowDefinition.id)
        setStatus(`Draft workflow version created for ${selectedWorkflowDefinition.workflow_key}.`)
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : editingWorkflowVersionId ? 'Failed to update workflow version' : 'Failed to create workflow version')
    } finally {
      setIsBusy(false)
    }
  }

  function loadWorkflowVersionForEditing(version: WorkflowDefinitionVersion) {
    setWorkflowVersionForm({
      version_notes: version.version_notes,
      definition_snapshot_text: JSON.stringify(version.definition_snapshot, null, 2),
      transition_rules_text: JSON.stringify(version.transition_rules, null, 2),
    })
    if (version.status === 'draft') {
      setEditingWorkflowVersionId(version.id)
      setStatus(`Draft workflow version ${version.version} loaded for editing.`)
    } else {
      setEditingWorkflowVersionId(null)
      setStatus(`Published workflow version ${version.version} loaded as a new draft template.`)
    }
  }

  function clearWorkflowVersionEditor() {
    setWorkflowVersionForm(createWorkflowVersionForm(selectedWorkflowDefinition))
    setEditingWorkflowVersionId(null)
    setStatus('Workflow draft editor reset to the current published version.')
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
      setEditingWorkflowVersionId(null)
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

  function updateTimelinessCriterionReview(criterionKey: string, updates: Partial<Pick<TimelinessChecklistResult, 'manager_status' | 'manager_comment'>>) {
    setSelectedTimelinessClient((current) => {
      if (!current) return current
      return {
        ...current,
        checklist_results: current.checklist_results.map((result) =>
          result.key === criterionKey
            ? {
                ...result,
                ...updates,
              }
            : result,
        ),
      }
    })
    setTimelinessCriterionDirty(true)
  }

  async function saveTimelinessCriterionReviews() {
    if (!selectedTimelinessClient || !canOverrideTimeliness) return
    setIsBusy(true)
    setError('')
    try {
      const payload = selectedTimelinessClient.checklist_results.map((result) => ({
        criterion_key: result.key,
        status: result.manager_status || 'Not Reviewed',
        comment: result.manager_comment || '',
      }))
      const detail = await apiRequest<TimelinessClientDetail>(
        `/timeliness/clients/${selectedTimelinessClient.id}/criterion-reviews${timelinessQueryString()}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      )
      setSelectedTimelinessClient(detail)
      setSelectedTimelinessClientId(detail.id)
      setTimelinessCriterionDirty(false)
      setStatus(`Saved manager checklist notes for patient ${detail.patient_id}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to save manager checklist notes')
    } finally {
      setIsBusy(false)
    }
  }

  function exportSelectedTimelinessCounselorActions() {
    if (!selectedTimelinessClient) {
      setError('Select a treatment-plan item before exporting a counselor action list.')
      return
    }
    const safePatientId = selectedTimelinessClient.patient_id.replace(/[^a-z0-9_-]+/gi, '-')
    downloadTextFile(
      `treatment-plan-counselor-actions-${safePatientId}.csv`,
      buildSelectedTimelinessCounselorActions(selectedTimelinessClient),
      'text/csv',
    )
    setStatus(`Exported counselor action list for patient ${selectedTimelinessClient.patient_id}.`)
  }

  async function clearAllPatientData() {
    setIsBusy(true)
    setError('')
    try {
      const result = await apiRequest<ClearPatientDataResponse>('/patient-data', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmation_phrase: CLEAR_PATIENT_DATA_CONFIRMATION }),
      })
      setCharts([])
      setSelectedChart(null)
      setSelectedChartId(null)
      setNoteSets([])
      setSelectedNoteSet(null)
      setSelectedNoteSetId(null)
      setTimelinessDashboard(null)
      setSelectedTimelinessClient(null)
      setSelectedTimelinessClientId(null)
      setTimelinessCriterionDirty(false)
      await loadWorkspace()
      setStatus(result.message)
      if (result.status === 'partial') setError(result.message)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to clear patient data')
    } finally {
      setIsBusy(false)
    }
  }

  function openClearPatientDataDialog() {
    setConfirmDialog({
      title: 'Clear all patient data?',
      message:
        'This removes local patient/chart/treatment-plan/manual-upload/review data and encrypted uploaded files. It preserves user accounts, app settings, API credentials, audit logs, docs, and rules.',
      confirmLabel: 'Clear patient data',
      cancelLabel: 'Cancel',
      confirmationPhrase: CLEAR_PATIENT_DATA_CONFIRMATION,
      confirmationLabel: `Type ${CLEAR_PATIENT_DATA_CONFIRMATION} to confirm`,
      onConfirm: () => {
        setConfirmDialog(null)
        void clearAllPatientData()
      },
    })
  }

  function openApiConnectivityHarness() {
    const harnessWindow = window.open('/api-configuration', '_blank')
    const currentToken = getStoredSessionToken()
    if (!harnessWindow || !currentToken) return
    const sendSession = () => {
      try {
        harnessWindow.postMessage({ type: 'iz-cna-session-token', token: currentToken }, window.location.origin)
      } catch {
        // The harness still falls back to direct same-origin session reads when available.
      }
    }
    const handleSessionRequest = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return
      if ((event.data as { type?: string } | null)?.type === 'iz-cna-session-token-request') sendSession()
    }
    window.addEventListener('message', handleSessionRequest)
    window.setTimeout(sendSession, 150)
    window.setTimeout(sendSession, 800)
    window.setTimeout(() => window.removeEventListener('message', handleSessionRequest), 5000)
  }

  function openRejectedPatientUpload(chart: ChartDetail) {
    changeView('uploads')
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
    storeSessionToken('')
    setToken('')
    setMustResetPassword(false)
    initialRoleViewAppliedRef.current = false
    explicitInitialViewRef.current = false
    setActiveView('dashboard')
    clearWorkspaceState()
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
          <div className='brand-lockup'>
            <img src={`${API}/branding/header-logo`} alt='R3 Recovery Services' className='brand-logo' />
            <p className='eyebrow'>R3 Recovery Services Status Dashboard</p>
          </div>
          <h1>Clinical Notes Analyzer</h1>
          <p className='hero-copy'>
            Local-first compliance workspace for treatment-plan timeliness, deterministic checklist review, manual upload, workflow queues, and API readiness.
          </p>
        </div>
        <div className='status-card' role='status' aria-live='polite' aria-label='Current app status'>
          <h2>Current status</h2>
          <div className='status-card__messages'>
            <p>{status}</p>
            {error ? <p className='error-text'>{error}</p> : null}
          </div>
          {user ? (
            <div className='status-meta'>
              <span>{user.full_name || user.username}</span>
              <span>{user.role}</span>
            </div>
          ) : null}
          <div className='status-meta'>
            <span>Local clock</span>
            <span>{localClockLabel}</span>
          </div>
          {lastAllevaSyncResult ? (
            <dl className='status-diagnostics' aria-label='Alleva treatment-plan sync diagnostics'>
              <div>
                <dt>Last sync</dt>
                <dd>{lastAllevaSyncResult.status}</dd>
              </div>
              {lastAllevaSyncDiagnostics.map((item) => (
                <div key={item.label}>
                  <dt>{item.label}</dt>
                  <dd>{item.value}</dd>
                </div>
              ))}
            </dl>
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
              <li>Counselor uploads a patient note binder using Patient ID only.</li>
              <li>The app runs an automatic clinical-note checklist evaluation.</li>
              <li>The reviewer can drill into any criterion and mark it ok or not ok.</li>
              <li>The office manager approves or returns the chart for correction.</li>
              <li>Every read, write, approval, and change is written to the forensic log.</li>
            </ol>
          </div>
        </section>
      ) : !user ? (
        <section className='panel form-panel narrow' aria-live='polite'>
          <h2>Checking session</h2>
          <p>Validating this browser session before loading the workspace.</p>
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

          <div className='view-tabs'>
            <nav className='view-tabs__primary' aria-label='Primary workflow'>
              {PRIMARY_WORKFLOW_VIEWS.map((view) => (
                <button
                  key={view}
                  className={activeView === view ? 'tab-button tab-button--active' : 'tab-button'}
                  onClick={() => changeView(view)}
                  type='button'
                >
                  {VIEW_LABELS[view]}
                </button>
              ))}
            </nav>
            <div className='view-tabs__secondary' aria-label='Support and administration shortcuts'>
              {SUPPORT_WORKFLOW_VIEWS.map((view) => (
                <button
                  key={view}
                  className={activeView === view ? 'utility-nav-button utility-nav-button--active' : 'utility-nav-button'}
                  onClick={() => changeView(view)}
                  type='button'
                >
                  {VIEW_LABELS[view]}
                </button>
              ))}
              {user?.role === 'admin' || user?.role === 'manager'
                ? MANAGER_WORKFLOW_VIEWS.map((view) => (
                    <button
                      key={view}
                      className={activeView === view ? 'utility-nav-button utility-nav-button--active' : 'utility-nav-button'}
                      onClick={() => changeView(view)}
                      type='button'
                    >
                      {VIEW_LABELS[view]}
                    </button>
                  ))
                : null}
              {user?.role === 'admin'
                ? ADMIN_WORKFLOW_VIEWS.map((view) => (
                    <button
                      key={view}
                      className={activeView === view ? 'utility-nav-button utility-nav-button--active' : 'utility-nav-button'}
                      onClick={() => changeView(view)}
                      type='button'
                    >
                      {VIEW_LABELS[view]}
                    </button>
                  ))
                : null}
              <button className='utility-nav-button utility-nav-button--signout' onClick={handleSignOut} type='button'>
                Sign out
              </button>
            </div>
          </div>

          {activeView === 'dashboard' ? (
            <section className='dashboard-grid dashboard-workbench'>
              <section className='panel detail-panel dashboard-main-panel'>
                <div className='panel-heading'>
                  <div>
                    <h2>Summary dashboard</h2>
                    <p>Executive view of treatment-plan risk, source readiness, queue movement, and recent evidence events.</p>
                  </div>
                  <button type='button' className='ghost-button' onClick={() => void loadWorkspace()} disabled={isBusy}>
                    Refresh
                  </button>
                </div>

                <section className='operational-status-band'>
                  <div>
                    <h3>Today's operational status</h3>
                    <p>{operationalStatusText}</p>
                  </div>
                  <RiskStatusStrip
                    summaries={timelinessStatusSummaries}
                    activeFilter={timelinessStatusFilter}
                    allCount={timelinessDashboard?.items.length ?? 0}
                    onSelect={(filter) => {
                      setTimelinessStatusFilter(filter)
                      changeView('timeliness')
                    }}
                    label='Dashboard treatment-plan risk status'
                  />
                </section>

                <div className='dashboard-metrics dashboard-metrics--operations'>
                  <article className='mini-card'>
                    <span>Active clients</span>
                    <strong>{timelinessDashboard?.total_active_clients ?? activeBinders}</strong>
                  </article>
                  <article className='mini-card mini-card--danger'>
                    <span>Overdue</span>
                    <strong>{timelinessDashboard?.overdue ?? 0}</strong>
                  </article>
                  <article className='mini-card mini-card--warning'>
                    <span>Urgent</span>
                    <strong>{timelinessDashboard?.urgent ?? 0}</strong>
                  </article>
                  <article className='mini-card'>
                    <span>Manager queue</span>
                    <strong>{totalAwaiting}</strong>
                  </article>
                  <article className='mini-card'>
                    <span>Checklist</span>
                    <strong>{treatmentPlanChecklist?.version ? `v${treatmentPlanChecklist.version}` : 'Not loaded'}</strong>
                  </article>
                </div>

                <section className='panel-subsection source-readiness-preview'>
                  <div className='panel-heading'>
                    <div>
                      <h3>Source readiness</h3>
                      <p>Manual upload, API readiness, and gated Alleva sync share one evidence model.</p>
                    </div>
                    <button type='button' className='ghost-button' onClick={() => changeView('sources')}>
                      Open source readiness
                    </button>
                  </div>
                  <div className='source-readiness-preview__grid'>
                    {sourceCards.map((card) => (
                      <article key={card.title} className={`source-readiness-preview__card source-readiness-preview__card--${card.tone}`}>
                        <div>
                          <strong>{card.title}</strong>
                          <span className={`pill pill--${card.tone}`}>{card.state}</span>
                        </div>
                        <p>{card.description}</p>
                        <small>{card.facts.map((fact) => `${fact.label}: ${fact.value}`).slice(0, 2).join(' | ')}</small>
                      </article>
                    ))}
                  </div>
                  <div className='source-readiness-legacy-labels' aria-label='Source readiness compatibility labels'>
                    <span>Monthly compliance-check fallback</span>
                    <span>As of upload time only</span>
                  </div>
                </section>

                <section className='panel-subsection dashboard-queue-preview'>
                  <div className='panel-heading'>
                    <div>
                      <h3>Work queue preview</h3>
                      <p>Risk-ordered treatment-plan work from the same queue used by the Treatment Plans page.</p>
                    </div>
                    <button type='button' className='ghost-button' onClick={() => changeView('timeliness')}>
                      Open Treatment plans
                    </button>
                  </div>
                  {groupedTimelinessItems.length ? (
                    <div className='compact-work-queue'>
                      {groupedTimelinessItems.slice(0, 3).map((group) => (
                        <section key={group.status} className='compact-work-queue__group'>
                          <h4>{group.label}</h4>
                          {group.items.slice(0, 3).map((item) => (
                            <button
                              type='button'
                              key={item.id}
                              className='compact-work-queue__row'
                              onClick={() => {
                                changeView('timeliness')
                                void loadTimelinessClientDetail(item.id)
                              }}
                            >
                              <span>
                                <strong>{item.patient_id}</strong>
                                <small>{item.current_level_of_care || 'LOC missing'}</small>
                              </span>
                              <span className={`pill pill--${timelinessTone(item.status)}`}>{formatDueDelta(item.status, item.days_until_due)}</span>
                            </button>
                          ))}
                        </section>
                      ))}
                    </div>
                  ) : (
                    <p className='empty-state'>No treatment-plan work queue is loaded yet.</p>
                  )}
                </section>

                <section className='panel-subsection'>
                  <div className='panel-heading'>
                    <div>
                      <h3>Recent evidence ledger</h3>
                      <p>Latest source events available to the local workstation.</p>
                    </div>
                    {user?.role === 'admin' ? (
                      <button type='button' className='ghost-button' onClick={() => changeView('logs')}>
                        Forensic logs
                      </button>
                    ) : null}
                  </div>
                  <EvidenceLedger entries={evidenceLedger.slice(0, 4)} title='Recent evidence ledger' />
                </section>
              </section>

              <aside className='panel queue-panel action-rail' aria-label='Dashboard action rail'>
                <section className='action-rail__section'>
                  <h3>Review Work</h3>
                  <button type='button' onClick={() => changeView('timeliness')}>
                    Treatment plans
                  </button>
                  <button type='button' className='ghost-button' onClick={() => changeView('reviews')}>
                    Review queue
                  </button>
                  <button type='button' className='ghost-button' onClick={() => changeView('checklist')}>
                    Checklist v1
                  </button>
                  <button type='button' className='ghost-button' onClick={exportTimelinessTaskList} disabled={isBusy}>
                    Export task list
                  </button>
                </section>
                <section className='action-rail__section'>
                  <h3>Data / Source Setup</h3>
                  <button type='button' className='ghost-button' onClick={() => changeView('uploads')}>
                    Upload binder
                  </button>
                  <button type='button' className='ghost-button' onClick={() => changeView('sources')}>
                    Source readiness
                  </button>
                  {user?.role === 'admin' || user?.role === 'manager' ? (
                    <button type='button' className='ghost-button' onClick={() => void runDailyReviewSourceCheck()} disabled={isBusy}>
                      Run safe API readiness check
                    </button>
                  ) : null}
                  {canRunAllevaTreatmentPlanSync ? (
                    <button type='button' className='ghost-button' onClick={() => void runAllevaTreatmentPlanSyncNow({ revealTimeliness: true })} disabled={isBusy}>
                      Retrieve Active Treatment Plans
                    </button>
                  ) : null}
                </section>
                <section className='action-rail__section'>
                  <h3>Admin</h3>
                  <button type='button' className='ghost-button' onClick={() => changeView('profile')}>
                    My account
                  </button>
                  <button type='button' className='ghost-button' onClick={() => changeView('help')}>
                    Help
                  </button>
                  {user?.role === 'admin' || user?.role === 'manager' ? (
                    <>
                      <button type='button' className='ghost-button' onClick={() => changeView('users')}>
                        User management
                      </button>
                      <button type='button' className='ghost-button' onClick={() => changeView('workflows')}>
                        Workflow profiles
                      </button>
                    </>
                  ) : null}
                  {user?.role === 'admin' ? (
                    <>
                      <button type='button' className='ghost-button' onClick={() => changeView('logs')}>
                        Forensic logs
                      </button>
                      <button type='button' className='ghost-button' onClick={() => changeView('settings')}>
                        App settings
                      </button>
                      <button type='button' className='danger-button' onClick={openClearPatientDataDialog} disabled={isBusy}>
                        Clear All Patient Data
                      </button>
                    </>
                  ) : null}
                  {readiness ? <p>Runtime readiness: {readiness.status}; failed checks {readiness.failed}; warnings {readiness.warnings}.</p> : null}
                </section>
              </aside>
            </section>
          ) : null}

          {activeView === 'help' ? (
            <section className='panel detail-panel help-workspace'>
              <div className='panel-heading'>
                <div>
                  <h2>Help</h2>
                  <p>Role permissions, screen guides, and setup notes for local production use.</p>
                </div>
                <button type='button' className='ghost-button' onClick={() => changeView('dashboard')}>
                  Back to dashboard
                </button>
              </div>

              <section className='panel-subsection'>
                <h3>Role permissions</h3>
                <div className='role-matrix'>
                  {ROLE_CAPABILITIES.map((roleInfo) => (
                    <article key={roleInfo.role} className='finding-card'>
                      <div className='finding-card__header'>
                        <strong>{roleInfo.role}</strong>
                        <span className='pill pill--neutral'>{roleInfo.can.length} allowed</span>
                      </div>
                      <h4>Can do</h4>
                      <ul className='compact-list'>
                        {roleInfo.can.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                      <h4>Cannot do</h4>
                      <ul className='compact-list'>
                        {roleInfo.cannot.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </article>
                  ))}
                </div>
              </section>

              <section className='panel-subsection'>
                <h3>Screen and button guide</h3>
                <div className='help-grid'>
                  {HELP_SECTIONS.map((section) => (
                    <article key={section.title} className='finding-card help-card'>
                      <h4>{section.title}</h4>
                      <ul className='compact-list'>
                        {section.items.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    </article>
                  ))}
                </div>
              </section>
            </section>
          ) : null}

          {activeView === 'timeliness' ? (
            <section className='timeliness-workspace'>
              <h2 className='sr-only'>Treatment plan timeliness</h2>
	              <aside className='panel queue-panel timeliness-queue-panel'>
	                <div className='panel-heading'>
	                  <div>
	                    <h2>Treatment Plan Workbench</h2>
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
                      <button type='button' className='ghost-button' onClick={() => changeView('sources')}>
                        Open API readiness
                      </button>
                      {user?.role === 'admin' ? (
                        <button type='button' className='ghost-button' onClick={() => changeView('settings')}>
                          Settings
                        </button>
                      ) : null}
	                    {user?.role === 'admin' ? (
	                      <button type='button' onClick={() => void runAllevaTreatmentPlanSyncNow()} disabled={isBusy}>
	                        Pull / sync
	                      </button>
	                    ) : null}
	                  </div>
	                </div>

	                <section className='timeliness-release-banner' role='status' aria-label='Treatment plan timeliness update status'>
	                  <strong>Updated evidence queue {timelinessBuildLabel}</strong>
	                  <span>Source-document Next Review Due, date-clock due date, and LOC-change due date are shown side by side in the selected-client detail.</span>
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

                <RiskStatusStrip
                  summaries={timelinessStatusSummaries}
                  activeFilter={timelinessStatusFilter}
                  allCount={timelinessFilterCount(timelinessDashboard, 'All')}
                  onSelect={setTimelinessStatusFilter}
                  label='Treatment plan risk status filters'
                />

	                {timelinessDashboard?.items.length ? (
	                  <div className='timeliness-queue-table' role='table' aria-label='Treatment plan timeliness queue'>
	                    <div className='timeliness-queue-table__head' role='row'>
                        <span>Risk</span>
	                      <span>Client</span>
                        <span>LOC / program</span>
	                      <span>Status</span>
                        <span>Initial TP date</span>
                        <span>Master TP due</span>
                        <span>Last update</span>
	                      <span>Next due</span>
                        <span>Days</span>
	                      <span>Evidence</span>
                        <span>Source</span>
                        <span>Reviewer</span>
                        <span>Last checked</span>
	                    </div>
	                    {filteredTimelinessItems.length ? (
                      groupedTimelinessItems.map((group) => (
                        <section key={group.status} className='queue-group' role='rowgroup' aria-label={`${group.label} clients`}>
                          <div className='queue-group__header' role='row'>
                            <strong>{group.label}</strong>
                            <span>{group.items.length} client{group.items.length === 1 ? '' : 's'}</span>
                          </div>
                          {group.items.map((item) => (
                            <button
                              type='button'
                              key={item.id}
                              className={
                                selectedTimelinessClientId === item.id
                                  ? `timeliness-queue-table__row timeliness-queue-table__row--${timelinessTone(item.status)} timeliness-queue-table__row--active`
                                  : `timeliness-queue-table__row timeliness-queue-table__row--${timelinessTone(item.status)}`
                              }
                              data-audit-label='Open treatment-plan evidence'
                              onClick={() => void loadTimelinessClientDetail(item.id)}
                              aria-label={`Open ${item.patient_id} treatment plan evidence`}
                            >
                              <span className={`queue-risk-stripe queue-risk-stripe--${timelinessTone(item.status)}`} aria-hidden='true' />
                              <span>
                                <strong>{item.patient_id}</strong>
                                <small>{item.counselor_name || 'Primary clinician pending'}</small>
                                {item.discharge_conflict ? <small className='text-warning'>Active status plus discharge field</small> : null}
                              </span>
                              <span>{item.current_level_of_care || 'Missing'}</span>
                              <span>
                                <span className={`pill pill--${timelinessTone(item.status)}`}>{statusToOperationalStatus(item.status)}</span>
                                {!item.current_plan_record_id ? <small className='text-warning'>Current plan not selected</small> : null}
                              </span>
                              <span>{item.admission_date || 'Missing'}</span>
                              <span>
                                <strong>{item.rule_used || 'Rule unavailable'}</strong>
                                <small>{item.current_plan_record_id ? 'Current plan selected' : 'Current plan missing'}</small>
                              </span>
                              <span>{displayDate(item.last_valid_review_date)}</span>
                              <span>
                                <strong>{item.next_due_date || 'Missing'}</strong>
                                <small>{item.current_date || 'Evaluation date unavailable'}</small>
                              </span>
                              <span>{formatDueDelta(item.status, item.days_until_due)}</span>
                              <span>
                                <strong>{item.evidence_completeness_percent}%</strong>
                                <small>{item.missing_evidence_fields.length ? `${item.missing_evidence_fields.length} missing` : 'Complete'}</small>
                              </span>
                              <span>{item.last_imported_at ? `Imported ${formatDateTime(item.last_imported_at)}` : 'Manual/source pending'}</span>
                              <span>{item.counselor_name || 'Reviewer pending'}</span>
                              <span>{formatDateTime(item.last_checked_at)}</span>
                            </button>
                          ))}
                        </section>
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
	                        <h2>{selectedTimelinessClient.patient_id}</h2>
	                        <p>{selectedTimelinessClient.current_level_of_care || 'LOC missing'} | {selectedTimelinessClient.counselor_name || 'Reviewer pending'}</p>
	                      </div>
	                      <div className='button-row'>
	                        <button type='button' className='ghost-button' onClick={() => exportSelectedTimeliness('csv')}>
	                          Export CSV
	                        </button>
	                        <button type='button' className='ghost-button' onClick={() => exportSelectedTimeliness('json')}>
	                          Export JSON
	                        </button>
	                        <button type='button' className='ghost-button' onClick={exportSelectedTimelinessCounselorActions}>
	                          Export counselor actions
	                        </button>
	                        <span className={`pill pill--${timelinessTone(selectedTimelinessClient.status)}`}>{selectedTimelinessClient.status}</span>
	                      </div>
	                    </div>

                    <DateEvidenceTimeline steps={selectedTreatmentTimeline} />

                    <SourceComparisonTable rows={selectedSourceComparisonRows} />

	                    <section className='timeliness-client-summary' aria-label='Selected treatment plan client summary'>
	                      <div>
	                        <span>Next review due</span>
	                        <strong>{selectedTimelinessClient.next_due_date || 'Missing'}</strong>
	                        <small>{selectedTimelinessClient.days_until_due == null ? 'No day count' : `${selectedTimelinessClient.days_until_due} days from evaluation date`}</small>
	                      </div>
	                      <dl>
	                        <div>
	                          <dt>Current date used</dt>
	                          <dd>{selectedTimelinessClient.current_date || selectedTimelinessClient.evidence_comparison.current_date}</dd>
	                        </div>
	                        <div>
	                          <dt>Date-clock anchor</dt>
	                          <dd>
	                            {displayDate(selectedTimelinessClient.evidence_comparison.date_clock_anchor_date)} ({selectedTimelinessClient.evidence_comparison.date_clock_anchor_source})
	                          </dd>
	                        </div>
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

	                    <DataQualityWarnings
	                      dischargeConflict={selectedTimelinessClient.discharge_conflict}
	                      warnings={selectedTimelinessClient.data_quality_warnings}
	                      idJoinWarnings={selectedTimelinessClient.id_join_warnings}
	                      idJoinConfidence={selectedTimelinessClient.id_join_confidence}
	                      identifiers={{
	                        sourceId: selectedTimelinessClient.alleva_source_id,
	                        leadId: selectedTimelinessClient.alleva_lead_id,
	                        clientId: selectedTimelinessClient.alleva_client_id,
	                        uniqueId: selectedTimelinessClient.alleva_unique_id,
	                        mrn: selectedTimelinessClient.alleva_mrn,
	                      }}
	                    />

                    <TreatmentPlanContentSummary
                      plans={selectedTimelinessClient.treatment_plans}
                      currentPlanRecordId={selectedTimelinessClient.current_plan_record_id}
                    />

                    {user?.role === 'admin' ? (
                      <AllevaPatientTreatmentPlanPanel
                        pullState={allevaPatientPlanPull}
                        patientId={allevaPatientPlanInput}
                        onPatientIdChange={(nextPatientId) => setAllevaPatientPlanInput(nextPatientId)}
                        onLoadPatient={() => void loadAllevaPatientCenteredTreatmentPlans('single_patient_treatment_plans')}
                        onLoadActivePatients={() => void loadAllevaPatientCenteredTreatmentPlans('active_patient_centered_treatment_plans')}
                        isBusy={isBusy || allevaPatientPlanPull.status === 'loading'}
                      />
                    ) : null}

                    <section className='panel-subsection evidence-comparison-panel'>
                      <div className='panel-heading'>
                        <div>
                          <h3>Evidence comparison</h3>
	                          <p>Document due date, date-clock calculation, and LOC-change calculation are shown together.</p>
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
	                          <span>Date clock due date</span>
	                          <strong>{displayDate(selectedTimelinessClient.evidence_comparison.date_clock_due_date)}</strong>
	                          <small>{displayDate(selectedTimelinessClient.evidence_comparison.date_clock_anchor_date)} anchor</small>
	                        </article>
	                        <article>
	                          <span>LOC-change due date</span>
	                          <strong>{displayDate(selectedTimelinessClient.evidence_comparison.loc_change_due_date || selectedTimelinessClient.evidence_comparison.loc_anchor_due_date)}</strong>
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

	                    <section className='panel-subsection checklist-evaluation-panel' aria-label='42-Step Checklist Evaluation'>
	                      <div className='panel-heading'>
	                        <div>
	                          <h3>42-Step Checklist Evaluation</h3>
	                          <p>
	                            Selected-client checklist result using app {versionInfo?.version ? `${versionPrefix(versionInfo)}${versionInfo.version}` : 'version unavailable'} and checklist content v{selectedTimelinessClient.checklist_version || 'Not loaded'}.
	                          </p>
	                        </div>
	                        <div className='button-row'>
	                          {canOverrideTimeliness ? (
	                            <button type='button' onClick={() => void saveTimelinessCriterionReviews()} disabled={isBusy || !timelinessCriterionDirty}>
	                              Save manager notes
	                            </button>
	                          ) : null}
	                          <span className='pill pill--neutral'>{selectedTimelinessClient.checklist_results.length} steps</span>
	                        </div>
	                      </div>
	                      {selectedTimelinessClient.checklist_results.length ? (
	                        <div className='finding-list checklist-result-list'>
	                          {selectedTimelinessClient.checklist_results.map((result) => (
	                            <details key={result.key} className='finding-card checklist-result-card'>
	                              <summary>
	                                <span>
	                                  <strong>
	                                    Step {result.step}. {result.title}
	                                  </strong>
	                                  <small>{result.finding_message}</small>
	                                </span>
	                                <span className={`pill pill--${timelinessTone(result.status)}`}>{result.status}</span>
	                              </summary>
	                              <div className='criterion-review-controls'>
	                                <div>
	                                  <span className={`pill pill--${managerCriterionTone(result.manager_status || 'Not Reviewed')}`}>
	                                    Manager: {result.manager_status || 'Not Reviewed'}
	                                  </span>
	                                  {result.manager_updated_at ? <small>Saved {formatDateTime(result.manager_updated_at)}</small> : <small>Not saved yet</small>}
	                                </div>
	                                {canOverrideTimeliness ? (
	                                  <div className='criterion-review-form'>
	                                    <label>
	                                      <span>Manager status</span>
	                                      <select
	                                        value={result.manager_status || 'Not Reviewed'}
	                                        onChange={(event) => updateTimelinessCriterionReview(result.key, { manager_status: event.target.value })}
	                                      >
	                                        {MANAGER_CRITERION_STATUSES.map((statusOption) => (
	                                          <option key={statusOption} value={statusOption}>
	                                            {statusOption}
	                                          </option>
	                                        ))}
	                                      </select>
	                                    </label>
	                                    <label>
	                                      <span>Manager comment / counselor action</span>
	                                      <textarea
	                                        value={result.manager_comment || ''}
	                                        onChange={(event) => updateTimelinessCriterionReview(result.key, { manager_comment: event.target.value })}
	                                        placeholder='Add follow-up needed for this criterion'
	                                      />
	                                    </label>
	                                  </div>
	                                ) : result.manager_comment ? (
	                                  <p className='muted-text'>{result.manager_comment}</p>
	                                ) : null}
	                              </div>
	                              <dl>
	                                <div>
	                                  <dt>Why this result</dt>
	                                  <dd>{result.finding_message || 'No finding message recorded.'}</dd>
	                                </div>
	                                <div>
	                                  <dt>Evaluated values</dt>
	                                  <dd>
	                                    {result.evaluated_values?.length ? (
	                                      <div className='evaluated-value-list'>
	                                        {result.evaluated_values.map((item) => (
	                                          <div key={`${result.key}-${item.field}-${item.label}`} className='evaluated-value-row'>
	                                            <strong>{item.label || item.field}</strong>
	                                            <span>{formatEvaluatedValue(item.value)}</span>
	                                            <small>
	                                              {item.status || 'unknown'}
	                                              {item.source ? ` - ${item.source}` : ''}
	                                            </small>
	                                          </div>
	                                        ))}
	                                      </div>
	                                    ) : (
	                                      'No evaluated values recorded'
	                                    )}
	                                  </dd>
	                                </div>
	                                <div>
	                                  <dt>Source evidence</dt>
	                                  <dd>{result.source_evidence || 'Not recorded'}</dd>
	                                </div>
	                                <div>
	                                  <dt>Evidence fields used</dt>
	                                  <dd>{result.evidence_fields_used.length ? result.evidence_fields_used.join(', ') : 'None recorded'}</dd>
	                                </div>
	                                <div>
	                                  <dt>Required metadata</dt>
	                                  <dd>{result.required_metadata.length ? result.required_metadata.join(', ') : 'None'}</dd>
	                                </div>
	                                <div>
	                                  <dt>Required documents</dt>
	                                  <dd>{result.required_documents.length ? result.required_documents.join(', ') : 'None'}</dd>
	                                </div>
	                                <div>
	                                  <dt>Checks</dt>
	                                  <dd>{result.checks.length ? result.checks.join('; ') : 'None'}</dd>
	                                </div>
	                                <div>
	                                  <dt>Finding examples</dt>
	                                  <dd>{result.finding_examples.length ? result.finding_examples.join('; ') : 'None'}</dd>
	                                </div>
	                                <div>
	                                  <dt>Remediation suggestions</dt>
	                                  <dd>{result.remediation_suggestions.length ? result.remediation_suggestions.join('; ') : 'None'}</dd>
	                                </div>
	                                <div>
	                                  <dt>Reviewer actions</dt>
	                                  <dd>{result.reviewer_actions.length ? result.reviewer_actions.join(', ') : 'None'}</dd>
	                                </div>
	                                <div>
	                                  <dt>Override and audit</dt>
	                                  <dd>
	                                    {result.manual_override_allowed ? 'Manual override allowed' : 'Manual override not allowed'}; {result.override_reason_required ? 'reason required' : 'reason not required'}; audit event {result.audit_event || 'not recorded'}
	                                  </dd>
	                                </div>
	                                <div>
	                                  <dt>Export fields</dt>
	                                  <dd>{result.export_fields.length ? result.export_fields.join(', ') : 'None'}</dd>
	                                </div>
	                              </dl>
	                            </details>
	                          ))}
	                        </div>
	                      ) : (
	                        <p className='empty-state'>No selected-client checklist evaluation is loaded.</p>
	                      )}
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
	                            <span>Content</span>
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
	                              <span>
                                <strong>
                                  {(plan.plan_field_count ?? safeContentItems(plan.content_items).filter((item) => item.kind === 'plan_field').length) +
                                    (plan.problem_count ?? 0) +
                                    (plan.behavioral_definition_count ?? 0) +
                                    (plan.diagnosis_count ?? 0) +
                                    (plan.goal_count ?? 0) +
                                    (plan.objective_count ?? 0) +
                                    (plan.intervention_count ?? 0)}{' '}
                                  items
                                </strong>
	                                <small>
	                                  {plan.is_current ? 'Current' : 'Historical'} - {plan.detail_fetched ? 'Detail loaded' : 'Detail pending'} - {safeContentItems(plan.content_items).length} facts
	                                </small>
	                              </span>
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
                  <EmptyTreatmentPlanDetail
                    onPull={() => void runAllevaTreatmentPlanSyncNow({ revealTimeliness: true })}
                    onUpload={() => changeView('uploads')}
                    onReadiness={() => changeView('sources')}
                    onSettings={() => changeView('settings')}
                    canPull={canRunAllevaTreatmentPlanSync}
                    canOpenSettings={user?.role === 'admin'}
                  />
	                )}
	              </section>
	            </section>
	          ) : null}

          {activeView === 'sources' ? (
            <section className='source-readiness-workspace'>
              <header className='operational-toolbar source-readiness-toolbar'>
                <div className='operational-toolbar__title'>
                  <h2>Source readiness</h2>
                  <p>Manual upload, safe API readiness, and gated Alleva treatment-plan sync status for the local workstation.</p>
                </div>
                <div className='operational-toolbar__controls'>
                  <button type='button' className='ghost-button' onClick={() => void loadWorkspace()} disabled={isBusy}>
                    Refresh
                  </button>
                  <button type='button' className='ghost-button' onClick={() => changeView('uploads')}>
                    Upload binder
                  </button>
                  {user?.role === 'admin' || user?.role === 'manager' ? (
                    <button type='button' className='ghost-button' onClick={() => void runDailyReviewSourceCheck()} disabled={isBusy}>
                      Run safe API readiness check
                    </button>
                  ) : null}
                  {user?.role === 'admin' ? (
                    <button type='button' onClick={() => void runAllevaTreatmentPlanSyncNow({ revealTimeliness: true })} disabled={isBusy}>
                      Retrieve Active Treatment Plans
                    </button>
                  ) : null}
                </div>
              </header>

              <section className='timeliness-release-banner source-readiness-boundary' role='status' aria-label='Alleva live sync boundary'>
                <strong>Alleva live import remains gated</strong>
                <span>Live patient import is disabled until approval, credentials, endpoint mapping, pagination, rate limits, and compliance review are complete.</span>
              </section>

              <div className='source-readiness-grid'>
                {sourceCards.map((card) => (
                  <SourceReadinessCard key={card.title} source={card} />
                ))}
              </div>

              <section className='source-readiness-layout'>
                <EvidenceLedger entries={evidenceLedger} />
                <aside className='panel source-readiness-summary'>
                  <h3>Readiness facts</h3>
                  <dl className='source-mode-facts'>
                    <div>
                      <dt>API mode</dt>
                      <dd>{reviewSourceDiscovery?.api_mode_label || 'Mock/stub mode'}</dd>
                    </div>
                    <div>
                      <dt>Manual cadence</dt>
                      <dd>{reviewSourceDiscovery?.manual_review_cadence || 'Monthly compliance-check fallback'}</dd>
                    </div>
                    <div>
                      <dt>Upload freshness</dt>
                      <dd>As of upload time only</dd>
                    </div>
                    <div>
                      <dt>Needs follow-up</dt>
                      <dd>{reviewSourceDiscovery?.notification_badge_count ?? reviewSourceApiItems}</dd>
                    </div>
                    <div>
                      <dt>Routed manual items</dt>
                      <dd>{reviewSourceUploadItems}</dd>
                    </div>
                    <div>
                      <dt>LOC change window</dt>
                      <dd>
                        {timelinessDashboard?.loc_change_window_days == null ? 'Not configured' : `${timelinessDashboard.loc_change_window_days} days`};{' '}
                        {timelinessDashboard?.loc_change_window_validated ? 'validated' : 'unvalidated'}
                      </dd>
                    </div>
                  </dl>
                  <div className='button-row'>
                    <button type='button' className='ghost-button' onClick={() => changeView('timeliness')}>
                      Open Treatment plans
                    </button>
                    {user?.role === 'admin' ? (
                      <button type='button' className='ghost-button' onClick={() => changeView('settings')}>
                        Open API settings
                      </button>
                    ) : null}
                  </div>
                </aside>
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
                      ? `App ${versionInfo?.version ? `${versionPrefix(versionInfo)}${versionInfo.version}` : 'version unavailable'}; checklist content v${treatmentPlanChecklist.version} from ${treatmentPlanChecklist.source_of_truth}`
                      : 'Loading canonical checklist...'}
                  </p>
                </div>
                <div className='button-row'>
                  {canManageWorkflowProfiles ? (
                    <button type='button' className='ghost-button' onClick={() => changeView('workflows')}>
                      Workflow profiles
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
                              <dt>Evidence fields</dt>
                              <dd>{step.evidence_fields.length ? step.evidence_fields.join(', ') : 'None'}</dd>
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
                          <dl>
                            <div>
                              <dt>Finding examples</dt>
                              <dd>{step.finding_examples.length ? step.finding_examples.join('; ') : 'None'}</dd>
                            </div>
                            <div>
                              <dt>Remediation suggestions</dt>
                              <dd>{step.remediation_suggestions.length ? step.remediation_suggestions.join('; ') : 'None'}</dd>
                            </div>
                          </dl>
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
                  <div className='button-row'>
                    <button type='button' className='ghost-button' onClick={() => void loadWorkspace()} disabled={isBusy}>
                      Refresh
                    </button>
                  </div>
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
                        <h2>Patient Details</h2>
                        <p>Patient ID: {selectedChart.patient_id}</p>
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
                          <button
                            type='button'
                            className='ghost-button'
                            onClick={() => {
                              setActiveView('uploads')
                              void loadNoteSetDetail(linkedNoteSet.id)
                            }}
                          >
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
                  Manual upload is the primary local workflow. Use the patient ID as the source-of-truth key; patient names are not used as local display labels.
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
                  {uploadProgress ? <UploadProgressPanel progress={uploadProgress} /> : null}
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
                      <button
                        type='button'
                        onClick={() => {
                          setActiveView('reviews')
                          void loadChartDetail(selectedNoteSet.review_chart_id!)
                        }}
                      >
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
                    <div className='danger-zone'>
                      <strong>Delete this uploaded binder</strong>
                      <p>
                        Deletes this upload, its linked automated review, and the encrypted stored files from this computer. Audit logs remain.
                      </p>
                      <label>
                        Type patient ID to confirm
                        <input
                          value={deleteNoteSetConfirmation}
                          onChange={(event) => setDeleteNoteSetConfirmation(event.target.value)}
                          placeholder={selectedNoteSet.patient_id}
                        />
                      </label>
                      <button
                        type='button'
                        className='danger-button'
                        onClick={() => void deleteSelectedNoteSet()}
                        disabled={deletingNoteSetId === selectedNoteSet.id}
                        aria-busy={deletingNoteSetId === selectedNoteSet.id ? 'true' : undefined}
                      >
                        {deletingNoteSetId === selectedNoteSet.id ? 'Deleting...' : 'Delete uploaded binder'}
                      </button>
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

          {activeView === 'users' && canManageUsers ? (
            <section className='workspace-grid'>
              <aside className='panel queue-panel'>
                <div className='panel-heading'>
                  <div>
                    <h2>User management</h2>
                    <p>
                      {user?.role === 'admin'
                        ? 'Select a user to edit access, reset their password, or delete the account.'
                        : 'Office managers can maintain counselor accounts. Admin and manager accounts are visible but not editable here.'}
                    </p>
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
                            <dd>
                              {selectedManagedUserIsBootstrap
                                ? 'Bootstrap admin is fixed'
                                : canManageSelectedUser
                                  ? user?.role === 'manager'
                                    ? 'Counselor only'
                                    : 'Yes'
                                  : 'No'}
                            </dd>
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
                            disabled={isBusy || !canManageSelectedUser}
                            onChange={(event) => setManagedUserForm((current) => (current ? { ...current, full_name: event.target.value } : current))}
                          />
                        </label>
                        <label>
                          Role
                          <select
                            value={managedUserForm.role}
                            disabled={isBusy || selectedManagedUserIsBootstrap || user?.role === 'manager' || !canManageSelectedUser}
                            onChange={(event) =>
                              setManagedUserForm((current) => (current ? { ...current, role: event.target.value as Role } : current))
                            }
                          >
                            <option value='counselor'>Counselor</option>
                            {user?.role === 'admin' ? <option value='manager'>Office manager</option> : null}
                            {user?.role === 'admin' ? <option value='admin'>Admin</option> : null}
                          </select>
                        </label>
                        <label className='checkbox-row'>
                          <input
                            type='checkbox'
                            checked={managedUserForm.is_active}
                            disabled={isBusy || selectedManagedUserIsBootstrap || !canManageSelectedUser}
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
                            disabled={isBusy || selectedManagedUserIsBootstrap || !canManageSelectedUser}
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
                            disabled={isBusy || selectedManagedUserIsBootstrap || !canManageSelectedUser}
                            onChange={(event) =>
                              setManagedUserForm((current) => (current ? { ...current, must_reset_password: event.target.checked } : current))
                            }
                          />
                          Force password reset at next login
                        </label>
                        <div className='full-width form-actions'>
                          <button type='submit' disabled={isBusy || !canManageSelectedUser}>
                            Save selected user
                          </button>
                        </div>
                      </form>

                      <section className='panel-subsection'>
                        <h3>Password reset</h3>
                        {selectedManagedUserIsBootstrap || !canManageSelectedUser ? (
                          <p className='muted-text'>
                            {selectedManagedUserIsBootstrap
                              ? 'The bootstrap admin password is fixed outside the app.'
                              : 'This account is outside your user-management scope.'}
                          </p>
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
                              : selectedManagedUserIsCurrentUser
                                ? 'The signed-in account cannot delete itself.'
                                : 'This account is outside your user-management scope.'}
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
                  <p className='muted-text'>
                    {user?.role === 'admin'
                      ? 'Create a managed user account with a temporary password of at least 12 characters. The user will be prompted to reset it after the first sign-in.'
                      : 'Create a counselor account with a temporary password of at least 12 characters. The counselor will be prompted to reset it after the first sign-in.'}
                  </p>
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
                      <select
                        value={newUserForm.role}
                        disabled={user?.role === 'manager'}
                        onChange={(event) => setNewUserForm((current) => ({ ...current, role: event.target.value as Role }))}
                      >
                        <option value='counselor'>Counselor</option>
                        {user?.role === 'admin' ? <option value='manager'>Office manager</option> : null}
                        {user?.role === 'admin' ? <option value='admin'>Admin</option> : null}
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

          {activeView === 'workflows' && canManageWorkflowProfiles ? (
            <section className='panel detail-panel workflow-admin-panel'>
              <div className='panel-heading'>
                <div>
                  <h2>Workflow profiles</h2>
                  <p>Version the checklist logic and routing rules used by treatment-plan and chart-review work.</p>
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
                <article className='mini-card'>
                  <span>Access</span>
                  <strong>{user?.role === 'admin' ? 'Admin' : 'Manager'}</strong>
                </article>
              </div>

              <div className='workflow-admin-grid'>
                <section className='panel-subsection'>
                  <h3>Profiles</h3>
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
                            setEditingWorkflowVersionId(null)
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
                  <h3>{selectedWorkflowDefinition?.display_name || 'Selected profile'}</h3>
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
                            <span className='button-row'>
                              <button type='button' className='ghost-button' onClick={() => loadWorkflowVersionForEditing(version)} disabled={isBusy}>
                                {version.status === 'draft' ? 'Edit draft' : 'Use as draft'}
                              </button>
                              {version.status === 'draft' ? (
                                <button type='button' className='ghost-button' onClick={() => void publishWorkflowVersion(version.id)} disabled={isBusy}>
                                  Publish
                                </button>
                              ) : (
                                <span>{formatDateTime(version.published_at || version.archived_at)}</span>
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
                <h3>Create workflow profile</h3>
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
                  <h3>{editingWorkflowVersionId ? 'Edit draft version' : 'Create draft version'}</h3>
                  <div className='rule-alert'>
                    <strong>Manager/admin-editable checklist workflow</strong>
                    <p>Seed a draft from the canonical 42-step checklist, adjust the workflow JSON for R3 operations, create the draft, then publish it when approved.</p>
                    <div className='form-actions'>
                      <button type='button' className='ghost-button' onClick={() => void seedWorkflowDraftFromCanonicalChecklist()} disabled={isBusy}>
                        Seed draft from 42-step checklist
                      </button>
                      <button type='button' className='ghost-button' onClick={clearWorkflowVersionEditor} disabled={isBusy}>
                        Reset editor
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
                        {editingWorkflowVersionId ? 'Save draft edits' : 'Create draft version'}
                      </button>
                    </div>
                  </form>
                </section>
              ) : null}
            </section>
          ) : null}

          {activeView === 'settings' && user?.role === 'admin' ? (
            <section className='workspace-grid'>
              <aside className='panel queue-panel'>
                <div className='panel-heading'>
                  <div>
                    <h2>Application settings</h2>
                    <p>Configure local settings, the single active Alleva/API connection, optional saved endpoint presets, and disabled-by-default LLM support.</p>
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
                    <dt>Periodic API check</dt>
                    <dd>{appSettings?.emr_periodic_check_enabled ? `Every ${appSettings.emr_periodic_check_interval_minutes} minutes` : 'Off'}</dd>
                  </div>
                  <div>
                    <dt>Last API check</dt>
                    <dd>
                      {appSettings?.emr_last_check_at
                        ? `${appSettings.emr_last_check_status || 'checked'} at ${formatDateTime(appSettings.emr_last_check_at)}`
                        : 'Not run'}
                    </dd>
                  </div>
                  <div>
                    <dt>Alleva REST sync</dt>
                    <dd>
                      {appSettings?.alleva_treatment_plan_sync_enabled
                        ? appSettings.alleva_treatment_plan_sync_on_startup
                          ? 'On at startup'
                          : 'Manual only'
                        : 'Off'}
                    </dd>
                  </div>
                  <div>
                    <dt>Plan detail fetch</dt>
                    <dd>
                      {appSettings?.alleva_treatment_plan_detail_fetch_enabled
                        ? `On, cap ${appSettings.alleva_treatment_plan_detail_fetch_limit ?? 50}`
                        : 'Off'}
                    </dd>
                  </div>
                  <div>
                    <dt>Last Alleva sync</dt>
                    <dd>
                      {appSettings?.alleva_treatment_plan_sync_last_at
                        ? `${appSettings.alleva_treatment_plan_sync_last_status || 'checked'} at ${formatDateTime(appSettings.alleva_treatment_plan_sync_last_at)}`
                        : 'Not run'}
                    </dd>
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
	                    <p className='muted-text field-note'>
	                      PHP treatment plans use a 30-calendar-day update clock. IOP, OP, and other configured non-PHP levels use 60 calendar days. This field controls the separate LOC-change update clock; the preset is 7 calendar days and remains manager-editable.
	                    </p>
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
                    <section className='panel-subsection full-width'>
                      <h3>Active Alleva/API connection</h3>
                      <p className='muted-text field-note'>
                        These fields are the source of truth for readiness checks, the API connectivity harness, and approved Alleva REST treatment-plan sync.
                        Paste the client ID and client secret supplied by Alleva/R3 when using OAuth client credentials. The saved secret is encrypted locally,
                        write-only after save, and never returned to the browser.
                      </p>
                      <div className='compact-status-frame' aria-live='polite'>
                        <strong>Connection activity</strong>
                        <pre>{settingsActivityLog.length ? settingsActivityLog.join('\n') : 'No App settings/API action has run in this browser session.'}</pre>
                      </div>
                    </section>
                    <label className='checkbox-row full-width'>
                      <input
                        type='checkbox'
                        checked={settingsForm.emr_api_enabled}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, emr_api_enabled: event.target.checked } : current))}
                      />
                      Enable HL7/API readiness checks
                    </label>
                    <label>
                      Integration vendor label
                      <input
                        value={settingsForm.emr_vendor_name}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, emr_vendor_name: event.target.value } : current))}
                      />
                    </label>
                    <label className='full-width'>
                      OAuth token URL
                      <input
                        value={settingsForm.api_oauth_token_url}
                        placeholder='https://authorization.allevasoft.com/connect/token'
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, api_oauth_token_url: event.target.value } : current))}
                      />
                    </label>
                    <label>
                      Token auth style
                      <select
                        value={settingsForm.api_token_auth_style}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, api_token_auth_style: event.target.value } : current))
                        }
                      >
                        <option value='body'>Body credentials</option>
                        <option value='basic'>Basic auth header</option>
                        <option value='basic_urlencoded'>Basic auth header, URL-encoded pair</option>
                        <option value='both'>Try body, then Basic</option>
                        <option value='all'>Try all supported styles</option>
                      </select>
                    </label>
                    <label>
                      API client ID
                      <input
                        value={settingsForm.api_client_id}
                        onChange={(event) => setSettingsForm((current) => (current ? { ...current, api_client_id: event.target.value } : current))}
                      />
                    </label>
                    <label>
                      API client secret
                      <input
                        type='password'
                        autoComplete='off'
                        value={settingsForm.api_client_secret}
                        placeholder={appSettings?.api_client_secret_configured ? 'Configured. Enter a new secret to replace it.' : 'Required for approved REST sync and authenticated API checks'}
                        onChange={(event) =>
                          setSettingsForm((current) =>
                            current
                              ? {
                                  ...current,
                                  api_client_secret: event.target.value,
                                  clear_api_client_secret: false,
                                }
                              : current,
                          )
                        }
                      />
                    </label>
                    <label className='checkbox-row'>
                      <input
                        type='checkbox'
                        checked={settingsForm.clear_api_client_secret}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, clear_api_client_secret: event.target.checked } : current))
                        }
                      />
                      Clear stored API client secret
                    </label>
                    <p className='muted-text field-note full-width'>
                      For Alleva OAuth, pasting the client ID and client secret here is expected. To avoid duplicate entry, save reusable alternatives under
                      API endpoint presets below, then activate a preset to copy it into these active fields.
                    </p>
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
                    <label className='checkbox-row'>
                      <input
                        type='checkbox'
                        checked={settingsForm.emr_periodic_check_enabled}
                        onChange={(event) =>
                          setSettingsForm((current) => (current ? { ...current, emr_periodic_check_enabled: event.target.checked } : current))
                        }
                      />
                      Periodically run safe Alleva API checks
                    </label>
                    <p className='muted-text field-note full-width'>
                      This checkbox only turns on the background schedule. The manual safe API readiness check below stays available for one-time configuration tests and does not import patient charts.
                    </p>
                    <label>
                      Check interval (minutes)
                      <input
                        type='number'
                        min={5}
                        max={10080}
                        value={settingsForm.emr_periodic_check_interval_minutes}
                        onChange={(event) =>
                          setSettingsForm((current) =>
                            current ? { ...current, emr_periodic_check_interval_minutes: Number(event.target.value || 1440) } : current
                          )
                        }
                      />
                    </label>
                    <section className='panel-subsection full-width'>
                      <h3>Alleva REST treatment-plan sync</h3>
                      <p className='muted-text field-note'>
                        This path uses Alleva REST endpoints such as /clients, /treatment-plans, and /treatment-reviews. R3 compliance checks run inside this app after the mapped data is imported.
                      </p>
                      <div className='form-grid'>
                        <label>
                          Alleva REST API base URL
                          <input
                            value={settingsForm.alleva_api_base_url}
                            placeholder='https://api.allevasoft.com'
                            onChange={(event) => setSettingsForm((current) => (current ? { ...current, alleva_api_base_url: event.target.value } : current))}
                          />
                        </label>
                        <label>
                          Alleva OpenAPI URL
                          <input
                            value={settingsForm.alleva_openapi_url}
                            placeholder='https://api.allevasoft.com/swagger/v1/swagger.json'
                            onChange={(event) => setSettingsForm((current) => (current ? { ...current, alleva_openapi_url: event.target.value } : current))}
                          />
                        </label>
                        <label>
                          Alleva API version
                          <input
                            value={settingsForm.alleva_api_version}
                            onChange={(event) => setSettingsForm((current) => (current ? { ...current, alleva_api_version: event.target.value } : current))}
                          />
                        </label>
                        <label>
                          Max records per sync endpoint
                          <input
                            type='number'
                            min={1}
                            max={5000}
                            value={settingsForm.alleva_treatment_plan_sync_limit}
                            onChange={(event) =>
                              setSettingsForm((current) =>
                                current ? { ...current, alleva_treatment_plan_sync_limit: Number(event.target.value || 250) } : current
                              )
                            }
                          />
                        </label>
                        <label>
                          Current-plan detail fetch cap
                          <input
                            type='number'
                            min={0}
                            max={5000}
                            value={settingsForm.alleva_treatment_plan_detail_fetch_limit}
                            onChange={(event) =>
                              setSettingsForm((current) =>
                                current ? { ...current, alleva_treatment_plan_detail_fetch_limit: Number(event.target.value || 0) } : current
                              )
                            }
                          />
                        </label>
                        <label className='checkbox-row'>
                          <input
                            type='checkbox'
                            checked={settingsForm.alleva_treatment_plan_sync_enabled}
                            onChange={(event) =>
                              setSettingsForm((current) =>
                                current ? { ...current, alleva_treatment_plan_sync_enabled: event.target.checked } : current
                              )
                            }
                          />
                          Enable Alleva REST treatment-plan sync
                        </label>
                        <label className='checkbox-row'>
                          <input
                            type='checkbox'
                            checked={settingsForm.alleva_treatment_plan_detail_fetch_enabled}
                            onChange={(event) =>
                              setSettingsForm((current) =>
                                current ? { ...current, alleva_treatment_plan_detail_fetch_enabled: event.target.checked } : current
                              )
                            }
                          />
                          Fetch current-plan clinical detail
                        </label>
                        <label className='checkbox-row'>
                          <input
                            type='checkbox'
                            checked={settingsForm.alleva_treatment_plan_patient_name_import_enabled}
                            onChange={(event) =>
                              setSettingsForm((current) =>
                                current ? { ...current, alleva_treatment_plan_patient_name_import_enabled: event.target.checked } : current
                              )
                            }
                          />
                          Import and display Alleva patient names
                        </label>
                        <label className='checkbox-row'>
                          <input
                            type='checkbox'
                            checked={settingsForm.alleva_treatment_plan_sync_on_startup}
                            onChange={(event) =>
                              setSettingsForm((current) =>
                                current ? { ...current, alleva_treatment_plan_sync_on_startup: event.target.checked } : current
                              )
                            }
                          />
                          Run sync every time the app starts (off by default for beta)
                        </label>
                        <label className='checkbox-row'>
                          <input
                            type='checkbox'
                            checked={settingsForm.alleva_treatment_plan_sync_approved}
                            onChange={(event) =>
                              setSettingsForm((current) =>
                                current ? { ...current, alleva_treatment_plan_sync_approved: event.target.checked } : current
                              )
                            }
                          />
                          R3 and Alleva have approved live treatment-plan sync
                        </label>
                        <label className='checkbox-row'>
                          <input
                            type='checkbox'
                            checked={settingsForm.alleva_treatment_plan_endpoint_mapping_validated}
                            onChange={(event) =>
                              setSettingsForm((current) =>
                                current ? { ...current, alleva_treatment_plan_endpoint_mapping_validated: event.target.checked } : current
                              )
                            }
                          />
                          Active-client, treatment-plan, review, pagination, and status fields are validated
                        </label>
                        <label className='checkbox-row'>
                          <input
                            type='checkbox'
                            checked={settingsForm.alleva_treatment_plan_name_join_fallback_enabled}
                            onChange={(event) =>
                              setSettingsForm((current) =>
                                current ? { ...current, alleva_treatment_plan_name_join_fallback_enabled: event.target.checked } : current
                              )
                            }
                          />
                          Allow name fallback only for validation
                        </label>
                      </div>
                      <p className='muted-text field-note'>
                        The sync, startup, approval, mapping, patient-name import, and name-fallback checkboxes are separate safety gates. Names stay redacted in the Treatment Plans queue unless import/display is enabled here and saved.
                      </p>
                      <div className='form-actions'>
                        <button
                          type='button'
                          className='ghost-button'
                          onClick={() => void runAllevaTreatmentPlanSyncNow()}
                          disabled={isBusy}
                        >
                          Run treatment-plan sync now
                        </button>
                      </div>
                      {appSettings?.alleva_treatment_plan_sync_last_message ? (
                        <p className='muted-text'>
                          Last Alleva treatment-plan sync
                          {appSettings.alleva_treatment_plan_sync_last_status
                            ? ` (${appSettings.alleva_treatment_plan_sync_last_status}${appSettings.alleva_treatment_plan_sync_last_at ? ` at ${formatDateTime(appSettings.alleva_treatment_plan_sync_last_at)}` : ''})`
                            : ''}
                          : {appSettings.alleva_treatment_plan_sync_last_message}
                        </p>
                      ) : null}
                    </section>
                    <section className='panel-subsection full-width'>
                      <h3>Alleva REST/OpenAPI readiness</h3>
                      <p className='muted-text field-note'>
                        This readiness panel uses the active connection saved above. The safe readiness check tests authentication and API documentation access;
                        it does not import live patient charts. Use the API connectivity harness for the ALL Patient Records pull or advanced OpenAPI operation checks.
                      </p>
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
                        <button
                          type='button'
                          className='ghost-button'
                          onClick={() => void runDailyReviewSourceCheck()}
                          disabled={isBusy}
                        >
                          Run safe API readiness check now
                        </button>
                        <button type='button' className='ghost-button' onClick={openApiConnectivityHarness}>
                          Open API Testing Harness
                        </button>
                      </div>
                      {appSettings?.emr_last_check_message ? <p className='muted-text'>Last API check: {appSettings.emr_last_check_message}</p> : null}
                    </section>
                    <section className='panel-subsection full-width danger-zone'>
                      <div className='panel-heading'>
                        <div>
                          <h3>Clear All Patient Data</h3>
                          <p>
                            Removes local patient/chart/treatment-plan/manual-upload/review data and encrypted uploaded files. App settings, API credentials,
                            user accounts, audit logs, rules, and documentation are preserved.
                          </p>
                        </div>
                        <button type='button' className='danger-button' onClick={openClearPatientDataDialog} disabled={isBusy}>
                          Clear All Patient Data
                        </button>
                      </div>
                    </section>
                    <section className='panel-subsection full-width'>
                      <div className='panel-heading'>
                        <div>
                          <h3>Stored API endpoint profiles</h3>
                          <p>Save optional presets. Activating a preset copies it into the active connection above without exposing stored secrets back to the browser.</p>
                        </div>
                        <button type='button' className='ghost-button' onClick={() => void loadEmrEndpointProfiles(selectedEmrEndpointProfileId)} disabled={isBusy}>
                          Refresh profiles
                        </button>
                      </div>
                      <div className='workflow-admin-grid'>
                        <section className='panel-subsection'>
                          <h4>Saved profiles</h4>
                          {emrEndpointProfiles.length ? (
                            <div className='queue-list'>
                              {emrEndpointProfiles.map((profile) => (
                                <button
                                  type='button'
                                  key={profile.id}
                                  className={selectedEmrEndpointProfile?.id === profile.id ? 'queue-item queue-item--active' : 'queue-item'}
                                  data-audit-label='Open EMR endpoint profile'
                                  onClick={() => setSelectedEmrEndpointProfileId(profile.id)}
                                >
                                  <div>
                                    <strong>{profile.display_name}</strong>
                                    <span>{profile.vendor_name}</span>
                                  </div>
                                  <div className='queue-item-meta'>
                                    <span className={`pill pill--${profile.is_default ? 'success' : profile.is_active ? 'neutral' : 'muted'}`}>
                                      {profile.is_default ? 'current' : profile.is_active ? 'saved' : 'inactive'}
                                    </span>
                                    <span>{profile.client_secret_configured ? 'secret stored' : 'no secret'}</span>
                                  </div>
                                </button>
                              ))}
                            </div>
                          ) : (
                            <p className='empty-state'>No endpoint profiles are stored yet.</p>
                          )}
                        </section>

                        <section className='panel-subsection'>
                          <h4>{selectedEmrEndpointProfile?.display_name || 'Selected endpoint'}</h4>
                          {selectedEmrEndpointProfile ? (
                            <>
                              <div className='fact-list'>
                                <div>
                                  <dt>REST API base URL</dt>
                                  <dd>{selectedEmrEndpointProfile.api_base_url || 'Not set'}</dd>
                                </div>
                                <div>
                                  <dt>OpenAPI URL</dt>
                                  <dd>{selectedEmrEndpointProfile.openapi_url || 'Not set'}</dd>
                                </div>
                                <div>
                                  <dt>Token URL</dt>
                                  <dd>{selectedEmrEndpointProfile.token_url || 'Not set'}</dd>
                                </div>
                                <div>
                                  <dt>Client ID</dt>
                                  <dd>{selectedEmrEndpointProfile.client_id_configured ? selectedEmrEndpointProfile.client_id : 'Not set'}</dd>
                                </div>
                              </div>
                              <div className='form-actions'>
                                <button
                                  type='button'
                                  className='ghost-button'
                                  onClick={() => void activateEmrEndpointProfile(selectedEmrEndpointProfile.id)}
                                  disabled={isBusy || selectedEmrEndpointProfile.is_default}
                                >
                                  Use for active API settings
                                </button>
                                <button
                                  type='button'
                                  className='danger-button'
                                  onClick={() => void deleteEmrEndpointProfile(selectedEmrEndpointProfile.id)}
                                  disabled={isBusy || selectedEmrEndpointProfile.is_default}
                                >
                                  Delete saved profile
                                </button>
                              </div>
                            </>
                          ) : (
                            <p className='empty-state'>Select a saved endpoint profile.</p>
                          )}
                        </section>
                      </div>

                      <section className='panel-subsection'>
                        <h4>Add endpoint profile</h4>
                        <div className='form-grid'>
                          <label>
                            Profile key
                            <input
                              pattern='[a-z0-9][a-z0-9_-]*'
                              value={emrEndpointProfileForm.profile_key}
                              onChange={(event) => setEmrEndpointProfileForm((current) => ({ ...current, profile_key: event.target.value }))}
                            />
                          </label>
                          <label>
                            Display name
                            <input
                              value={emrEndpointProfileForm.display_name}
                              onChange={(event) => setEmrEndpointProfileForm((current) => ({ ...current, display_name: event.target.value }))}
                            />
                          </label>
                          <label>
                            Vendor
                            <input
                              value={emrEndpointProfileForm.vendor_name}
                              onChange={(event) => setEmrEndpointProfileForm((current) => ({ ...current, vendor_name: event.target.value }))}
                            />
                          </label>
                          <label>
                            Adapter key
                            <input
                              value={emrEndpointProfileForm.adapter_key}
                              onChange={(event) => setEmrEndpointProfileForm((current) => ({ ...current, adapter_key: event.target.value }))}
                            />
                          </label>
                          <label className='full-width'>
                            REST API base URL
                            <input
                              placeholder='https://api.allevasoft.com'
                              value={emrEndpointProfileForm.api_base_url}
                              onChange={(event) => setEmrEndpointProfileForm((current) => ({ ...current, api_base_url: event.target.value }))}
                            />
                          </label>
                          <label className='full-width'>
                            OpenAPI URL
                            <input
                              value={emrEndpointProfileForm.openapi_url}
                              onChange={(event) => setEmrEndpointProfileForm((current) => ({ ...current, openapi_url: event.target.value }))}
                            />
                          </label>
                          <label className='full-width'>
                            OAuth token URL
                            <input
                              value={emrEndpointProfileForm.token_url}
                              onChange={(event) => setEmrEndpointProfileForm((current) => ({ ...current, token_url: event.target.value }))}
                            />
                          </label>
                          <label>
                            Token auth style
                            <select
                              value={emrEndpointProfileForm.token_auth_style}
                              onChange={(event) => setEmrEndpointProfileForm((current) => ({ ...current, token_auth_style: event.target.value }))}
                            >
                              <option value='body'>Body credentials</option>
                              <option value='basic'>Basic auth header</option>
                              <option value='basic_urlencoded'>Basic auth header, URL-encoded pair</option>
                              <option value='both'>Try body, then Basic</option>
                              <option value='all'>Try all supported styles</option>
                            </select>
                          </label>
                          <label>
                            Client ID
                            <input
                              value={emrEndpointProfileForm.client_id}
                              onChange={(event) => setEmrEndpointProfileForm((current) => ({ ...current, client_id: event.target.value }))}
                            />
                          </label>
                          <label>
                            Client secret
                            <input
                              type='password'
                              autoComplete='off'
                              value={emrEndpointProfileForm.client_secret}
                              onChange={(event) => setEmrEndpointProfileForm((current) => ({ ...current, client_secret: event.target.value }))}
                            />
                          </label>
                          <label>
                            Timeout seconds
                            <input
                              type='number'
                              min={1}
                              max={60}
                              value={emrEndpointProfileForm.timeout_seconds}
                              onChange={(event) => setEmrEndpointProfileForm((current) => ({ ...current, timeout_seconds: Number(event.target.value || 10) }))}
                            />
                          </label>
                          <label className='full-width'>
                            Notes
                            <textarea
                              value={emrEndpointProfileForm.notes}
                              onChange={(event) => setEmrEndpointProfileForm((current) => ({ ...current, notes: event.target.value }))}
                            />
                          </label>
                          <div className='full-width form-actions'>
                            <button type='button' onClick={() => void handleCreateEmrEndpointProfile()} disabled={isBusy}>
                              Save endpoint profile
                            </button>
                          </div>
                        </div>
                      </section>
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
                                    setEditingWorkflowVersionId(null)
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
                                    <span className='button-row'>
                                      <button type='button' className='ghost-button' onClick={() => loadWorkflowVersionForEditing(version)} disabled={isBusy}>
                                        {version.status === 'draft' ? 'Edit draft' : 'Use as draft'}
                                      </button>
                                      {version.status === 'draft' ? (
                                        <button type='button' className='ghost-button' onClick={() => void publishWorkflowVersion(version.id)} disabled={isBusy}>
                                          Publish
                                        </button>
                                      ) : (
                                        <span>{formatDateTime(version.published_at || version.archived_at)}</span>
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
                          <h4>{editingWorkflowVersionId ? 'Edit draft version' : 'Create draft version'}</h4>
                          <div className='rule-alert'>
                            <strong>Manager/admin-editable checklist workflow</strong>
                            <p>
                              Seed a draft from the canonical 42-step checklist, adjust the workflow JSON for R3 operations, create the draft, then publish it when approved.
                            </p>
                            <div className='form-actions'>
                              <button type='button' className='ghost-button' onClick={() => void seedWorkflowDraftFromCanonicalChecklist()} disabled={isBusy}>
                                Seed draft from 42-step checklist
                              </button>
                              <button type='button' className='ghost-button' onClick={clearWorkflowVersionEditor} disabled={isBusy}>
                                Reset editor
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
                                {editingWorkflowVersionId ? 'Save draft edits' : 'Create draft version'}
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

      {appDialog ? <AppDialogModal dialog={appDialog} onClose={() => setAppDialog(null)} /> : null}

      {confirmDialog ? <ConfirmDialogModal dialog={confirmDialog} onCancel={() => setConfirmDialog(null)} /> : null}

      <footer className='app-footer' aria-label='Application version'>
        <span>IZ Clinical Notes Analyzer</span>
        <span>{versionLabel}</span>
      </footer>
    </main>
  )
}

export default App
