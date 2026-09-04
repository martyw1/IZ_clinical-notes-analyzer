import type { PatientIdentity, PatientRecordId, PlanIdentity, PlanVersionId, SourceMode } from '../types/identity'
import { ApiRequestError, readString } from './json'
import type { JsonRecord } from './json'
import type { PatientSelection, TreatmentPlanSelection } from './types'

function isPatientRecordId(value: unknown): value is PatientRecordId {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}

function isPlanVersionId(value: unknown): value is PlanVersionId {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0
}

export function readPatientRecordId(record: JsonRecord): PatientRecordId {
  const value = record.patient_record_id
  if (isPatientRecordId(value)) return value
  throw new ApiRequestError(502, 'The local service returned an invalid patient-record identity. Refresh the roster.')
}

export function readPlanVersionId(record: JsonRecord): PlanVersionId {
  const value = record.plan_version_id
  if (isPlanVersionId(value)) return value
  throw new ApiRequestError(502, 'The local service returned an invalid treatment-plan version. Refresh the roster.')
}

export function readSourceMode(record: JsonRecord): SourceMode {
  switch (record.source_mode) {
    case 'manual_upload': return 'manual_upload'
    case 'alleva_rest_api': return 'alleva_rest_api'
    case 'synthetic_fixture': return 'synthetic_fixture'
    default: throw new ApiRequestError(502, 'The local service returned an unsupported record source. Refresh the roster.')
  }
}

export function readPlanIdentity(record: JsonRecord): PlanIdentity {
  return { patientRecordId: readPatientRecordId(record), planVersionId: readPlanVersionId(record), sourceMode: readSourceMode(record), treatmentPlanId: readString(record, 'treatment_plan_id') }
}

export function patientSelectionQuery(selection: PatientSelection): URLSearchParams {
  return new URLSearchParams({ patient_record_id: String(selection.patientRecordId), source_mode: selection.sourceMode })
}

export function planSelectionQuery(selection: TreatmentPlanSelection): URLSearchParams {
  const query = patientSelectionQuery(selection)
  query.set('plan_version_id', String(selection.planVersionId))
  query.set('treatment_plan_id', selection.treatmentPlanId)
  return query
}

export function planSelectionBody(selection: PlanIdentity): JsonRecord {
  return { patient_record_id: selection.patientRecordId, plan_version_id: selection.planVersionId, source_mode: selection.sourceMode, treatment_plan_id: selection.treatmentPlanId }
}

export function assertPatientIdentity(actual: PatientIdentity, selected: PatientIdentity): void {
  if (actual.patientRecordId !== selected.patientRecordId || actual.sourceMode !== selected.sourceMode) {
    throw new ApiRequestError(502, 'The returned record does not match the selected patient record. Refresh the roster.')
  }
}

export function assertPlanIdentity(actual: PlanIdentity, selected: PlanIdentity): void {
  assertPatientIdentity(actual, selected)
  if (actual.planVersionId !== selected.planVersionId || actual.treatmentPlanId !== selected.treatmentPlanId) {
    throw new ApiRequestError(502, 'The returned record does not match the selected treatment-plan version. Refresh the roster.')
  }
}
