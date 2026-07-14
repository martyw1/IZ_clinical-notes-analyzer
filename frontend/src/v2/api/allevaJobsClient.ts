import { readRecordListPayload, readRecordPayload } from './json'
import { mapJob } from './jobMapper'
import { request } from './request'
import type { ApiHarnessJob } from './jobTypes'

export async function runApprovedAllevaTreatmentPlanSync(token: string): Promise<ApiHarnessJob> {
  return mapJob(await readRecordPayload(await request('/api/v2/alleva-sync/run', { token, method: 'POST' })))
}

export async function getApprovedAllevaTreatmentPlanSyncJob(token: string, jobId: string): Promise<ApiHarnessJob> {
  return mapJob(await readRecordPayload(await request(`/api/v2/alleva-sync/jobs/${jobId}`, { token })))
}

export async function resumeApprovedAllevaTreatmentPlanSync(token: string, jobId: string): Promise<ApiHarnessJob> {
  return mapJob(await readRecordPayload(await request(`/api/v2/alleva-sync/jobs/${jobId}/resume`, { token, method: 'POST' })))
}

export async function getLatestApprovedAllevaTreatmentPlanSyncJob(token: string): Promise<ApiHarnessJob | null> {
  const jobs = (await readRecordListPayload(await request('/api/v2/api-harness/jobs', { token }))).map(mapJob)
  return jobs.find((job) => job.jobType === 'approved_treatment_plan_sync') ?? null
}

export async function runActivePatientRosterPull(token: string): Promise<ApiHarnessJob> {
  return mapJob(await readRecordPayload(await request('/api/v2/patient-roster/pull', { token, method: 'POST' })))
}

export async function getActivePatientRosterJob(token: string, jobId: string): Promise<ApiHarnessJob> {
  return mapJob(await readRecordPayload(await request(`/api/v2/patient-roster/jobs/${jobId}`, { token })))
}

export async function getLatestActivePatientRosterJob(token: string): Promise<ApiHarnessJob> {
  return mapJob(await readRecordPayload(await request('/api/v2/patient-roster/jobs/latest', { token })))
}
