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
          <dd>{status === 'idle' ? '0' : '6'}</dd>
        </div>
        <div>
          <dt>Preview limit</dt>
          <dd>25 records / 50 fields</dd>
        </div>
      </dl>
      <div className='button-row'>
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
        </ul>
      )}
    </section>
  )
}
