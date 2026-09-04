import { readPlanIdentity } from './identity'
import { readBoolean, readNumber, readRecordPayload, readString, readStringList } from './json'
import type { JsonRecord } from './json'
import { request } from './request'
import type { ManualTreatmentPlanImportResult } from './types'

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
    ...readPlanIdentity(record),
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
