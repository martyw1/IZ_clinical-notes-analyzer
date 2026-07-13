import { readBoolean, readNumber, readRecord, readRecordList, readRecordPayload, readString } from './json'
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
    detailsSummary: summarizeDetails(item),
  }))
}

function summarizeDetails(item: Record<string, unknown>): string {
  const details = readRecord(item, 'details')
  return Object.entries(details)
    .sort(([left], [right]) => left.localeCompare(right))
    .flatMap(([key, value]) => {
      const rendered = renderPrimitive(value)
      return rendered === null ? [] : [`${key}=${rendered}`]
    })
    .join('; ')
}

function renderPrimitive(value: unknown): string | null {
  if (value === null) return 'null'
  if (Array.isArray(value)) {
    const primitiveValues = value.filter((item): item is string | number | boolean => (
      typeof item === 'string' || typeof item === 'number' || typeof item === 'boolean'
    ))
    return primitiveValues.length === value.length ? primitiveValues.join(',') : null
  }
  switch (typeof value) {
    case 'string':
    case 'number':
    case 'boolean':
      return String(value)
    default:
      return null
  }
}

export async function verifyAuditLogs(token: string): Promise<AuditVerification> {
  const payload = await readRecordPayload(await request('/api/audit/verify', { token }))
  const firstInvalidId = payload.first_invalid_id
  return {
    valid: readBoolean(payload, 'valid'),
    eventCount: readNumber(payload, 'event_count'),
    verifiedEventCount: readNumber(payload, 'verified_event_count'),
    legacyEventCount: readNumber(payload, 'legacy_event_count'),
    firstInvalidId: typeof firstInvalidId === 'number' ? firstInvalidId : null,
    verificationScope: readString(payload, 'verification_scope'),
    privacyMode: readString(payload, 'privacy_mode'),
    retentionHook: readString(payload, 'retention_hook'),
  }
}
