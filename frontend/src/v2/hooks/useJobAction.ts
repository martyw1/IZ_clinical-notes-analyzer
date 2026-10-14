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
  const latest = useRef(options)
  latest.current = options
  const activeRef = useRef(false)
  const mounted = useRef(true)
  const [job, setJob] = useState<ApiHarnessJob | null>(null)
  const [isActive, setIsActive] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [monitorAttempt, setMonitorAttempt] = useState(0)
  const setLastJob = useCallback((saved: ApiHarnessJob | null) => {
    // A delayed history response must not replace a job started on this page.
    setJob((current) => current && current.jobId !== saved?.jobId ? current : saved)
  }, [])

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  useEffect(() => {
    if (!job || isTerminalJobStatus(job.status)) return
    let stopped = false
    activeRef.current = true
    setIsActive(true)
    setError('')
    const started = Date.now()
    async function monitor() {
      try {
        let current = job!
        while (!stopped && !isTerminalJobStatus(current.status)) {
          current = await latest.current.poll(current.jobId)
          if (stopped) return
          setJob(current)
          if (!isTerminalJobStatus(current.status)) {
            if (Date.now() - started >= 60_000) setMessage('The job is still running. You can continue using the app while it updates.')
            await delay(document.hidden ? 5_000 : 1_000)
          }
        }
        if (stopped) return
        if (isSuccessfulJobStatus(current.status)) {
          await latest.current.onCompleted?.(current)
          if (!stopped) setMessage(latest.current.successMessage?.(current) ?? completionMessage(current))
        } else setError(terminalFailureMessage(current.status))
      } catch (caught) {
        if (!stopped) setError(safeErrorMessage(caught, 'Unable to check progress. The backend job may still be running. Try again to reconnect.'))
      } finally {
        if (!stopped) { activeRef.current = false; setIsActive(false) }
      }
    }
    void monitor()
    return () => { stopped = true; activeRef.current = false }
    // Status changes update the panel without restarting the monitor.
  }, [job?.jobId, monitorAttempt])

  const run = useCallback(async () => {
    if (activeRef.current) return
    setError('')
    setMessage('')
    if (job && !isTerminalJobStatus(job.status)) {
      setMonitorAttempt((value) => value + 1)
      return
    }
    activeRef.current = true
    setIsActive(true)
    try {
      const started = await latest.current.start()
      if (mounted.current) {
        setJob(started)
        if (isTerminalJobStatus(started.status)) {
          activeRef.current = false
          setIsActive(false)
          if (isSuccessfulJobStatus(started.status)) {
            await latest.current.onCompleted?.(started)
            if (mounted.current) setMessage(latest.current.successMessage?.(started) ?? completionMessage(started))
          } else setError(terminalFailureMessage(started.status))
        }
      }
    } catch (caught) {
      activeRef.current = false
      if (mounted.current) { setIsActive(false); setError(safeErrorMessage(caught, latest.current.failureMessage)) }
    }
  }, [job])

  return { job, isActive, message, error, run, setLastJob }
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
