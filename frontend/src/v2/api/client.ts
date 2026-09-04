import type { TreatmentPlanAggregate } from '../types/treatmentPlan'
import { readBoolean, readNumber, readRecord, readRecordList, readRecordListPayload, readRecordPayload, readString, readStringList } from './json'
import type { JsonRecord } from './json'
import { request } from './request'
import type {
  DashboardData,
  Facility,
  LoginResult,
  ManagerActionPayload,
  NavigationResult,
  PatientSelection,
  TreatmentPlanSelection,
  UserProfile,
  UserRole,
} from './types'
import { mapTreatmentPlanAggregate, mapTreatmentPlanList } from './treatmentPlanMapper'
import type { TreatmentPlanListData } from './types'
import type { PatientRecordId, SourceMode } from '../types/identity'
import { assertPlanIdentity, patientSelectionQuery, planSelectionBody, planSelectionQuery } from './identity'
export { getPatientRoster, getPatientRecordDetail, getTreatmentPlanRoster } from './rosterClient'

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

type TreatmentPlanListScope = {
  readonly sourceMode?: SourceMode
  readonly patientRecordId?: PatientRecordId
  readonly treatmentPlanId?: string
  readonly includeHistory?: boolean
}

export async function getTreatmentPlans(token: string, scope: TreatmentPlanListScope = {}): Promise<TreatmentPlanListData> {
  const query = new URLSearchParams()
  if (scope.sourceMode) query.set('source_mode', scope.sourceMode)
  if (scope.patientRecordId) query.set('patient_record_id', String(scope.patientRecordId))
  if (scope.treatmentPlanId) query.set('treatment_plan_id', scope.treatmentPlanId)
  if (scope.includeHistory) query.set('include_history', 'true')
  const suffix = query.size ? `?${query}` : ''
  return mapTreatmentPlanList(await readRecordPayload(await request(`/api/v2/treatment-plans${suffix}`, { token })))
}


export async function getTreatmentPlanDetail(
  token: string,
  selection: TreatmentPlanSelection,
): Promise<TreatmentPlanAggregate> {
  const path = `/api/v2/treatment-plans/${encodeURIComponent(selection.patientKey)}/${encodeURIComponent(selection.treatmentPlanId)}`
  const plan = mapTreatmentPlanAggregate(await readRecordPayload(
    await request(`${path}?${planSelectionQuery(selection)}`, { token }),
  ))
  assertPlanIdentity(plan, selection)
  return plan
}


export { importTreatmentPlanAggregate, importTreatmentPlanFile } from './manualImportClient'


export async function saveManagerAction(token: string, selection: TreatmentPlanSelection, payload: ManagerActionPayload): Promise<void> {
  await request(`/api/v2/treatment-plans/${encodeURIComponent(selection.patientKey)}/manager-actions`, {
    token,
    method: 'POST',
    body: {
      ...planSelectionBody(selection),
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

export async function assignPatient(token: string, selection: PatientSelection, counselorUsername: string): Promise<void> {
  await request(`/api/patient-assignments/${encodeURIComponent(selection.patientKey)}/${encodeURIComponent(counselorUsername)}?${patientSelectionQuery(selection)}`, { token, method: 'PUT' })
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
