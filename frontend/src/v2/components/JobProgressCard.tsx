import { useEffect, useRef, useState } from 'react'
import { cancelApiHarnessJob, downloadApiHarnessArtifact, getApiHarnessJob, getApiHarnessPreview, listApiHarnessArtifacts, startApiHarnessJob } from '../api/jobs'
import { ApiRequestError } from '../api/json'
import type { ApiHarnessArtifact, ApiHarnessJob, ApiHarnessPreview } from '../api/types'

type JobProgressCardProps = {
  readonly token: string
}

function messageForError(error: unknown): string {
  if (error instanceof ApiRequestError) return error.message
  if (error instanceof Error) return error.message
  return 'Unable to start API harness job.'
}

export function JobProgressCard({ token }: JobProgressCardProps) {
  const isMounted = useRef(true)
  const [job, setJob] = useState<ApiHarnessJob | null>(null)
  const [artifacts, setArtifacts] = useState<readonly ApiHarnessArtifact[]>([])
  const [preview, setPreview] = useState<ApiHarnessPreview | null>(null)
  const [error, setError] = useState('')
  const [isStarting, setIsStarting] = useState(false)
  const [isCancelling, setIsCancelling] = useState(false)
  const status = job?.status ?? 'idle'
  const progress = job?.progressPercent ?? 0

  useEffect(() => {
    isMounted.current = true
    return () => {
      isMounted.current = false
    }
  }, [])

  const startJob = async () => {
    setError('')
    setIsStarting(true)
    try {
      const started = await startApiHarnessJob(token)
      setJob(started)
      const completed = await pollJob(started)
      setJob(completed)
      if (completed.status === 'completed' || completed.status === 'completed_with_warnings') {
        const [completedArtifacts, completedPreview] = await Promise.all([
          completed.artifacts.length ? completed.artifacts : listApiHarnessArtifacts(token, completed.jobId),
          getApiHarnessPreview(token, completed.jobId),
        ])
        setArtifacts(completedArtifacts)
        setPreview(completedPreview)
      } else if (completed.status === 'failed') {
        setArtifacts(await listApiHarnessArtifacts(token, completed.jobId))
      }
    } catch (startError) {
      setError(messageForError(startError))
    } finally {
      setIsStarting(false)
    }
  }

  async function pollJob(started: ApiHarnessJob): Promise<ApiHarnessJob> {
    let current = started
    for (let attempt = 0; attempt < 5_000 && !isTerminalStatus(current.status) && isMounted.current; attempt += 1) {
      await sleep(120)
      current = await getApiHarnessJob(token, current.jobId)
      if (isMounted.current) setJob(current)
    }
    if (!isTerminalStatus(current.status) && isMounted.current) throw new Error('The API job is still running. Return to this page to check it again.')
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

  async function downloadArtifact(artifact: ApiHarnessArtifact) {
    try {
      await downloadApiHarnessArtifact(token, job?.jobId ?? '', artifact)
    } catch (downloadError) {
      setError(messageForError(downloadError))
    }
  }

  return (
    <section className='panel job-card' aria-label='Diagnostic treatment-plan pull'>
      <div>
        <p className='eyebrow'>Preview and export only</p>
        <h2>Diagnostic treatment-plan pull</h2>
        <p>Pulls available treatment-plan metadata into a redacted preview and secret-keyed identifier-hashed local artifacts. Direct patient and treatment-plan identifiers are not written. This diagnostic does not add records to the Treatment Plans queue.</p>
      </div>
      <div className='job-meter' role='progressbar' aria-label='API job progress' aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
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
        <button type='button' onClick={startJob} disabled={isStarting || (job !== null && !isTerminalStatus(status))}>
          {isStarting ? 'Starting diagnostic pull...' : 'Pull treatment plans for diagnostic preview'}
        </button>
        <button type='button' className='secondary-button' onClick={() => void cancelJob()} disabled={!job || isCancelling || isTerminalStatus(status)}>
          {isCancelling ? 'Cancelling job...' : 'Cancel in backend queue'}
        </button>
      </div>
      {error && <p role='alert' className='error-banner'>{error}</p>}
      {status === 'completed_with_warnings' && (
        <p role='status'>Pull completed safely with a warning: Alleva repeated a full page or the diagnostic safety limit was reached. Duplicate pages were not written.</p>
      )}
      {status === 'failed' && (
        <p role='alert' className='error-banner'>The diagnostic pull failed before completion. A redacted failure was recorded in Forensic Logs and the local error artifact; credentials and response bodies were not logged.</p>
      )}
      {artifacts.length > 0 && (
        <ul className='artifact-list' aria-label='Completed job artifacts'>
          {artifacts.map((artifact) => (
            <li key={artifact.artifactId}>
              <span>{artifact.name}</span>
              <button type='button' className='secondary-button' onClick={() => void downloadArtifact(artifact)} aria-label={`Download ${artifact.name}`}>Download</button>
            </li>
          ))}
        </ul>
      )}
      {preview && (
        <div>
          <p className='muted'>{preview.message}</p>
          {preview.records.length > 0 && (
            <table>
              <thead><tr><th>Record</th><th>Source</th><th>Redaction</th></tr></thead>
              <tbody>{preview.records.map((record) => <tr key={`${record.recordIndex}-${record.recordId}`}><td>{record.recordId}</td><td>{record.sourceEndpoint}</td><td>{record.redactionStatus}</td></tr>)}</tbody>
            </table>
          )}
        </div>
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
