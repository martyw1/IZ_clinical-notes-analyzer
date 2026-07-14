import { readBoolean, readNumber, readRecordPayload, readString } from './json'
import type { JsonRecord } from './json'
import { request } from './request'
import type { ApiConfiguration, AppSettings } from './configurationTypes'

export async function getSettings(token: string): Promise<AppSettings> {
  return mapSettings(await readRecordPayload(await request('/api/settings', { token })))
}

export async function saveSettings(token: string, settings: AppSettings): Promise<AppSettings> {
  return mapSettings(await readRecordPayload(await request('/api/settings', {
    token,
    method: 'PATCH',
    body: {
      organization_name: settings.organizationName,
      facility_timezone: settings.facilityTimezone,
      treatment_plan_master_due_days: settings.treatmentPlanMasterDueDays,
      treatment_plan_php_review_interval_days: settings.treatmentPlanPhpReviewIntervalDays,
      treatment_plan_iop_op_review_interval_days: settings.treatmentPlanIopOpReviewIntervalDays,
      treatment_plan_loc_change_window_days: settings.treatmentPlanLocChangeWindowDays,
      treatment_plan_loc_change_window_validated: settings.treatmentPlanLocChangeWindowValidated,
    },
  })))
}

export async function getApiConfiguration(token: string): Promise<ApiConfiguration> {
  return mapApiConfiguration(await readRecordPayload(await request('/api/api-configuration', { token })))
}

export async function saveApiConfiguration(
  token: string,
  config: ApiConfiguration,
  clientId: string,
  clientSecret: string,
): Promise<ApiConfiguration> {
  const credentials: Record<string, unknown> = {}
  if (clientId.trim()) credentials.client_id = clientId.trim()
  if (clientSecret) credentials.client_secret = clientSecret
  return mapApiConfiguration(await readRecordPayload(await request('/api/api-configuration', {
    token,
    method: 'PATCH',
    body: {
      vendor_name: config.vendorName,
      api_base_url: config.apiBaseUrl,
      openapi_url: config.openapiUrl,
      token_url: config.tokenUrl,
      token_auth_style: config.tokenAuthStyle,
      scopes: config.scopes,
      api_version: config.apiVersion,
      treatment_plan_start_date: config.treatmentPlanStartDate,
      pagination_limit: config.paginationLimit,
      sync_limit: config.syncLimit,
      requests_per_minute: config.requestsPerMinute,
      timeout_seconds: config.timeoutSeconds,
      api_enabled: config.apiEnabled,
      treatment_plan_sync_enabled: config.treatmentPlanSyncEnabled,
      treatment_plan_sync_approved: config.treatmentPlanSyncApproved,
      ...credentials,
    },
  })))
}

function mapSettings(record: JsonRecord): AppSettings {
  const locWindow = record.treatment_plan_loc_change_window_days
  return {
    organizationName: readString(record, 'organization_name'),
    facilityTimezone: readString(record, 'facility_timezone'),
    treatmentPlanMasterDueDays: readNumber(record, 'treatment_plan_master_due_days'),
    treatmentPlanPhpReviewIntervalDays: readNumber(record, 'treatment_plan_php_review_interval_days'),
    treatmentPlanIopOpReviewIntervalDays: readNumber(record, 'treatment_plan_iop_op_review_interval_days'),
    treatmentPlanLocChangeWindowDays: typeof locWindow === 'number' ? locWindow : null,
    treatmentPlanLocChangeWindowValidated: readBoolean(record, 'treatment_plan_loc_change_window_validated'),
  }
}

function mapApiConfiguration(record: JsonRecord): ApiConfiguration {
  return {
    vendorName: readString(record, 'vendor_name'),
    apiBaseUrl: readString(record, 'api_base_url'),
    openapiUrl: readString(record, 'openapi_url'),
    tokenUrl: readString(record, 'token_url'),
    clientIdConfigured: readBoolean(record, 'client_id_configured'),
    apiKeyConfigured: readBoolean(record, 'api_key_configured'),
    clientSecretConfigured: readBoolean(record, 'client_secret_configured'),
    tokenAuthStyle: readString(record, 'token_auth_style', 'body'),
    scopes: readString(record, 'scopes'),
    apiVersion: readString(record, 'api_version', '1.0'),
    treatmentPlanStartDate: readString(record, 'treatment_plan_start_date'),
    paginationLimit: readNumber(record, 'pagination_limit', 500),
    syncLimit: readNumber(record, 'sync_limit', 100),
    requestsPerMinute: readNumber(record, 'requests_per_minute', 600),
    timeoutSeconds: readNumber(record, 'timeout_seconds', 10),
    apiEnabled: readBoolean(record, 'api_enabled'),
    treatmentPlanSyncEnabled: readBoolean(record, 'treatment_plan_sync_enabled'),
    treatmentPlanSyncApproved: readBoolean(record, 'treatment_plan_sync_approved'),
    activeContractVersion: readString(record, 'active_contract_version'),
    activeContractEffectiveAt: readString(record, 'active_contract_effective_at'),
  }
}
