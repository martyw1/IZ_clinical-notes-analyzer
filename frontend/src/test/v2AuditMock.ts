export function auditLogsPayload() {
  return {
    items: [{
      event_id: 'evt-1', timestamp_utc: '2026-07-08T10:00:00Z', actor_username: 'admin', actor_role: 'admin',
      action: 'settings.api_profile.saved', details: { client_secret_configured: true },
      target_entity_type: 'api_connection_profile', target_entity_id: 'Alleva REST API', outcome_status: 'success',
    }, {
      event_id: 'evt-2', timestamp_utc: '2026-07-08T10:01:00Z', actor_username: 'admin', actor_role: 'admin',
      action: 'api_harness.job.failed', details: { error_class: 'HTTPStatusError', failure_stage: 'first_page', http_status: 503 },
      target_entity_type: 'api_harness_job', target_entity_id: 'job-synthetic', outcome_status: 'failure',
    }],
  }
}

export const auditVerificationPayload = { valid: true, event_count: 3, verified_event_count: 3, legacy_event_count: 0, first_invalid_id: null, verification_scope: 'all_events', privacy_mode: 'redacted_minimum_necessary', retention_hook: 'local_policy_required' }
