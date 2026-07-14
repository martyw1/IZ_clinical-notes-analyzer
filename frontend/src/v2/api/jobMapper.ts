import { readBoolean, readNumber, readRecordList, readString } from './json'
import type { JsonRecord } from './json'
import type { ApiHarnessArtifact } from './types'
import type { ApiHarnessJob, JobStatus } from './jobTypes'

export function mapJob(record: JsonRecord): ApiHarnessJob {
  return {
    jobId: readString(record, 'job_id'),
    jobType: readString(record, 'job_type'),
    createdAt: readString(record, 'created_at'),
    startedAt: readString(record, 'started_at'),
    updatedAt: readString(record, 'updated_at'),
    completedAt: readString(record, 'completed_at'),
    status: mapJobStatus(readString(record, 'status')),
    phase: readString(record, 'phase'),
    message: readString(record, 'message'),
    progressPercent: readNumber(record, 'progress_percent'),
    currentEndpoint: readString(record, 'current_endpoint'),
    currentPage: readNumber(record, 'current_page'),
    recordsSeen: readNumber(record, 'records_seen'),
    recordsWritten: readNumber(record, 'records_written'),
    recordsFailed: readNumber(record, 'records_failed'),
    warningsCount: readNumber(record, 'warnings_count'),
    errorsCount: readNumber(record, 'errors_count'),
    cancelRequested: readBoolean(record, 'cancel_requested'),
    lastHeartbeatAt: readString(record, 'last_heartbeat_at'),
    artifacts: readRecordList(record, 'artifacts').map(mapArtifact),
  }
}

export function mapArtifact(record: JsonRecord): ApiHarnessArtifact {
  return {
    artifactId: readString(record, 'artifact_id'),
    name: readString(record, 'name'),
    mediaType: readString(record, 'media_type'),
    sizeBytes: readNumber(record, 'size_bytes'),
    redactionMode: readString(record, 'redaction_mode'),
  }
}

function mapJobStatus(value: string): JobStatus {
  switch (value) {
    case 'running':
      return 'running'
    case 'writing':
      return 'writing'
    case 'completed':
      return 'completed'
    case 'completed_with_warnings':
      return 'completed_with_warnings'
    case 'failed':
      return 'failed'
    case 'cancelled':
      return 'cancelled'
    case 'stale_or_interrupted':
      return 'stale_or_interrupted'
    default:
      return 'queued'
  }
}
