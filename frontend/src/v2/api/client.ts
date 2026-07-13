import type { TreatmentPlanAggregate } from '../types/treatmentPlan'
import { readBoolean, readNumber, readRecord, readRecordList, readRecordListPayload, readRecordPayload, readString, readStringList } from './json'
import type { JsonRecord } from './json'
import { request } from './request'
import type {
  ApiHarnessJob,
  ApiConfiguration,
  AppSettings,
  DashboardData,
  Facility,
  LoginResult,
  ManualTreatmentPlanImportResult,
  ManagerActionPayload,
  NavigationResult,
  UserProfile,
  UserRole,
} from './types'
import { mapTreatmentPlanAggregate, mapTreatmentPlanList } from './treatmentPlanMapper'
import type { TreatmentPlanListData } from './types'

export async function login(username: string, password: string): Promise<LoginResult> {
  const payload = await readRecordPayload(
    await request('/api/auth/login', {
      method: 'POST',
      body: { username, password },
    }),
  )
  return mapLoginResult(payload)
}

function mapLoginResult(payload: JsonRecord): LoginResult {
  return {
    accessToken: readString(payload, 'access_token'),
    mustResetPassword: readBoolean(payload, 'must_reset_password'),
    authState: readString(payload, 'auth_state') === 'password_change_required' ? 'password_change_required' : 'active',
  }
}

export async function getCurrentUser(token: string): Promise<UserProfile> {
  return mapUser(await readRecordPayload(await request('/api/users/me', { token })))
}

export async function changeCurrentPassword(token: string, currentPassword: string, newPassword: string): Promise<LoginResult> {
  return mapLoginResult(
    await readRecordPayload(
      await request('/api/users/me/change-password', { token, method: 'POST', body: { current_password: currentPassword, new_password: newPassword } }),
    ),
  )
}

export async function getNavigation(token: string): Promise<NavigationResult> {
  const payload = await readRecordPayload(await request('/api/v2/navigation', { token }))
  return {
    items: readStringList(payload, 'items'),
    activeRuntime: readString(payload, 'active_runtime', 'v2'),
  }
}

export async function getDashboard(token: string): Promise<DashboardData> {
  const payload = await readRecordPayload(await request('/api/v2/dashboard', { token }))
  const metrics = readRecord(payload, 'metrics')
  return {
    refreshedAt: readString(payload, 'refreshed_at'),
    sourceCards: readRecordList(payload, 'source_cards').map((card) => ({
      label: readString(card, 'label'),
      status: readString(card, 'status'),
      detail: readString(card, 'detail'),
    })),
    metrics: mapNumberRecord(metrics),
    blockers: readStringList(payload, 'blockers'),
  }
}

export async function getTreatmentPlans(token: string): Promise<TreatmentPlanListData> {
  return mapTreatmentPlanList(await readRecordPayload(await request('/api/v2/treatment-plans', { token })))
}

export async function getTreatmentPlanDetail(token: string, patientId: string): Promise<TreatmentPlanAggregate> {
  return mapTreatmentPlanAggregate(await readRecordPayload(await request(`/api/v2/treatment-plans/${patientId}`, { token })))
}

export async function importTreatmentPlanAggregate(token: string, payload: JsonRecord): Promise<ManualTreatmentPlanImportResult> {
  const result = await readRecordPayload(
    await request('/api/v2/manual-uploads/treatment-plan-aggregate', {
      token,
      method: 'POST',
      body: payload,
    }),
  )
  return mapManualTreatmentPlanImportResult(result)
}

export async function importTreatmentPlanFile(
  token: string,
  file: File,
  patientId: string,
  confirmPatientIdCorrection: boolean,
): Promise<ManualTreatmentPlanImportResult> {
  const formData = new FormData()
  formData.set('patient_id', patientId)
  formData.set('confirm_patient_id_correction', String(confirmPatientIdCorrection))
  formData.set('file', file)
  const result = await readRecordPayload(
    await request('/api/v2/manual-uploads/treatment-plan-file', { token, method: 'POST', formBody: formData }),
  )
  return mapManualTreatmentPlanImportResult(result)
}

function mapManualTreatmentPlanImportResult(record: Record<string, unknown>): ManualTreatmentPlanImportResult {
  return {
    status: 'imported',
    patientId: readString(record, 'patient_id'),
    patientDisplayLabel: readString(record, 'patient_display_label'),
    sourceMode: 'manual_upload',
    criteriaTotal: readNumber(record, 'criteria_total'),
    encryptedAtRest: readBoolean(record, 'encrypted_at_rest'),
    sourceFileArchived: readBoolean(record, 'source_file_archived'),
    sourceFileId: readString(record, 'source_file_id'),
    patientIdCorrectionApplied: readBoolean(record, 'patient_id_correction_applied'),
  }
}

