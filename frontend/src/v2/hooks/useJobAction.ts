import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiRequestError } from '../api/json'
import { isSuccessfulJobStatus, isTerminalJobStatus } from '../api/jobTypes'
import type { ApiHarnessJob } from '../api/jobTypes'

type JobActionOptions = {
  readonly start: () => Promise<ApiHarnessJob>
  readonly poll: (jobId: string) => Promise<ApiHarnessJob>
  readonly onCompleted?: (job: ApiHarnessJob) => void | Promise<void>
  readonly failureMessage: string
  readonly successMessage?: (job: ApiHarnessJob) => string
}

type JobActionState = {
  readonly job: ApiHarnessJob | null
  readonly isActive: boolean
  readonly message: string
  readonly error: string
  readonly run: () => Promise<void>
  readonly setLastJob: (job: ApiHarnessJob | null) => void
}

export function useJobAction(options: JobActionOptions): JobActionState {
  const mounted = useRef(true)
  const activeRef = useRef(false)
  const [job, setJob] = useState<ApiHarnessJob | null>(null)
  const [isActive, setIsActive] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  useEffect(() => () => { mounted.current = false }, [])

  const run = useCallback(async () => {
    if (activeRef.current) return
    activeRef.current = true
    setIsActive(true)
    setMessage('')
    setError('')
    try {
      let current = await options.start()
      if (mounted.current) setJob(current)
      for (let attempt = 0; attempt < 240 && !isTerminalJobStatus(current.status); attempt += 1) {
        current = await options.poll(current.jobId)
        if (mounted.current) setJob(current)
        if (!isTerminalJobStatus(current.status)) await delay(250)
      }
      if (!isTerminalJobStatus(current.status)) {
        if (mounted.current) setMessage('The job is still running. Return to this page to review its latest status.')
      } else if (isSuccessfulJobStatus(current.status)) {
        await options.onCompleted?.(current)
        if (mounted.current) setMessage(options.successMessage?.(current) ?? completionMessage(current))
      } else if (mounted.current) {
        setError(terminalFailureMessage(current.status))
      }
    } catch (caught) {
      if (mounted.current) setError(safeErrorMessage(caught, options.failureMessage))
    } finally {
      activeRef.current = false
      if (mounted.current) setIsActive(false)
    }
  }, [options])

  return { job, isActive, message, error, run, setLastJob: setJob }
}

function completionMessage(job: ApiHarnessJob): string {
  const count = `${job.recordsWritten} record${job.recordsWritten === 1 ? '' : 's'}`
  return job.status === 'completed_with_warnings'
    ? `Completed with warnings. ${count} updated; ${job.warningsCount} warning${job.warningsCount === 1 ? '' : 's'}.`
    : `Completed successfully. ${count} updated.`
}

function terminalFailureMessage(status: ApiHarnessJob['status']): string {
  switch (status) {
    case 'failed':
      return 'The job failed safely. Review the saved connection and try again.'
    case 'cancelled':
      return 'The job was cancelled. You can try again.'
    case 'stale_or_interrupted':
      return 'The job was interrupted. Confirm the local app is running, then try again.'
    case 'queued':
    case 'running':
    case 'writing':
      return 'The job is still running.'
    case 'completed':
    case 'completed_with_warnings':
      return ''
  }
}

function safeErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 401) return 'Your session expired. Sign in again and retry.'
    if (error.status === 403) return 'Your account is not authorized to run this action.'
    if (error.status === 409) return error.message
    if (error.status === 422) return 'The saved API settings are incomplete or invalid. Review Settings and retry.'
    if (error.status === 429) return 'Alleva is limiting requests. Wait briefly and retry.'
    return fallback
  }
  if (error instanceof Error && error.message) return fallback
  return fallback
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}
