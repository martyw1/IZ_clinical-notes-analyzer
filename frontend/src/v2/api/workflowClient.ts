import { isRecord, readBoolean, readNumber, readRecordList, readRecordListPayload, readRecordPayload, readString } from './json'
import { request } from './request'

export type WorkflowProfileVersion = {
  readonly id: number
  readonly version: number
  readonly status: string
  readonly versionNotes: string
}

export type WorkflowProfile = {
  readonly id: number
  readonly workflowKey: string
  readonly displayName: string
  readonly description: string
  readonly isActive: boolean
  readonly currentVersion: WorkflowProfileVersion | null
  readonly versions: readonly WorkflowProfileVersion[]
}

function mapVersion(record: Record<string, unknown>): WorkflowProfileVersion {
  return {
    id: readNumber(record, 'id'),
    version: readNumber(record, 'version'),
    status: readString(record, 'status'),
    versionNotes: readString(record, 'version_notes'),
  }
}

function mapProfile(record: Record<string, unknown>): WorkflowProfile {
  const currentVersion = record.current_version
  return {
    id: readNumber(record, 'id'),
    workflowKey: readString(record, 'workflow_key'),
    displayName: readString(record, 'display_name'),
    description: readString(record, 'description'),
    isActive: readBoolean(record, 'is_active'),
    currentVersion: isRecord(currentVersion) ? mapVersion(currentVersion) : null,
    versions: readRecordList(record, 'versions').map(mapVersion),
  }
}

export async function listWorkflowProfiles(token: string): Promise<readonly WorkflowProfile[]> {
  return (await readRecordListPayload(await request('/api/workflow-definitions', { token }))).map(mapProfile)
}

export async function createWorkflowProfile(token: string, workflowKey: string, displayName: string, description: string): Promise<WorkflowProfile> {
  const response = await request('/api/workflow-definitions', { token, method: 'POST', body: { workflow_key: workflowKey, display_name: displayName, description } })
  return mapProfile(await readRecordPayload(response))
}

export async function publishWorkflowProfile(token: string, profileId: number, versionId: number): Promise<WorkflowProfile> {
  const response = await request(`/api/workflow-definitions/${profileId}/versions/${versionId}/publish`, { token, method: 'POST' })
  return mapProfile(await readRecordPayload(response))
}
