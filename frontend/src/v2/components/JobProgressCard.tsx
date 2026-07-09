<<<<<<< HEAD
import { useState } from 'react'
import { getApiHarnessJob, listApiHarnessArtifacts, startApiHarnessJob } from '../api/jobs'
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
  const status = job?.status ?? 'idle'
  const progress = job?.progressPercent ?? 0

  const startJob = async () => {
    setError('')
    setIsStarting(true)
    try {
      const completed = await pollJob(await startApiHarnessJob(token))
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
    }
    return current
=======
import { useEffect, useState } from 'react'

type JobStatus = 'idle' | 'queued' | 'running' | 'completed' | 'cancelled'

export function JobProgressCard() {
  const [status, setStatus] = useState<JobStatus>('idle')
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    if (status !== 'running') return undefined
    const timer = window.setInterval(() => {
      setProgress((current) => {
        const next = Math.min(100, current + 25)
        if (next === 100) setStatus('completed')
        return next
      })
    }, 80)
    return () => window.clearInterval(timer)
  }, [status])

  const startJob = () => {
    setProgress(5)
    setStatus('running')
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
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
<<<<<<< HEAD
          <dd>{job?.recordsWritten ?? 0}</dd>
=======
          <dd>{status === 'idle' ? '0' : '6'}</dd>
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
        </div>
        <div>
          <dt>Preview limit</dt>
          <dd>25 records / 50 fields</dd>
        </div>
      </dl>
      <div className='button-row'>
<<<<<<< HEAD
        <button type='button' onClick={startJob} disabled={isStarting}>
          {isStarting ? 'Starting large job...' : 'Start large job'}
        </button>
        <button type='button' className='secondary-button' disabled>
          Cancel in backend queue
        </button>
      </div>
      {error && <p role='alert' className='error-banner'>{error}</p>}
      {artifacts.length > 0 && (
        <ul className='artifact-list' aria-label='Completed job artifacts'>
          {artifacts.map((artifact) => (
            <li key={artifact.artifactId}>{artifact.name}</li>
          ))}
=======
        <button type='button' onClick={startJob}>
          Start synthetic large job
        </button>
        <button type='button' className='secondary-button' onClick={() => setStatus('cancelled')}>
          Cancel
        </button>
      </div>
      {status === 'completed' && (
        <ul className='artifact-list' aria-label='Completed job artifacts'>
          <li>run-summary.json</li>
          <li>all-treatment-plans.all-fields.redacted.jsonl</li>
          <li>all-treatment-plans.flattened-fields.tsv</li>
          <li>all-treatment-plans.observed-schema.json</li>
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
        </ul>
      )}
    </section>
  )
}
<<<<<<< HEAD

function isTerminalStatus(status: string): boolean {
  return ['completed', 'completed_with_warnings', 'failed', 'cancelled', 'stale_or_interrupted'].includes(status)
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}
=======
>>>>>>> 7ff7108 (Rebuild V2 beta local desktop app)
