import { useState } from 'react'
import { cancelApiHarnessJob, getApiHarnessJob, listApiHarnessArtifacts, startApiHarnessJob } from '../api/jobs'
import { ApiRequestError } from '../api/json'
import type { ApiHarnessArtifact, ApiHarnessJob } from '../api/types'

type JobProgressCardProps = {
  readonly token: string
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to start API harness job.'
}

export function JobProgressCard({ token }: JobProgressCardProps) {
  const [job, setJob] = useState<ApiHarnessJob | null>(null)
  const [artifacts, setArtifacts] = useState<readonly ApiHarnessArtifact[]>([])
  const [error, setError] = useState('')
  const [isStarting, setIsStarting] = useState(false)
  const [isCancelling, setIsCancelling] = useState(false)
  const status = job?.status ?? 'idle'
  const progress = job?.progressPercent ?? 0

  const startJob = async () => {
    setError('')
    setIsStarting(true)
    try {
      const started = await startApiHarnessJob(token)
      setJob(started)
      const completed = await pollJob(started)
      setJob(completed)
      setArtifacts(completed.artifacts.length ? completed.artifacts : await listApiHarnessArtifacts(token, completed.jobId))
    } catch (startError) {
      setError(messageForError(startError))
    } finally {
      setIsStarting(false)
    }
  }

  async function pollJob(started: ApiHarnessJob): Promise<ApiHarnessJob> {
    let current = started
    for (let attempt = 0; attempt < 20 && !isTerminalStatus(current.status); attempt += 1) {
      await sleep(120)
      current = await getApiHarnessJob(token, current.jobId)
      setJob(current)
    }
    return current
  }

  async function cancelJob() {
    if (!job) return
    setIsCancelling(true)
    try {
      setJob(await cancelApiHarnessJob(token, job.jobId))
    } catch (cancelError) {
      setError(messageForError(cancelError))
    } finally {
      setIsCancelling(false)
    }
  }

  return (
    <section className='panel job-card' aria-label='Pull ALL Treatment Plans job card'>
      <div>
        <p className='eyebrow'>Large API job</p>
        <h2>Pull ALL Treatment Plans - ALL Fields</h2>
        <p>Starts as a backend job and keeps browser output bounded to compact progress and previews.</p>
      </div>
      <div className='job-meter' aria-label={`Job progress ${progress}%`}>
        <span style={{ width: `${progress}%` }} />
      </div>
      <dl className='job-stats'>
        <div>
          <dt>Status</dt>
          <dd>{status}</dd>
        </div>
        <div>
          <dt>Records written</dt>
          <dd>{job?.recordsWritten ?? 0}</dd>
        </div>
        <div>
          <dt>Preview limit</dt>
          <dd>25 records / 50 fields</dd>
        </div>
      </dl>
      <div className='button-row'>
        <button type='button' onClick={startJob} disabled={isStarting}>
          {isStarting ? 'Starting large job...' : 'Start large job'}
        </button>
        <button type='button' className='secondary-button' onClick={() => void cancelJob()} disabled={!job || isCancelling || isTerminalStatus(status)}>
          {isCancelling ? 'Cancelling job...' : 'Cancel in backend queue'}
        </button>
      </div>
      {error && <p role='alert' className='error-banner'>{error}</p>}
      {artifacts.length > 0 && (
        <ul className='artifact-list' aria-label='Completed job artifacts'>
          {artifacts.map((artifact) => (
            <li key={artifact.artifactId}>{artifact.name}</li>
          ))}
        </ul>
      )}
    </section>
  )
}

function isTerminalStatus(status: string): boolean {
  return ['completed', 'completed_with_warnings', 'failed', 'cancelled', 'stale_or_interrupted'].includes(status)
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}
