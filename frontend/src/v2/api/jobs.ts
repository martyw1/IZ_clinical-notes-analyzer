import { readNumber, readRecordList, readRecordListPayload, readRecordPayload, readString } from './json'
import { mapArtifact, mapJob } from './jobMapper'
import { request } from './request'
import type { ApiHarnessArtifact, ApiHarnessJob, ApiHarnessPreview } from './types'

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

export async function listApiHarnessJobs(token: string): Promise<readonly ApiHarnessJob[]> {
  return (await readRecordListPayload(await request('/api/v2/api-harness/jobs', { token }))).map(mapJob)
}

export async function cancelApiHarnessJob(token: string, jobId: string): Promise<ApiHarnessJob> {
  return mapJob(
    await readRecordPayload(await request(`/api/v2/api-harness/jobs/${jobId}/cancel`, { token, method: 'POST' })),
  )
}

export async function listApiHarnessArtifacts(token: string, jobId: string): Promise<readonly ApiHarnessArtifact[]> {
  return (await readRecordListPayload(await request(`/api/v2/api-harness/jobs/${jobId}/artifacts`, { token }))).map(mapArtifact)
}

export async function getApiHarnessPreview(token: string, jobId: string): Promise<ApiHarnessPreview> {
  const payload = await readRecordPayload(await request(`/api/v2/api-harness/jobs/${jobId}/preview`, { token }))
  return {
    records: readRecordList(payload, 'records').map((record) => ({
      recordIndex: readNumber(record, 'record_index'),
      recordId: readString(record, 'record_id'),
      sourceEndpoint: readString(record, 'source_endpoint'),
      redactionStatus: readString(record, 'redaction_status'),
    })),
    message: readString(payload, 'message'),
  }
}

export async function downloadApiHarnessArtifact(token: string, jobId: string, artifact: ApiHarnessArtifact): Promise<void> {
  const response = await request(
    `/api/v2/api-harness/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(artifact.artifactId)}`,
    { token },
  )
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = artifact.name
  document.body.append(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