export async function saveManagerAction(token: string, patientId: string, payload: ManagerActionPayload): Promise<void> {
  await request(`/api/v2/treatment-plans/${patientId}/manager-actions`, {
    token,
    method: 'POST',
    body: {
      criterion_id: payload.criterionId,
      action: payload.action,
      comment: payload.comment,
      override_reason: payload.overrideReason,
    },
  })
}

export async function getSettings(token: string): Promise<AppSettings> {
  return mapSettings(await readRecordPayload(await request('/api/settings', { token })))
}

export async function saveSettings(token: string, settings: AppSettings): Promise<AppSettings> {
  return mapSettings(
    await readRecordPayload(
      await request('/api/settings', {
        token,
        method: 'PATCH',
        body: {
          organization_name: settings.organizationName,
          facility_timezone: settings.facilityTimezone,
          treatment_plan_master_due_days: settings.treatmentPlanMasterDueDays,
          treatment_plan_php_review_interval_days: settings.treatmentPlanPhpReviewIntervalDays,
          treatment_plan_iop_op_review_interval_days: settings.treatmentPlanIopOpReviewIntervalDays,
          treatment_plan_loc_change_window_days: settings.treatmentPlanLocChangeWindowDays,
          treatment_plan_loc_change_window_validated: settings.treatmentPlanLocChangeWindowValidated,
        },
      }),
    ),
  )
}

export async function getApiConfiguration(token: string): Promise<ApiConfiguration> {
  return mapApiConfiguration(await readRecordPayload(await request('/api/api-configuration', { token })))
}

export async function saveApiConfiguration(token: string, config: ApiConfiguration, clientSecret: string): Promise<ApiConfiguration> {
  return mapApiConfiguration(
    await readRecordPayload(
      await request('/api/api-configuration', {
        token,
        method: 'PATCH',
        body: {
          vendor_name: config.vendorName,
          api_base_url: config.apiBaseUrl,
          openapi_url: config.openapiUrl,
          token_url: config.tokenUrl,
          client_id: config.clientId,
          client_secret: clientSecret || undefined,
          token_auth_style: config.tokenAuthStyle,
          scopes: config.scopes,
          pagination_limit: config.paginationLimit,
          sync_limit: config.syncLimit,
          timeout_seconds: config.timeoutSeconds,
          api_enabled: config.apiEnabled,
          treatment_plan_sync_enabled: config.treatmentPlanSyncEnabled,
          treatment_plan_sync_approved: config.treatmentPlanSyncApproved,
          treatment_plan_endpoint_mapping_validated: config.treatmentPlanEndpointMappingValidated,
        },
      }),
    ),
  )
}

export async function listUsers(token: string): Promise<readonly UserProfile[]> {
  return (await readRecordListPayload(await request('/api/users', { token }))).map(mapUser)
}

export async function listFacilities(token: string): Promise<readonly Facility[]> {
  return (await readRecordListPayload(await request('/api/facilities', { token }))).map((record) => ({
    id: readNumber(record, 'id'),
    facilityKey: readString(record, 'facility_key'),
    displayName: readString(record, 'display_name'),
    timezone: readString(record, 'timezone'),
    isActive: readBoolean(record, 'is_active'),
  }))
}

export async function assignUserFacility(token: string, userId: number, facilityId: number): Promise<void> {
  await request(`/api/users/${userId}/facilities/${facilityId}`, { token, method: 'PUT' })
}

export async function assignPatient(token: string, patientId: string, counselorUsername: string): Promise<void> {
  await request(`/api/patient-assignments/${encodeURIComponent(patientId)}/${encodeURIComponent(counselorUsername)}`, { token, method: 'PUT' })
}

export async function runApprovedAllevaTreatmentPlanSync(token: string): Promise<ApiHarnessJob> {
  const payload = await readRecordPayload(await request('/api/v2/alleva-sync/run', { token, method: 'POST' }))
  return {
    jobId: readString(payload, 'job_id'),
    status: readString(payload, 'status'),
    progressPercent: readNumber(payload, 'progress_percent'),
    recordsWritten: readNumber(payload, 'records_written'),
    recordsFailed: readNumber(payload, 'records_failed'),
    warningsCount: readNumber(payload, 'warnings_count'),
    artifacts: [],
  }
}

export async function getApprovedAllevaTreatmentPlanSyncJob(token: string, jobId: string): Promise<ApiHarnessJob> {
  const payload = await readRecordPayload(await request(`/api/v2/alleva-sync/jobs/${jobId}`, { token }))
  return {
    jobId: readString(payload, 'job_id'),
    status: readString(payload, 'status'),
    progressPercent: readNumber(payload, 'progress_percent'),
    recordsWritten: readNumber(payload, 'records_written'),
    recordsFailed: readNumber(payload, 'records_failed'),
    warningsCount: readNumber(payload, 'warnings_count'),
    artifacts: [],
  }
}

