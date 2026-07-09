import { readNumber, readRecordList, readRecordListPayload, readRecordPayload, readString } from './json'
import { request } from './request'
import type { ApiHarnessArtifact, ApiHarnessJob } from './types'

export async function startApiHarnessJob(token: string): Promise<ApiHarnessJob> {
  return mapJob(
    await readRecordPayload(
      await request('/api/v2/api-harness/jobs', {
        token,
        method: 'POST',
        body: { job_type: 'pull_all_treatment_plans_all_fields' },
      }),
    ),
  )
}

export async function getApiHarnessJob(token: string, jobId: string): Promise<ApiHarnessJob> {
  return mapJob(await readRecordPayload(await request(`/api/v2/api-harness/jobs/${jobId}`, { token })))
}

export async function listApiHarnessArtifacts(token: string, jobId: string): Promise<readonly ApiHarnessArtifact[]> {
  return (await readRecordListPayload(await request(`/api/v2/api-harness/jobs/${jobId}/artifacts`, { token }))).map(mapArtifact)
}

function mapJob(record: Record<string, unknown>): ApiHarnessJob {
  return {
    jobId: readString(record, 'job_id'),
    status: readString(record, 'status'),
    progressPercent: readNumber(record, 'progress_percent'),
    recordsWritten: readNumber(record, 'records_written'),
    recordsFailed: readNumber(record, 'records_failed'),
    warningsCount: readNumber(record, 'warnings_count'),
    artifacts: readRecordList(record, 'artifacts').map(mapArtifact),
  }
}

function mapArtifact(record: Record<string, unknown>): ApiHarnessArtifact {
  return {
    artifactId: readString(record, 'artifact_id'),
    name: readString(record, 'name'),
    mediaType: readString(record, 'media_type'),
    sizeBytes: readNumber(record, 'size_bytes'),
    redactionMode: readString(record, 'redaction_mode'),
  }
}
