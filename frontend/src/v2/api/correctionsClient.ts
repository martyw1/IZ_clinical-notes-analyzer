import { readRecordList, readRecordPayload, readString } from './json'
import { request } from './request'
import type { CorrectionQueueItem, CorrectionSubmissionPayload } from './types'

export async function getCorrectionQueue(token: string): Promise<readonly CorrectionQueueItem[]> {
  const payload = await readRecordPayload(await request('/api/v2/corrections', { token }))
  return readRecordList(payload, 'items').map((item) => ({
    patientId: readString(item, 'patient_id'), patientDisplayLabel: readString(item, 'patient_display_label'),
    criterionId: readString(item, 'criterion_id'), criterionTitle: readString(item, 'criterion_title'),
    returnComment: readString(item, 'return_comment'), returnedByUsername: readString(item, 'returned_by_username'),
    returnedAt: readString(item, 'returned_at'),
  }))
}

export async function submitCorrection(token: string, patientId: string, payload: CorrectionSubmissionPayload): Promise<void> {
  await request(`/api/v2/treatment-plans/${patientId}/correction-submissions`, {
    token, method: 'POST', body: { criterion_id: payload.criterionId, comment: payload.comment },
  })
}