export async function createUser(token: string, username: string, fullName: string, role: UserRole, password: string): Promise<UserProfile> {
  return mapUser(
    await readRecordPayload(
      await request('/api/users', { token, method: 'POST', body: { username, full_name: fullName, role, password } }),
    ),
  )
}

export async function resetUserPassword(token: string, userId: number, newPassword: string): Promise<UserProfile> {
  return mapUser(
    await readRecordPayload(
      await request(`/api/users/${userId}/reset-password`, { token, method: 'POST', body: { new_password: newPassword, require_reset_on_login: true } }),
    ),
  )
}

function mapUser(record: Record<string, unknown>): UserProfile {
  return {
    id: readNumber(record, 'id'),
    username: readString(record, 'username'),
    fullName: readString(record, 'full_name'),
    role: mapRole(readString(record, 'role')),
    isActive: readBoolean(record, 'is_active'),
    isLocked: readBoolean(record, 'is_locked'),
    mustResetPassword: readBoolean(record, 'must_reset_password'),
    authState: mapAuthState(readString(record, 'auth_state', 'active')),
    lockedUntil: readString(record, 'locked_until'),
    facilityIds: Array.isArray(record.facility_ids)
      ? record.facility_ids.filter((value): value is number => typeof value === 'number')
      : [],
  }
}

function mapAuthState(value: string): UserProfile['authState'] {
  switch (value) {
    case 'bootstrap_required':
      return 'bootstrap_required'
    case 'password_change_required':
      return 'password_change_required'
    case 'locked_until':
      return 'locked_until'
    default:
      return 'active'
  }
}

export async function resumeApprovedAllevaTreatmentPlanSync(token: string, jobId: string): Promise<ApiHarnessJob> {
  const payload = await readRecordPayload(await request(`/api/v2/alleva-sync/jobs/${jobId}/resume`, { token, method: 'POST' }))
  return {
    jobId: readString(payload, 'job_id'),
    status: readString(payload, 'status'),
    progressPercent: readNumber(payload, 'progress_percent'),
    recordsWritten: readNumber(payload, 'records_written'),
    recordsFailed: readNumber(payload, 'records_failed'),
    warningsCount: readNumber(payload, 'warnings_count'),
    artifacts: [],
  }
}

function mapRole(value: string): UserRole {
  switch (value) {
    case 'admin':
      return 'admin'
    case 'office_manager':
      return 'office_manager'
    case 'viewer':
      return 'viewer'
    default:
      return 'counselor'
  }
}

function mapNumberRecord(record: Record<string, unknown>): Record<string, number> {
  const numbers: Record<string, number> = {}
  for (const [key, value] of Object.entries(record)) {
    if (typeof value === 'number') numbers[key] = value
  }
  return numbers
}

function mapSettings(record: Record<string, unknown>): AppSettings {
  const locWindow = record.treatment_plan_loc_change_window_days
  return {
    organizationName: readString(record, 'organization_name'),
    facilityTimezone: readString(record, 'facility_timezone'),
    treatmentPlanMasterDueDays: readNumber(record, 'treatment_plan_master_due_days'),
    treatmentPlanPhpReviewIntervalDays: readNumber(record, 'treatment_plan_php_review_interval_days'),
    treatmentPlanIopOpReviewIntervalDays: readNumber(record, 'treatment_plan_iop_op_review_interval_days'),
    treatmentPlanLocChangeWindowDays: typeof locWindow === 'number' ? locWindow : null,
    treatmentPlanLocChangeWindowValidated: readBoolean(record, 'treatment_plan_loc_change_window_validated'),
  }
}

function mapApiConfiguration(record: Record<string, unknown>): ApiConfiguration {
  return {
    vendorName: readString(record, 'vendor_name'),
    apiBaseUrl: readString(record, 'api_base_url'),
    openapiUrl: readString(record, 'openapi_url'),
    tokenUrl: readString(record, 'token_url'),
    clientId: readString(record, 'client_id'),
    apiKeyConfigured: readBoolean(record, 'api_key_configured'),
    clientSecretConfigured: readBoolean(record, 'client_secret_configured'),
    tokenAuthStyle: readString(record, 'token_auth_style', 'body'),
    scopes: readString(record, 'scopes'),
    paginationLimit: readNumber(record, 'pagination_limit', 500),
    syncLimit: readNumber(record, 'sync_limit', 100),
    timeoutSeconds: readNumber(record, 'timeout_seconds', 10),
    apiEnabled: readBoolean(record, 'api_enabled'),
    treatmentPlanSyncEnabled: readBoolean(record, 'treatment_plan_sync_enabled'),
    treatmentPlanSyncApproved: readBoolean(record, 'treatment_plan_sync_approved'),
    treatmentPlanEndpointMappingValidated: readBoolean(record, 'treatment_plan_endpoint_mapping_validated'),
    activeContractVersion: readString(record, 'active_contract_version'),
    activeContractEffectiveAt: readString(record, 'active_contract_effective_at'),
  }
}
