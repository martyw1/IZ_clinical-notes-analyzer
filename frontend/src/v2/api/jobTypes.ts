import type { ApiHarnessArtifact } from './types'

export type JobStatus =
  | 'queued'
  | 'running'
  | 'writing'
  | 'completed'
  | 'completed_with_warnings'
  | 'failed'
  | 'cancelled'
  | 'stale_or_interrupted'

export type ApiHarnessJob = {
  readonly jobId: string
  readonly jobType: string
  readonly createdAt: string
  readonly startedAt: string
  readonly updatedAt: string
  readonly completedAt: string
  readonly status: JobStatus
  readonly phase: string
  readonly message: string
  readonly progressPercent: number
  readonly currentEndpoint: string
  readonly currentPage: number
  readonly recordsSeen: number
  readonly recordsWritten: number
  readonly recordsFailed: number
  readonly warningsCount: number
  readonly errorsCount: number
  readonly cancelRequested: boolean
  readonly lastHeartbeatAt: string
  readonly artifacts: readonly ApiHarnessArtifact[]
}

export function isTerminalJobStatus(status: JobStatus): boolean {
  switch (status) {
    case 'completed':
    case 'completed_with_warnings':
    case 'failed':
    case 'cancelled':
    case 'stale_or_interrupted':
      return true
    case 'queued':
    case 'running':
    case 'writing':
      return false
  }
}

export function isSuccessfulJobStatus(status: JobStatus): boolean {
  return status === 'completed' || status === 'completed_with_warnings'
}
