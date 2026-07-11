import { readBoolean, readNumber, readRecordList, readRecordPayload, readString } from './json'
import { request } from './request'
import type { AuditLogItem, AuditVerification } from './types'

export async function listAuditLogs(token: string): Promise<readonly AuditLogItem[]> {
  const payload = await readRecordPayload(await request('/api/audit/logs', { token }))
  return readRecordList(payload, 'items').map((item) => ({
    eventId: readString(item, 'event_id'),
    timestampUtc: readString(item, 'timestamp_utc'),
    actorUsername: readString(item, 'actor_username'),
    actorRole: readString(item, 'actor_role'),
    action: readString(item, 'action'),
    targetEntityType: readString(item, 'target_entity_type'),
    targetEntityId: readString(item, 'target_entity_id'),
    outcomeStatus: readString(item, 'outcome_status'),
  }))
}

export async function verifyAuditLogs(token: string): Promise<AuditVerification> {
  const payload = await readRecordPayload(await request('/api/audit/verify', { token }))
  const firstInvalidId = payload.first_invalid_id
  return {
    valid: readBoolean(payload, 'valid'),
    eventCount: readNumber(payload, 'event_count'),
    firstInvalidId: typeof firstInvalidId === 'number' ? firstInvalidId : null,
    privacyMode: readString(payload, 'privacy_mode'),
    retentionHook: readString(payload, 'retention_hook'),
  }
}
