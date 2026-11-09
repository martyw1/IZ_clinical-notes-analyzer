import { readRecordPayload, readRecordList, readNumber, readString, readBoolean } from './json'
import type { JsonRecord } from './json'
import { request } from './request'

export type ClinicianAssignment = { patientRecordId: number; clinicianId: number | null; clinicianName: string; sourceClinicianName: string; origin: string; revision: number }
export type AssignmentPatient = ClinicianAssignment & { mrn: string; fullName: string; sourceMode: string }
function mapAssignment(row: JsonRecord): ClinicianAssignment {
  return { patientRecordId: readNumber(row, 'patient_record_id'), clinicianId: typeof row.clinician_id === 'number' ? row.clinician_id : null,
    clinicianName: readString(row,'clinician_name'), sourceClinicianName: readString(row,'source_clinician_name'), origin: readString(row,'origin'), revision: readNumber(row,'revision') }
}
export async function searchAssignmentPatients(token: string, query: string): Promise<{ items: AssignmentPatient[]; hasMore: boolean }> {
  const payload = await readRecordPayload(await request('/api/v2/clinician-assignment/patients/search',{token,method:'POST',body:{query}}))
  return { items: readRecordList(payload,'items').map((row)=>({...mapAssignment(row),mrn:readString(row,'mrn'),fullName:readString(row,'full_name'),sourceMode:readString(row,'source_mode')})),hasMore:readBoolean(payload,'has_more') }
}
export async function saveClinicianAssignment(token: string, patient: AssignmentPatient, mode: 'local'|'source', clinicianId: number|null): Promise<ClinicianAssignment> {
  return mapAssignment(await readRecordPayload(await request(`/api/v2/patient-records/${patient.patientRecordId}/clinician-assignment`,{token,method:'PUT',
    body:{mode,clinician_id:clinicianId,expected_revision:patient.revision}})))
}
