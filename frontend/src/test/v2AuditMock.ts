export function auditLogsPayload() {
  return {
    items: [{
      event_id: 'evt-1', timestamp_utc: '2026-07-08T10:00:00Z', actor_username: 'admin', actor_role: 'admin',
      action: 'settings.api_profile.saved', details: { client_secret_configured: true },
      target_entity_type: 'api_connection_profile', target_entity_id: 'Alleva REST API', outcome_status: 'success', prev_hash: '0', hash: 'abc',
    }],
  }
}

export const auditVerificationPayload = { valid: true, event_count: 3, first_invalid_id: null, privacy_mode: 'redacted_minimum_necessary', retention_hook: 'local_policy_required' }
