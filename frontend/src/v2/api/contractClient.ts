import { readRecordPayload, readString } from './json'
import { request } from './request'
import type { ApiConfiguration } from './types'

export type AllevaContractApprovalInput = {
  readonly contractVersion: string
  readonly testPopulationReference: string
  readonly maximumRequestsPerMinute: number
  readonly retryAfterSeconds: number
}

export type AllevaContractApprovalResult = {
  readonly contractVersion: string
  readonly contractSha256: string
}

export async function approvePublishedAllevaV1Contract(
  token: string,
  config: ApiConfiguration,
  input: AllevaContractApprovalInput,
): Promise<AllevaContractApprovalResult> {
  const payload = await readRecordPayload(await request('/api/v2/alleva-sync/contracts', {
    token,
    method: 'POST',
    body: publishedAllevaV1Contract(config, input),
  }))
  return {
    contractVersion: readString(payload, 'contract_version'),
    contractSha256: readString(payload, 'contract_sha256'),
  }
}

function publishedAllevaV1Contract(
  config: ApiConfiguration,
  input: AllevaContractApprovalInput,
): Record<string, unknown> {
  return {
    contract_version: input.contractVersion.trim(),
    api_base_url: config.apiBaseUrl,
    effective_at: new Date().toISOString(),
    vendor_documentation_url: config.openapiUrl,
    test_population_reference: input.testPopulationReference.trim(),
    oauth: {
      token_url: config.tokenUrl,
      token_auth_style: config.tokenAuthStyle === 'basic' ? 'basic' : 'body',
      scope: config.scopes,
    },
    pagination: {
      limit_parameter: 'Limit',
      offset_parameter: 'Cursor',
      maximum_page_size: config.paginationLimit,
      maximum_records: config.syncLimit,
      maximum_response_bytes: 1_048_576,
    },
    rate_limit: {
      maximum_requests_per_minute: input.maximumRequestsPerMinute,
      retry_after_seconds: input.retryAfterSeconds,
    },
    attachments: { mode: 'disabled', download_allowed: false },
    endpoints: {
      clients: {
        path: '/clients',
        parameters: { limit: 'Limit', offset: 'Cursor' },
        field_mappings: {
          client_id: 'id',
          lifecycle_status: 'status',
          level_of_care: 'levelOfCare',
          admission_date: 'admissionDateTime',
        },
      },
      treatment_plans: {
        path: '/treatment-plans',
        parameters: { limit: 'Limit', offset: 'Cursor', client_id: 'ClientId' },
        field_mappings: { client_id: 'client.id', client_reference: 'client.route', plan_id: 'id' },
      },
      treatment_plan_detail: {
        path: '/treatment-plans/{plan_id}',
        parameters: {},
        field_mappings: {
          reason_for_admission: 'reasonForAdmission',
          initial_client_needs: 'initialClientNeeds',
          family_education_needs: 'familyEducationNeeds',
          last_modified: 'lastModified',
          problem_description: 'problems.description',
          behavioral_definition: 'problems.behavioralDefinitions.description',
          goal_description: 'problems.goals.description',
          objective_description: 'problems.goals.objectives.description',
          intervention_description: 'problems.goals.objectives.interventions.description',
        },
      },
      diagnoses: {
        path: '/treatment-plans/{plan_id}/diagnosis',
        parameters: {},
        field_mappings: { description: 'description', icd10_code: 'code' },
      },
      reviews: {
        path: '/treatment-reviews',
        parameters: { limit: 'Limit', offset: 'Cursor' },
        field_mappings: { review_id: 'id', treatment_plan_review_id: 'treatmentPlanReviewId' },
      },
      review_detail: {
        path: '/treatment-reviews/{review_id}',
        parameters: {},
        field_mappings: { review_date: 'createdDated', signature_date: 'creatorSignatureDate' },
      },
    },
  }
}
