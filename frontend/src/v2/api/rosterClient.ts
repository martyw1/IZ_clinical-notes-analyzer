import { assertPatientIdentity, patientSelectionQuery, readPatientRecordId, readPlanIdentity, readSourceMode } from './identity'
import { readBoolean, readNumber, readRecord, readRecordList, readRecordPayload, readString } from './json'
import type { JsonRecord } from './json'
import { request } from './request'
import type { PatientRecordDetail, PatientRosterData, PatientRosterTreatmentPlan, PatientSelection, SourceMode, TreatmentPlanRosterData } from './types'

export function sourceFilterQuery(sourceMode?: SourceMode): string {
  return sourceMode ? `?source_mode=${sourceMode}` : ''
}

function mapPatientPlan(record: JsonRecord): PatientRosterTreatmentPlan {
  return {
    ...readPlanIdentity(record),
    lastUpdated: readString(record, 'last_updated', 'Unknown'),
    versionOrdinal: readNumber(record, 'version_ordinal'),
    originalPlanReference: readString(record, 'original_plan_reference'),
    serviceDate: readString(record, 'service_date'),
  }
}

export async function getPatientRoster(token: string, sourceMode?: SourceMode): Promise<PatientRosterData> {
  const payload = await readRecordPayload(await request(`/api/v2/patient-roster${sourceFilterQuery(sourceMode)}`, { token }))
  return {
    items: readRecordList(payload, 'items').map((item) => ({
      patientRecordId: readPatientRecordId(item),
      mrn: readString(item, 'mrn'),
      fullName: readString(item, 'full_name'),
      sourceMode: readSourceMode(item),
      lifecycleState: readString(item, 'lifecycle_state', 'unknown'),
      currentLevelOfCare: readString(item, 'current_level_of_care', 'Unknown'),
      treatmentPlans: readRecordList(item, 'treatment_plans').map(mapPatientPlan),
      firstSeenAt: readString(item, 'first_seen_at', 'Unknown'),
      lastSeenAt: readString(item, 'last_seen_at', 'Unknown'),
      reconciledAt: readString(item, 'reconciled_at', 'Not reconciled'),
    })),
  }
}

export async function getPatientRecordDetail(token: string, selection: PatientSelection): Promise<PatientRecordDetail> {
  const record = await readRecordPayload(await request(`/api/v2/patients/${encodeURIComponent(selection.patientKey)}?${patientSelectionQuery(selection)}`, { token }))
  const detail = {
    patientRecordId: readPatientRecordId(record),
    mrn: readString(record, 'mrn'),
    fullName: readString(record, 'full_name'),
    sourceMode: readSourceMode(record),
    lifecycleState: readString(record, 'lifecycle_state', 'unknown'),
    currentLevelOfCare: readString(record, 'current_level_of_care', 'Unknown'),
    sourceLastUpdated: readString(record, 'source_last_updated', 'Unknown'),
    firstSeenAt: readString(record, 'first_seen_at', 'Unknown'),
    lastSeenAt: readString(record, 'last_seen_at', 'Unknown'),
    reconciledAt: readString(record, 'reconciled_at', 'Not reconciled'),
    treatmentPlans: readRecordList(record, 'treatment_plans').map(mapPatientPlan),
    patientRecord: readRecord(record, 'patient_record'),
  }
  assertPatientIdentity(detail, selection)
  return detail
}

export async function getTreatmentPlanRoster(token: string, sourceMode?: SourceMode): Promise<TreatmentPlanRosterData> {
  const payload = await readRecordPayload(await request(`/api/v2/treatment-plan-roster${sourceFilterQuery(sourceMode)}`, { token }))
  return {
    items: readRecordList(payload, 'items').map((item) => ({
      ...mapPatientPlan(item),
      mrn: readString(item, 'mrn'),
      patientKey: readString(item, 'patient_key'),
      linkedToMrn: readBoolean(item, 'linked_to_mrn'),
      fullName: readString(item, 'full_name'),
      previousTreatmentPlanId: readString(item, 'previous_treatment_plan_id'),
      initialTreatmentPlanId: readString(item, 'initial_treatment_plan_id'),
      initialTreatmentPlanDate: readString(item, 'initial_treatment_plan_date', 'Unknown'),
    })),
  }
}
