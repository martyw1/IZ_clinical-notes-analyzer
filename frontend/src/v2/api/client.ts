import type { TreatmentPlanAggregate } from '../types/treatmentPlan'
import { readBoolean, readNumber, readRecord, readRecordList, readRecordListPayload, readRecordPayload, readString, readStringList } from './json'
import type { JsonRecord } from './json'
import { request } from './request'
import type {
  DashboardData,
  Facility,
  LoginResult,
  ManualTreatmentPlanImportResult,
  ManagerActionPayload,
  NavigationResult,
  PatientRosterData,
  TreatmentPlanRosterData,
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

export async function getPatientRoster(token: string): Promise<PatientRosterData> {
  const payload = await readRecordPayload(await request('/api/v2/patient-roster', { token }))
  return {
    items: readRecordList(payload, 'items').map((item) => ({
      mrn: readString(item, 'mrn'),
      sourceMode: readString(item, 'source_mode', 'unknown'),
      lifecycleState: readString(item, 'lifecycle_state', 'unknown'),
      currentLevelOfCare: readString(item, 'current_level_of_care', 'Unknown'),
      treatmentPlans: readRecordList(item, 'treatment_plans').map((plan) => ({
        treatmentPlanId: readString(plan, 'treatment_plan_id'),
        lastUpdated: readString(plan, 'last_updated', 'Unknown'),
      })),
      firstSeenAt: readString(item, 'first_seen_at', 'Unknown'),
      lastSeenAt: readString(item, 'last_seen_at', 'Unknown'),
      reconciledAt: readString(item, 'reconciled_at', 'Not reconciled'),
    })),
  }
}

export async function getTreatmentPlanDetail(
  token: string,
  patientId: string,
  treatmentPlanId?: string,
  sourceMode?: string,
): Promise<TreatmentPlanAggregate> {
  const suffix = treatmentPlanId ? `/${encodeURIComponent(treatmentPlanId)}` : ''
  const query = sourceMode ? `?source_mode=${encodeURIComponent(sourceMode)}` : ''
  return mapTreatmentPlanAggregate(await readRecordPayload(
    await request(`/api/v2/treatment-plans/${encodeURIComponent(patientId)}${suffix}${query}`, { token }),
  ))
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
  files: readonly File[],
  patientId: string,
  confirmPatientIdCorrection: boolean,
): Promise<ManualTreatmentPlanImportResult> {
  const formData = new FormData()
  formData.set('patient_id', patientId)
  formData.set('confirm_patient_id_correction', String(confirmPatientIdCorrection))
  for (const file of files) formData.append('file', file)
  const result = await readRecordPayload(
    await request('/api/v2/manual-uploads/treatment-plan-file', { token, method: 'POST', formBody: formData }),
  )
  return mapManualTreatmentPlanImportResult(result)
}

function mapManualTreatmentPlanImportResult(record: Record<string, unknown>): ManualTreatmentPlanImportResult {
  const status = readString(record, 'status') === 'imported_with_warnings' ? 'imported_with_warnings' : 'imported'
  return {
    status,
    patientId: readString(record, 'patient_id'),
    patientDisplayLabel: readString(record, 'patient_display_label'),
    sourceMode: 'manual_upload',
    criteriaTotal: readNumber(record, 'criteria_total'),
    encryptedAtRest: readBoolean(record, 'encrypted_at_rest'),
    sourceFileArchived: readBoolean(record, 'source_file_archived'),
    sourceFileId: readString(record, 'source_file_id'),
    sourceFileIds: readStringList(record, 'source_file_ids'),
    patientIdCorrectionApplied: readBoolean(record, 'patient_id_correction_applied'),
    fileCount: readNumber(record, 'file_count', 1),
    parsedFileCount: readNumber(record, 'parsed_file_count', 1),
    opaqueFileCount: readNumber(record, 'opaque_file_count'),
    overallStatus: readString(record, 'overall_status'),
    warnings: readStringList(record, 'warnings'),
  }
}

export async function getTreatmentPlanRoster(token: string): Promise<TreatmentPlanRosterData> {
  const payload = await readRecordPayload(await request('/api/v2/treatment-plan-roster', { token }))
  return {
    items: readRecordList(payload, 'items').map((item) => ({
      treatmentPlanId: readString(item, 'treatment_plan_id'),
      mrn: readString(item, 'mrn'),
      lastUpdated: readString(item, 'last_updated', 'Unknown'),
      previousTreatmentPlanId: readString(item, 'previous_treatment_plan_id'),
      initialTreatmentPlanId: readString(item, 'initial_treatment_plan_id'),
      initialTreatmentPlanDate: readString(item, 'initial_treatment_plan_date', 'Unknown'),
    })),
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
